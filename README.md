---
title: Tanauan Traffic Management System
emoji: 🚦
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# TrafficDetect

Real-time object detection web app built with Flask and YOLOv8.

## What it does

- Browser webcam mode: captures frames in the browser and sends them to Flask for inference.
- IP camera / RTSP mode: streams video from a server-accessible source and runs YOLO detection on each frame.

## Hugging Face Spaces Deployment

This project is set up for a **Docker Space** on Hugging Face.

### Files used for deployment

- `Dockerfile`
- `.dockerignore`
- `requirements.txt`

### Notes

- The app listens on port `7860` in Docker/Spaces.
- Your custom model must remain at `model/best.pt`.
- Free Spaces can sleep when unused.

## Local Setup

1. Put your custom trained `best.pt` inside the `model/` folder.
   - If your weights are in `weights.zip`, extract it first.
   - The app expects `model/best.pt` and will not use the pretrained YOLO weights.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   python main.py
   ```

4. Open `http://127.0.0.1:5000`.

## Notes

- Browser webcam access happens in the client browser, so permission prompts are expected.
- For IP cameras, use a source URL that OpenCV can read, such as an RTSP stream.
- This project is configured for your custom training checkpoint, so `yolov8s.pt` and `yolov8x.pt` are not used.

## Supported Classes

The model is trained to detect:

- Bike
- Bus
- Car
- Ebike
- Jeep
- Motor
- Tricycle
- Truck
