
from pathlib import Path
import csv
import argparse
import cv2
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent

VIDEO_SOURCES = {
    "N": BASE_DIR / "videos" / "north.mp4",
    "S": BASE_DIR / "videos" / "south.mp4",
    "E": BASE_DIR / "videos" / "east.mp4",
    "W": BASE_DIR / "videos" / "west.mp4",
}

# IMPORTANT: These labels must match best.pt's actual class names.
EMERGENCY_LABELS = {
    "ambulance",
    "police car",
    "police_car",
    "fire truck",
    "fire_truck",
    "emergency",
}

NORMAL_LABELS = {
    "car",
    "motorcycle",
    "motorbike",
    "bus",
    "truck",
    "van",
    "bicycle",
}


def classify_label(label):
    label = label.lower().strip()

    if label in EMERGENCY_LABELS:
        return "emergency"
    if label in NORMAL_LABELS:
        return "normal"

    return "other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=str(BASE_DIR / "best.pt"),
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=5,
        help="Run detection every N frames",
    )
    parser.add_argument("--confidence", type=float, default=0.25)
    args = parser.parse_args()

    if args.sample_every < 1:
        raise ValueError("--sample-every must be >= 1")

    model_path = Path(args.model)
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")

    for direction, path in VIDEO_SOURCES.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing {direction} video: {path}"
            )

    model = YOLO(str(model_path))

    print("Model classes:", model.names)

    # Keep one video reader for each approach.
    captures = {}
    fps_values = {}

    for direction, path in VIDEO_SOURCES.items():
        cap = cv2.VideoCapture(str(path))

        if not cap.isOpened():
            for opened in captures.values():
                opened.release()
            raise RuntimeError(f"Cannot open video: {path}")

        captures[direction] = cap
        fps_values[direction] = cap.get(cv2.CAP_PROP_FPS) or 25.0

    # Use the slowest FPS as a common timeline rate.
    # This is a basic offline synchronization assumption.
    common_fps = min(fps_values.values())
    output_dir = BASE_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_csv = output_dir / "camera_traffic_state.csv"

    frame_number = 0
    processed_samples = 0

    try:
        with output_csv.open(
            "w", newline="", encoding="utf-8"
        ) as file:
            fields = [
                "timestamp_s",
                "approach",
                "frame_number",
                "normal_count",
                "emergency_count",
                "other_count",
            ]

            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()

            while True:
                frames = {}
                ended = False

                # Read one frame from each camera for this snapshot.
                for direction, cap in captures.items():
                    success, frame = cap.read()

                    if not success:
                        ended = True
                        break

                    frames[direction] = frame

                # Stop when any video ends to avoid mixing timelines.
                if ended:
                    break

                current_frame = frame_number
                frame_number += 1

                if current_frame % args.sample_every != 0:
                    continue

                # Each video is passed through the same model separately.
                for direction, frame in frames.items():
                    result = model.predict(
                        source=frame,
                        conf=args.confidence,
                        verbose=False,
                    )[0]

                    normal_count = 0
                    emergency_count = 0
                    other_count = 0

                    if result.boxes is not None:
                        for box in result.boxes:
                            class_id = int(box.cls.item())
                            label = result.names[class_id]
                            category = classify_label(label)

                            if category == "normal":
                                normal_count += 1
                            elif category == "emergency":
                                emergency_count += 1
                            else:
                                other_count += 1

                    writer.writerow({
                        "timestamp_s": round(
                            current_frame / common_fps, 3
                        ),
                        "approach": direction,
                        "frame_number": current_frame,
                        "normal_count": normal_count,
                        "emergency_count": emergency_count,
                        "other_count": other_count,
                    })

                processed_samples += 1

                if processed_samples % 50 == 0:
                    print(
                        f"Processed synchronized snapshots: "
                        f"{processed_samples}"
                    )

    finally:
        for cap in captures.values():
            cap.release()

    print(f"\nDetection pipeline complete: {output_csv}")
    print("Remember: class labels must match the trained model.")


if __name__ == "__main__":
    main()
