```python
import unittest

from member4_traffic_prediction.traffic_predictor import TrafficPredictor
from member3_signal_optimization.signal_controller import adaptive_green_seconds


class TestTrafficPredictor(unittest.TestCase):

    def test_prediction_with_single_reading(self):
        predictor = TrafficPredictor()
        predictor.update(5)
        self.assertEqual(predictor.predict(), 5)

    def test_prediction_updates_with_new_readings(self):
        predictor = TrafficPredictor()
        predictor.update(5)
        first = predictor.predict()
        predictor.update(15)
        second = predictor.predict()
        self.assertNotEqual(first, second)

    def test_prediction(self):
        predictor = TrafficPredictor()
        for count in [8, 12, 15, 19, 22]:
            predictor.update(count)
        self.assertEqual(predictor.predict(), 18)

    def test_empty_history(self):
        predictor = TrafficPredictor()
        with self.assertRaises(ValueError):
            predictor.predict()

    def test_traffic_levels(self):
        predictor = TrafficPredictor()
        self.assertEqual(predictor.traffic_level(0), "LOW")
        self.assertEqual(predictor.traffic_level(9), "LOW")
        self.assertEqual(predictor.traffic_level(10), "MEDIUM")
        self.assertEqual(predictor.traffic_level(24), "MEDIUM")
        self.assertEqual(predictor.traffic_level(25), "HIGH")

    def test_high_traffic(self):
        predictor = TrafficPredictor()
        self.assertEqual(predictor.traffic_level(30), "HIGH")

    def test_invalid_inputs(self):
        predictor = TrafficPredictor()
        for value in [-1, 2.5, True, "10"]:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    predictor.update(value)

    def test_prediction_adjustment(self):
        base = adaptive_green_seconds(25)
        self.assertEqual(max(10, min(40, base - 2)), 23)
        self.assertEqual(max(10, min(40, base)), 25)
        self.assertEqual(max(10, min(40, base + 2)), 27)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```