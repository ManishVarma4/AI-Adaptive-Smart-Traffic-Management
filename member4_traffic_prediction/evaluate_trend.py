"""Evaluate trend-prediction results using MAE and RMSE."""
import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREDICTIONS_FILE = HERE / "predictions.csv"


def main():
    with PREDICTIONS_FILE.open("r", newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        print("No predictions found.")
        return

    errors = [
        float(row["actual_count"]) - float(row["predicted_count"])
        for row in rows
        if row.get("predicted_count", "").strip()
    ]

    if not errors:
        print("No valid prediction values to evaluate.")
        return

    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error ** 2 for error in errors) / len(errors))
    within_five = sum(abs(error) <= 5 for error in errors) / len(errors) * 100

    print(f"Evaluated predictions: {len(errors)}")
    print(f"MAE: {mae:.2f} vehicles")
    print(f"RMSE: {rmse:.2f} vehicles")
    print(f"Within 5 vehicles: {within_five:.1f}%")


if __name__ == "__main__":
    main()