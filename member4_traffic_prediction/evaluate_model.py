
import csv
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RESULTS_FILE = BASE_DIR / "predictions.csv"


def evaluate():
    with RESULTS_FILE.open(
        "r", newline="", encoding="utf-8"
    ) as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise ValueError("No predictions found. Run traffic_pipeline.py first.")

    errors = [
        int(row["predicted_count"]) - int(row["actual_count"])
        for row in rows
    ]

    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error ** 2 for error in errors) / len(errors))
    within_five = sum(abs(error) <= 5 for error in errors)

    print(f"Evaluated predictions: {len(errors)}")
    print(f"MAE: {mae:.2f} vehicles")
    print(f"RMSE: {rmse:.2f} vehicles")
    print(f"Within +/-5 vehicles: {within_five / len(errors) * 100:.1f}%")


if __name__ == "__main__":
    evaluate()
