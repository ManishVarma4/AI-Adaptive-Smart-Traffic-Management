
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "output" / "camera_traffic_state.csv"
OUTPUT_FILE = BASE_DIR / "output" / "traffic_state_by_timestamp.csv"

DIRECTIONS = ["N", "S", "E", "W"]


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run camera_traffic_pipeline.py first."
        )

    df = pd.read_csv(INPUT_FILE)

    required = {
        "timestamp_s",
        "approach",
        "normal_count",
        "emergency_count",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    if df.empty:
        raise ValueError("Input CSV contains no traffic observations.")

    if df.duplicated(["timestamp_s", "approach"]).any():
        raise ValueError(
            "Duplicate timestamp/approach records found. "
            "Check camera synchronization and input data."
        )

    df["approach"] = df["approach"].astype(str).str.upper()

    if not df["approach"].isin(DIRECTIONS).all():
        raise ValueError("Approach must be N, S, E, or W.")

    for column in ["normal_count", "emergency_count"]:
        df[column] = pd.to_numeric(df[column], errors="raise")

        if (df[column] < 0).any():
            raise ValueError(f"{column} cannot contain negative values.")

    # Convert the four direction rows into one row per timestamp.
    pivot = df.pivot(
        index="timestamp_s",
        columns="approach",
        values=["normal_count", "emergency_count"],
    )

    expected_columns = [
        (metric, direction)
        for metric in ["normal_count", "emergency_count"]
        for direction in DIRECTIONS
    ]

    missing_columns = [
        column for column in expected_columns
        if column not in pivot.columns
    ]

    if missing_columns:
        raise ValueError(
            "Some timestamps do not contain all four directions. "
            "Check the input videos and synchronization."
        )

    pivot = pivot[expected_columns]
    pivot.columns = [
        f"{metric}_{direction}"
        for metric, direction in pivot.columns
    ]

    pivot = pivot.reset_index()

    count_columns = [
        column for column in pivot.columns
        if column.startswith(("normal_count_", "emergency_count_"))
    ]

    pivot["total_detected"] = pivot[count_columns].sum(axis=1)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pivot.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Snapshots: {len(pivot)}")
    print(pivot.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
