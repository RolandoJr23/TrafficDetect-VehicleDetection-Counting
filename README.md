# TrafficDetect

Real-time object detection web app built with Flask and YOLOv8.

## What it does

- Browser webcam mode: captures frames in the browser and sends them to Flask for inference.
- IP camera / RTSP mode: streams video from a server-accessible source and runs YOLO detection on each frame.

## Deployment

The project is split into two deploy targets:

- Backend: Render
- Frontend: Vercel

### Backend on Render

Render should deploy the Flask app from the repository root using Docker.

Files used by Render:

- `Dockerfile`
- `render.yaml`
- `requirements.txt`

Notes:

- The backend listens on the `PORT` environment variable.
- Your custom model must remain at `model/best.pt`.
- `render.yaml` points Render at the Dockerfile and `/health` check route.

### Frontend on Vercel

Vercel serves the static frontend files in this repo:

- `index.html`
- `videocapture/index.html`
- `assets/`
- `static/`

The frontend keeps using `/api/*` URLs, and Vercel proxies those requests through `api/[...path].js` to your Render backend.

The template files under `templates/` are for Flask on Render, and the root-level `index.html` plus `videocapture/index.html` are the Vercel copies of the same pages.

Before deploying the frontend, set this environment variable in Vercel:

- `RENDER_BACKEND_URL` = your Render service URL, for example `https://your-service.onrender.com`

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
