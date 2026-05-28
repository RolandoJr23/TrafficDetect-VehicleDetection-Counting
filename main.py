from __future__ import annotations

import base64
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "model" / "best.pt"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

MODEL_LOCK = threading.Lock()
MODEL = None
COUNTING_LOCK = threading.RLock()
COUNTING_STATE: Dict[str, Any] = {
    "tracks": {},
    "next_track_id": 1,
    "direction_counts": {},
    "direction_totals": {"OUT": 0, "IN": 0},
    "frame_shape": None,
    "last_update": 0.0,
}

COUNT_LINE_RATIO = 0.78
TRACK_MATCH_DISTANCE = 90.0
TRACK_TTL_SECONDS = 1.5
COUNT_RESET_SECONDS = 5.0
DETECTION_IMGSZ = 128
DETECTION_CONFIDENCE = 0.45
DETECTION_JPEG_QUALITY = 60
DETECTION_MAX_DET = 10
MAX_DETECTION_SIDE = 256


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def resolve_model_path() -> Path:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Custom model not found: {MODEL_PATH}. "
            "Extract your trained weights.zip and place best.pt inside the model folder."
        )
    return MODEL_PATH


def load_model() -> YOLO:
    model_path = resolve_model_path()

    model = YOLO(str(model_path))
    try:
        model.fuse()
    except Exception:
        # Fusing is optional and can fail for some exported weights.
        pass
    return model


def detection_kwargs(imgsz: int | None = None) -> Dict[str, Any]:
    return {
        "verbose": False,
        "conf": DETECTION_CONFIDENCE,
        "imgsz": imgsz or DETECTION_IMGSZ,
        "max_det": DETECTION_MAX_DET,
    }


def resize_for_detection(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    longest_side = max(height, width)
    if longest_side <= MAX_DETECTION_SIDE:
        return frame

    scale = MAX_DETECTION_SIDE / float(longest_side)
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)


def get_model() -> YOLO:
    global MODEL
    if MODEL is None:
        MODEL = load_model()
    return MODEL


def decode_image_file(image_file) -> np.ndarray:
    file_bytes = np.frombuffer(image_file.read(), dtype=np.uint8)
    frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode the uploaded image.")
    return frame


def decode_base64_image(image_data: str) -> np.ndarray:
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]
    raw_bytes = base64.b64decode(image_data)
    buffer = np.frombuffer(raw_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode the base64 image.")
    return frame


def format_label(name: str, confidence: float) -> str:
    return f"{name} {confidence:.2f}"


def _frame_side(y: float, line_y: int) -> str:
    return "above" if y < line_y else "below"


def reset_counting_state(frame_shape: Tuple[int, int] | None = None) -> None:
    with COUNTING_LOCK:
        COUNTING_STATE["tracks"] = {}
        COUNTING_STATE["next_track_id"] = 1
        COUNTING_STATE["direction_counts"] = {}
        COUNTING_STATE["direction_totals"] = {"OUT": 0, "IN": 0}
        COUNTING_STATE["frame_shape"] = frame_shape
        COUNTING_STATE["last_update"] = time.monotonic()


def ensure_counting_state(frame_shape: Tuple[int, int]) -> None:
    now = time.monotonic()
    current_shape = COUNTING_STATE.get("frame_shape")
    last_update = float(COUNTING_STATE.get("last_update") or 0.0)

    if current_shape != frame_shape or (last_update and now - last_update > COUNT_RESET_SECONDS):
        reset_counting_state(frame_shape)


def get_direction_bucket(class_name: str) -> Dict[str, int]:
    direction_counts = COUNTING_STATE["direction_counts"]
    bucket = direction_counts.get(class_name)
    if bucket is None:
        bucket = {"OUT": 0, "IN": 0}
        direction_counts[class_name] = bucket
    return bucket


def copy_direction_counts() -> Dict[str, Dict[str, int]]:
    return {
        class_name: {"OUT": int(bucket.get("OUT", 0)), "IN": int(bucket.get("IN", 0))}
        for class_name, bucket in COUNTING_STATE["direction_counts"].items()
    }


def draw_counting_line(frame: np.ndarray, line_y: int) -> np.ndarray:
    annotated = frame.copy()
    height, width = annotated.shape[:2]

    cv2.line(annotated, (0, line_y), (width - 1, line_y), (255, 255, 255), 1, cv2.LINE_AA)

    def draw_label(text: str, center_x: int) -> None:
        font_scale = 0.28
        thickness = 1
        padding_x = 3
        padding_y = 2
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        box_w = text_w + padding_x * 2
        box_h = text_h + baseline + padding_y * 2
        x1 = int(center_x - box_w / 2)
        x1 = max(8, min(x1, width - box_w - 8))
        y2 = max(line_y - 5, box_h + 5)
        y1 = y2 - box_h
        cv2.rectangle(annotated, (x1, y1), (x1 + box_w, y2), (0, 0, 0), -1)
        cv2.putText(
            annotated,
            text,
            (x1 + padding_x, y2 - baseline - padding_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    draw_label("OUT", int(width * 0.17))
    draw_label("IN", int(width * 0.83))

    return annotated


def annotate_frame(
    frame: np.ndarray,
    imgsz: int = 640,
    use_tracking: bool = False,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    model = get_model()

    with MODEL_LOCK:
        if use_tracking:
            try:
                result = model.track(
                    frame,
                    persist=True,
                    **detection_kwargs(imgsz),
                    tracker="bytetrack.yaml",
                )[0]
            except Exception:
                result = model(frame, **detection_kwargs(imgsz))[0]
        else:
            result = model(frame, **detection_kwargs(imgsz))[0]

    annotated = frame.copy()
    detections: List[Dict[str, Any]] = []
    names = result.names

    if result.boxes is None or len(result.boxes) == 0:
        return annotated, detections

    boxes = result.boxes.xyxy.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)
    confs = result.boxes.conf.cpu().numpy()
    track_ids = None
    if getattr(result.boxes, "id", None) is not None:
        try:
            track_ids = result.boxes.id.cpu().numpy().astype(int)
        except Exception:
            track_ids = None

    for index, (box, class_id, confidence) in enumerate(zip(boxes, classes, confs)):
        x1, y1, x2, y2 = [int(v) for v in box.tolist()]
        class_id = int(class_id)
        confidence = float(confidence)
        class_name = names.get(class_id, str(class_id))
        label = format_label(class_name, float(confidence))
        track_id = int(track_ids[index]) if track_ids is not None and index < len(track_ids) else None

        color = (
            int((class_id * 37) % 255),
            int((class_id * 17) % 255),
            int((class_id * 29) % 255),
        )
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        text_top = max(y1 - text_h - 10, 0)
        cv2.rectangle(
            annotated,
            (x1, text_top),
            (x1 + text_w + 10, text_top + text_h + 10),
            color,
            -1,
        )
        cv2.putText(
            annotated,
            label,
            (x1 + 5, text_top + text_h + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "track_id": track_id,
                "box": {
                    "x1": int(x1),
                    "y1": int(y1),
                    "x2": int(x2),
                    "y2": int(y2),
                },
            }
        )

    return annotated, detections


def update_line_counts(
    frame: np.ndarray,
    detections: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int], int]:
    height, width = frame.shape[:2]
    line_y = int(height * COUNT_LINE_RATIO)
    now = time.monotonic()

    with COUNTING_LOCK:
        ensure_counting_state((height, width))

        tracks = COUNTING_STATE["tracks"]
        matched_track_ids = set()
        tracking_enabled = any(detection.get("track_id") is not None for detection in detections)

        for detection in detections:
            box = detection["box"]
            class_name = str(detection.get("class_name", "Unknown"))
            center_x = (box["x1"] + box["x2"]) / 2.0
            center_y = (box["y1"] + box["y2"]) / 2.0

            track_id_value = detection.get("track_id")
            if tracking_enabled and track_id_value is not None:
                track_key = f"track:{int(track_id_value)}"
                track = tracks.get(track_key)
                current_side = _frame_side(center_y, line_y)

                if track is None:
                    tracks[track_key] = {
                        "centroid": (center_x, center_y),
                        "class_name": class_name,
                        "last_seen": now,
                        "counted_side": current_side,
                    }
                    continue

                previous_side = _frame_side(track["centroid"][1], line_y)
                if previous_side != current_side and track.get("counted_side") != current_side:
                    direction = "OUT" if previous_side == "above" and current_side == "below" else "IN"
                    bucket = get_direction_bucket(class_name)
                    bucket[direction] = int(bucket.get(direction, 0)) + 1
                    COUNTING_STATE["direction_totals"][direction] = int(
                        COUNTING_STATE["direction_totals"].get(direction, 0)
                    ) + 1
                    track["counted_side"] = current_side

                track["centroid"] = (center_x, center_y)
                track["class_name"] = class_name
                track["last_seen"] = now
                continue

            best_track_id = None
            best_distance = float("inf")

            for track_id, track in tracks.items():
                if track_id in matched_track_ids:
                    continue
                if track.get("class_name") != class_name:
                    continue

                prev_x, prev_y = track["centroid"]
                distance = float(((prev_x - center_x) ** 2 + (prev_y - center_y) ** 2) ** 0.5)
                if distance < best_distance:
                    best_distance = distance
                    best_track_id = track_id

            if best_track_id is None:
                for track_id, track in tracks.items():
                    if track_id in matched_track_ids:
                        continue

                    prev_x, prev_y = track["centroid"]
                    distance = float(((prev_x - center_x) ** 2 + (prev_y - center_y) ** 2) ** 0.5)
                    if distance < best_distance:
                        best_distance = distance
                        best_track_id = track_id

            if best_track_id is None or best_distance > TRACK_MATCH_DISTANCE:
                track_id = int(COUNTING_STATE["next_track_id"])
                COUNTING_STATE["next_track_id"] = track_id + 1
                tracks[track_id] = {
                    "centroid": (center_x, center_y),
                    "class_name": class_name,
                    "last_seen": now,
                    "counted_side": _frame_side(center_y, line_y),
                }
                matched_track_ids.add(track_id)
                continue

            track = tracks[best_track_id]
            previous_side = _frame_side(track["centroid"][1], line_y)
            current_side = _frame_side(center_y, line_y)

            if previous_side != current_side and track.get("counted_side") != current_side:
                # Crossing downward is treated as OUT, upward as IN.
                direction = "OUT" if previous_side == "above" and current_side == "below" else "IN"
                bucket = get_direction_bucket(class_name)
                bucket[direction] = int(bucket.get(direction, 0)) + 1
                COUNTING_STATE["direction_totals"][direction] = int(
                    COUNTING_STATE["direction_totals"].get(direction, 0)
                ) + 1
                track["counted_side"] = current_side

            track["centroid"] = (center_x, center_y)
            track["class_name"] = class_name
            track["last_seen"] = now
            matched_track_ids.add(best_track_id)

        stale_ids = [
            track_id
            for track_id, track in tracks.items()
            if now - float(track.get("last_seen", now)) > TRACK_TTL_SECONDS
        ]
        for track_id in stale_ids:
            tracks.pop(track_id, None)

        COUNTING_STATE["last_update"] = now
        direction_totals = {
            "OUT": int(COUNTING_STATE["direction_totals"].get("OUT", 0)),
            "IN": int(COUNTING_STATE["direction_totals"].get("IN", 0)),
        }
        return copy_direction_counts(), direction_totals, line_y


def summarize_detections(detections: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for detection in detections:
        class_name = str(detection.get("class_name", "Unknown"))
        summary[class_name] = summary.get(class_name, 0) + 1
    return summary


def encode_image_to_data_url(frame: np.ndarray) -> str:
    success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), DETECTION_JPEG_QUALITY])
    if not success:
        raise ValueError("Unable to encode image as JPEG.")
    base64_image = base64.b64encode(buffer.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{base64_image}"


def parse_source(source: str) -> Any:
    source = source.strip()
    if source.isdigit():
        return int(source)
    return source


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/videocapture")
def videocapture():
    return render_template("videocapture.html")


@app.route("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(BASE_DIR / "assets", filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detect", methods=["POST"])
def detect_webcam_frame():
    try:
        if "frame" in request.files:
            frame = decode_image_file(request.files["frame"])
        else:
            payload = request.get_json(silent=True) or {}
            image_data = payload.get("image")
            if not image_data:
                return jsonify({"error": "No frame image provided."}), 400
            frame = decode_base64_image(image_data)

        frame = resize_for_detection(frame)
        annotated, detections = annotate_frame(frame, imgsz=DETECTION_IMGSZ, use_tracking=False)
        counts = summarize_detections(detections)
        direction_counts, direction_totals, line_y = update_line_counts(frame, detections)
        annotated = draw_counting_line(annotated, line_y)
        return jsonify(
            {
                "image": encode_image_to_data_url(annotated),
                "detections": detections,
                "count": len(detections),
                "counts": counts,
                "direction_counts": direction_counts,
                "direction_totals": direction_totals,
                "line_y": line_y,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/counting/reset", methods=["POST"])
def reset_counting():
    reset_counting_state()
    return jsonify({"status": "ok"})


def generate_mjpeg(source: Any):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        yield b"--frame\r\nContent-Type: text/plain\r\n\r\nUnable to open video source.\r\n"
        return

    try:
        while True:
            success, frame = cap.read()
            if not success:
                break

            frame = resize_for_detection(frame)
            annotated, _ = annotate_frame(frame, imgsz=DETECTION_IMGSZ, use_tracking=False)
            success, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), DETECTION_JPEG_QUALITY])
            if not success:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
    finally:
        cap.release()


@app.route("/api/stream")
def stream_ip_camera():
    source = request.args.get("source", "").strip()
    if not source:
        return jsonify({"error": "Missing source query parameter."}), 400

    return Response(
        generate_mjpeg(parse_source(source)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
