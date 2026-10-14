
from pathlib import Path
import argparse
import csv
import cv2
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent

VIDEO_SOURCES = {
    "N": BASE_DIR / "videos" / "north.mp4",
    "S": BASE_DIR / "videos" / "south.mp4",
    "E": BASE_DIR / "videos" / "east.mp4",
    "W": BASE_DIR / "videos" / "west.mp4",
}


def get_vehicle_class(class_name):
    """
    Map model labels to normal/emergency.
    Update these labels according to the actual model.
    Unknown labels are not assumed to be normal vehicles.
    """
    label = class_name.lower().strip()

    emergency_labels = {
        "ambulance",
        "fire truck",
        "fire_truck",
        "police car",
        "police_car",
        "emergency",
    }

    normal_labels = {
        "car",
        "motorcycle",
        "motorbike",
        "bus",
        "truck",
        "bicycle",
        "van",
    }

    if label in emergency_labels:
        return "emergency"

    if label in normal_labels:
        return "normal"

    return "other"


def process_video(model, approach, video_path, output_dir, writer):
    if not video_path.exists():
        print(f"[WARNING] {approach}: video not found: {video_path}")
        return

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    output_path = output_dir / f"{approach}_annotated.mp4"
    video_writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height),
    )

    frame_number = 0

    try:
        while True:
            success, frame = cap.read()

            if not success:
                break

            frame_number += 1

            result = model.predict(
                source=frame,
                conf=0.25,
                verbose=False,
            )[0]

            normal_count = 0
            emergency_count = 0
            other_count = 0

            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    class_name = result.names[class_id]
                    category = get_vehicle_class(class_name)

                    if category == "normal":
                        normal_count += 1
                    elif category == "emergency":
                        emergency_count += 1
                    else:
                        other_count += 1

            annotated_frame = result.plot()

            cv2.putText(
                annotated_frame,
                f"Approach: {approach} | Normal: {normal_count} "
                f"| Emergency: {emergency_count}",
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            video_writer.write(annotated_frame)

            # Log frame-level counts.
            writer.writerow({
                "approach": approach,
                "frame": frame_number,
                "timestamp_s": round((frame_number - 1) / fps, 3),
                "normal_count": normal_count,
                "emergency_count": emergency_count,
                "other_count": other_count,
            })

            if frame_number % 100 == 0:
                print(
                    f"[{approach}] Frames: {frame_number} | "
                    f"Normal: {normal_count} | "
                    f"Emergency: {emergency_count}"
                )

    finally:
        cap.release()
        video_writer.release()

    print(f"[DONE] {approach}: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=str(BASE_DIR / "best.pt"),
        help="Path to YOLO .pt model",
    )
    parser.add_argument(
        "--approach",
        choices=["N", "S", "E", "W", "ALL"],
        default="ALL",
    )
    args = parser.parse_args()

    model_path = Path(args.model)

    if not model_path.is_file():
        raise FileNotFoundError(
            f"Model not found: {model_path}. "
            "Add the model or pass --model with its path."
        )

    output_dir = BASE_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_path))

    selected_approaches = (
        list(VIDEO_SOURCES)
        if args.approach == "ALL"
        else [args.approach]
    )

    csv_path = output_dir / "vehicle_counts.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        fieldnames = [
            "approach",
            "frame",
            "timestamp_s",
            "normal_count",
            "emergency_count",
            "other_count",
        ]

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for approach in selected_approaches:
            process_video(
                model,
                approach,
                VIDEO_SOURCES[approach],
                output_dir,
                writer,
            )

    print(f"\nDetection complete. CSV saved at: {csv_path}")


if __name__ == "__main__":
    main()
