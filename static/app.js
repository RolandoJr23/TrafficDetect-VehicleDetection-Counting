const video = document.getElementById("webcam-video");
const annotatedImage = document.getElementById("annotated-image");
const startBtn = document.getElementById("start-webcam");
const stopBtn = document.getElementById("stop-webcam");
const statusLabel = document.getElementById("webcam-status");
const detectionCount = document.getElementById("detection-count");
const canvas = document.getElementById("capture-canvas");
const streamView = document.getElementById("stream-view");
const streamSourceInput = document.getElementById("stream-source");
const openStreamBtn = document.getElementById("open-stream");
const closeStreamBtn = document.getElementById("close-stream");
const modeWebcamBtn = document.getElementById("mode-webcam");
const modeStreamBtn = document.getElementById("mode-stream");
const webcamPanel = document.getElementById("webcam-panel");
const streamPanel = document.getElementById("stream-panel");
const vehicleOutTotal = document.getElementById("vehicle-out-total");
const vehicleInTotal = document.getElementById("vehicle-in-total");
const vehicleTotalInline = document.getElementById("vehicle-total-inline");
const vehicleStatus = document.getElementById("vehicle-status");
const vehicleCountBody = document.getElementById("vehicle-count-body");

const VEHICLE_ORDER = ["Bike", "Bus", "Car", "Ebike", "Jeep", "Motor", "Tricycle", "Truck"];
const BACKEND_BASE_URL = String(window.RENDER_BACKEND_URL || "").replace(/\/$/, "");
const IS_LOCAL_HOST = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

let webcamStream = null;
let webcamRafId = null;
let webcamFrameCallbackId = null;
let webcamBusy = false;
let lastCaptureAt = 0;
let activeMode = "webcam";
let demoMode = false;

const CAPTURE_INTERVAL_MS = IS_LOCAL_HOST ? 400 : 900;
const MAX_CAPTURE_WIDTH = IS_LOCAL_HOST ? 960 : 128;
const CAMERA_WIDTH = IS_LOCAL_HOST ? 1280 : 480;
const CAMERA_HEIGHT = IS_LOCAL_HOST ? 720 : 360;
const CAMERA_FPS = IS_LOCAL_HOST ? 30 : 24;

function getUserMedia(constraints) {
  if (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === "function") {
    return navigator.mediaDevices.getUserMedia(constraints);
  }

  const legacyGetUserMedia =
    navigator.getUserMedia ||
    navigator.webkitGetUserMedia ||
    navigator.mozGetUserMedia ||
    navigator.msGetUserMedia;

  if (typeof legacyGetUserMedia === "function") {
    return new Promise((resolve, reject) => {
      legacyGetUserMedia.call(navigator, constraints, resolve, reject);
    });
  }

  return Promise.reject(
    new Error("Camera access is not supported in this browser or context.")
  );
}

function setStatus(message) {
  statusLabel.textContent = message;
}

function showLiveVideoPreview() {
  video.classList.remove("hidden");
  annotatedImage.classList.remove("hidden");
  annotatedImage.style.opacity = "0";
}

function showAnnotatedPreview() {
  annotatedImage.classList.remove("hidden");
  annotatedImage.style.opacity = "1";
}

function enableDemoMode(reason) {
  if (!demoMode) {
    demoMode = true;
    console.warn("Switching to demo mode:", reason);
  }

  annotatedImage.alt = "Local webcam preview";
  detectionCount.textContent = "0";
  setStatus("Demo mode");
  setVehicleSummary({ OUT: 0, IN: 0 }, "Backend unavailable, using local preview");
  updateVehicleTable({});
  showLiveVideoPreview();
}

function setVehicleSummary(total, message) {
  const outTotal = Number(total?.OUT || 0);
  const inTotal = Number(total?.IN || 0);

  if (vehicleOutTotal) {
    vehicleOutTotal.textContent = String(outTotal);
  }

  if (vehicleInTotal) {
    vehicleInTotal.textContent = String(inTotal);
  }

  if (vehicleTotalInline) {
    vehicleTotalInline.textContent = String(outTotal + inTotal);
  }

  if (vehicleStatus) {
    vehicleStatus.textContent = message;
  }
}

function updateVehicleTable(counts) {
  if (!vehicleCountBody) {
    return;
  }

  const countMap = counts || {};
  vehicleCountBody.innerHTML = VEHICLE_ORDER.map((vehicle) => {
    const directionCounts = countMap[vehicle] || {};
    const outCount = Number(directionCounts.OUT || 0);
    const inCount = Number(directionCounts.IN || 0);
    return `<tr><td>${vehicle}</td><td>${outCount}</td><td>${inCount}</td></tr>`;
  }).join("");
}

function setMode(mode) {
  const previousMode = activeMode;
  activeMode = mode;

  const webcamActive = mode === "webcam";
  webcamPanel.classList.toggle("active", webcamActive);
  streamPanel.classList.toggle("active", !webcamActive);
  modeWebcamBtn.classList.toggle("active", webcamActive);
  modeStreamBtn.classList.toggle("active", !webcamActive);

  if (webcamActive) {
    if (previousMode !== "webcam") {
      closeStream();
    }
    setStatus(webcamStream ? "Streaming" : "Idle");
  } else {
    if (previousMode !== "stream") {
      stopWebcam();
    }
    setStatus("IP Camera mode");
  }
}

async function startWebcam() {
  try {
    webcamStream = await getUserMedia({
      video: {
        facingMode: "environment",
        width: { ideal: IS_LOCAL_HOST ? 1920 : CAMERA_WIDTH },
        height: { ideal: IS_LOCAL_HOST ? 1080 : CAMERA_HEIGHT },
        frameRate: { ideal: CAMERA_FPS, max: CAMERA_FPS },
      },
      audio: false,
    });

    video.srcObject = webcamStream;
    await video.play();
    annotatedImage.src = "";
    annotatedImage.alt = "Annotated detection result";
    annotatedImage.style.opacity = "0";
    showLiveVideoPreview();
    startBtn.disabled = true;
    stopBtn.disabled = false;
    setStatus("Streaming");
    setVehicleSummary({ OUT: 0, IN: 0 }, "Waiting for detection");
    updateVehicleTable({});

    if (IS_LOCAL_HOST) {
      fetch("/api/counting/reset", { method: "POST" }).catch(() => {});
    }

    lastCaptureAt = 0;
    scheduleCaptureLoop();
  } catch (error) {
    console.error(error);
    setStatus("Camera denied");
    alert(
      "Could not access the camera. Please allow camera permissions or open the app in a secure context (https:// or localhost)."
    );
  }
}

function stopWebcam() {
  if (webcamRafId) {
    window.cancelAnimationFrame(webcamRafId);
    webcamRafId = null;
  }

  if (webcamFrameCallbackId !== null && typeof video.cancelVideoFrameCallback === "function") {
    video.cancelVideoFrameCallback(webcamFrameCallbackId);
    webcamFrameCallbackId = null;
  }

  if (webcamStream) {
    webcamStream.getTracks().forEach((track) => track.stop());
    webcamStream = null;
  }

  video.srcObject = null;
  video.onloadedmetadata = null;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  setStatus("Idle");
  setVehicleSummary({ OUT: 0, IN: 0 }, "Waiting for live detection");
  updateVehicleTable({});
}

function scheduleCaptureLoop() {
  if (!webcamStream) {
    return;
  }

  if (typeof video.requestVideoFrameCallback === "function") {
    if (webcamFrameCallbackId !== null) {
      return;
    }
    webcamFrameCallbackId = video.requestVideoFrameCallback((now, metadata) => {
      webcamFrameCallbackId = null;
      captureLoop(metadata?.mediaTime ? metadata.mediaTime * 1000 : now);
    });
    return;
  }

  if (webcamRafId !== null) {
    return;
  }
  webcamRafId = window.requestAnimationFrame(captureLoop);
}

function captureLoop(timestamp) {
  if (!webcamStream) {
    return;
  }

  if (demoMode) {
    scheduleCaptureLoop();
    return;
  }

  if (!webcamBusy && timestamp - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
    lastCaptureAt = timestamp;
    captureAndDetect();
  }

  scheduleCaptureLoop();
}

async function captureAndDetect() {
  if (webcamBusy || !webcamStream || video.videoWidth === 0) {
    return;
  }

  webcamBusy = true;
  const context = canvas.getContext("2d");
  const scale = Math.min(1, MAX_CAPTURE_WIDTH / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(async (blob) => {
    if (!blob) {
      webcamBusy = false;
      return;
    }

    const formData = new FormData();
    formData.append("frame", blob, "frame.jpg");

    try {
      const response = await fetch("/api/detect", {
        method: "POST",
        body: formData,
      });
      const contentType = response.headers.get("content-type") || "";
      const responseText = await response.text();
      let data = null;

      if (contentType.includes("application/json")) {
        try {
          data = JSON.parse(responseText);
        } catch (parseError) {
          throw new Error("Detection service returned invalid JSON.");
        }
      }

      if (!response.ok) {
        throw new Error((data && data.error) || responseText || "Detection failed");
      }

      if (!data) {
        throw new Error("Detection service returned an unexpected response.");
      }

      annotatedImage.src = data.image;
      showAnnotatedPreview();
      detectionCount.textContent = String(data.count ?? 0);
      updateVehicleTable(data.direction_counts || {});
      setVehicleSummary(
        data.direction_totals || { OUT: 0, IN: 0 },
        data.count ? "Live detection active" : "No vehicles detected"
      );
      setStatus("Streaming");
    } catch (error) {
      console.error(error);
      setStatus("Detection error");
      setVehicleSummary({ OUT: 0, IN: 0 }, "Detection unavailable");
      showLiveVideoPreview();
    } finally {
      webcamBusy = false;
    }
  }, "image/jpeg", 0.8);
}

function closeStream() {
  streamView.removeAttribute("src");
  streamView.src = "";
}

async function getBackendBaseUrl() {
  return BACKEND_BASE_URL;
}

async function openStream() {
  const source = streamSourceInput.value.trim();
  if (!source) {
    alert("Please enter an IP camera / RTSP source URL.");
    return;
  }

  if (demoMode) {
    alert("IP camera streaming is disabled in demo mode.");
    setStatus("Demo mode");
    return;
  }

  const backendBaseUrl = await getBackendBaseUrl();
  const streamUrl = backendBaseUrl
    ? `${backendBaseUrl}/api/stream?source=${encodeURIComponent(source)}`
    : `/api/stream?source=${encodeURIComponent(source)}`;
  streamView.src = streamUrl;
}

startBtn.addEventListener("click", startWebcam);
stopBtn.addEventListener("click", stopWebcam);
openStreamBtn.addEventListener("click", openStream);
closeStreamBtn.addEventListener("click", closeStream);
modeWebcamBtn.addEventListener("click", () => setMode("webcam"));
modeStreamBtn.addEventListener("click", () => setMode("stream"));

window.addEventListener("beforeunload", stopWebcam);

setMode("webcam");
