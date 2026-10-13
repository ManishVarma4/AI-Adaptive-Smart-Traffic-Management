
from collections import deque
from statistics import mean


class TrafficPredictor:
    """Predict near-future traffic using recent vehicle counts."""

    def __init__(self, history_size=5):
        if history_size < 1:
            raise ValueError("history_size must be at least 1")

        self.counts = deque(maxlen=history_size)

    def update(self, vehicle_count):
        """Record the observed number of vehicles."""
        if isinstance(vehicle_count, bool) or not isinstance(
            vehicle_count, (int, float)
        ):
            raise ValueError("Vehicle count must be a number")

        if vehicle_count < 0 or not float(vehicle_count).is_integer():
            raise ValueError("Vehicle count must be a non-negative integer")

        self.counts.append(int(vehicle_count))

    def predict(self):
        """Estimate traffic for the next observation."""
        if not self.counts:
            raise ValueError("Add at least one vehicle count before predicting")

        # Use a recent weighted average so newer observations matter more.
        weights = list(range(1, len(self.counts) + 1))
        weighted_total = sum(
            count * weight
            for count, weight in zip(self.counts, weights)
        )

        prediction = round(weighted_total / sum(weights))
        return max(0, prediction)

    def traffic_level(self, predicted_count):
        """Classify predicted traffic using configurable thresholds."""
        if predicted_count < 10:
            return "LOW"
        elif predicted_count < 25:
            return "MEDIUM"
        return "HIGH"


if __name__ == "__main__":
    predictor = TrafficPredictor(history_size=5)

    sample_counts = [8, 12, 15, 19, 22]

    for count in sample_counts:
        predictor.update(count)

    predicted = predictor.predict()

    print("Recent vehicle counts:", list(predictor.counts))
    print("Predicted next count:", predicted)
    print("Predicted traffic level:", predictor.traffic_level(predicted))
