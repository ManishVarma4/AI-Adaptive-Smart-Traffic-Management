
import csv
from pathlib import Path

from traffic_predictor import TrafficPredictor

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "traffic_data.csv"
OUTPUT_FILE = BASE_DIR / "predictions.csv"


def run_pipeline():
    predictor = TrafficPredictor(history_size=5)
    results = []

    with INPUT_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames or not {
            "timestamp", "vehicle_count"
        }.issubset(reader.fieldnames):
            raise ValueError(
                "CSV must contain timestamp and vehicle_count columns"
            )

        for row in reader:
            timestamp = row["timestamp"]

            try:
                actual = int(row["vehicle_count"])
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid vehicle count at {timestamp}"
                )

            if actual < 0:
                raise ValueError(
                    f"Negative vehicle count at {timestamp}"
                )

            # Predict before adding the current observation.
            if predictor.counts:
                predicted = predictor.predict()
                results.append({
                    "timestamp": timestamp,
                    "actual_count": actual,
                    "predicted_count": predicted,
                    "predicted_level": predictor.traffic_level(predicted),
                })

            predictor.update(actual)

    with OUTPUT_FILE.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        columns = [
            "timestamp", "actual_count",
            "predicted_count", "predicted_level"
        ]
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    print(f"Predictions saved to: {OUTPUT_FILE}")
    print(f"Predictions generated: {len(results)}")
    for result in results:
        print(result)


if __name__ == "__main__":
    run_pipeline()
