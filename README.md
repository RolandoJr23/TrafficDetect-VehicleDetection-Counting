# Traffic Detect: Vehicle Detection & Counting System

Rapid infrastructure growth in Tanauan City increased traffic congestion along Pres. J.P. Laurel Highway and A. Mabini Avenue. Using Operational Research and AI with the YOLOv8 algorithm, the study provides real-time vehicle detection and traffic flow monitoring to support the City TMO in traffic planning and regulation.

## Core Features

- Browser webcam mode for live frame capture and detection.
- IP camera / RTSP mode for server-side streaming input.
- Custom YOLOv8 object detection using `model/best.pt`.
- Annotated detection preview with bounding boxes and confidence scores.
- Live vehicle counting with OUT / IN totals.
- Line-crossing detection for counting vehicles as they pass through the frame.
- Per-class counts for the supported vehicle types.

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

## Tech Stack

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python, Flask, Gunicorn
- **Computer Vision:** Ultralytics YOLOv8, OpenCV, NumPy
- **Model File:** Custom-trained YOLO checkpoint at `model/best.pt`

## Project Structure

```text
traffic-detect/
├── model/
│   └── best.pt             # Custom YOLOv8 model weights
├── static/
│   ├── css/                # Stylesheets for the web UI
│   └── js/                 # JavaScript for webcam capture and API logic
├── templates/
│   └── index.html          # Main dashboard interface
├── main.py                 # Flask application entry point and YOLO inference
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

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
- This project is configured for your custom training checkpoint.

## License 

This project does not currently specify a license.

## Researcher & Developer

Research & Developed by Rolando Jr Hernandez
