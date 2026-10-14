import unittest
from traffic_predictor import TrafficPredictor


class TestTrafficPredictor(unittest.TestCase):
    def test_prediction(self):
        p = TrafficPredictor()
        for count in [8, 12, 15, 19, 22]:
            p.update(count)
        self.assertEqual(p.predict(), 18)

    def test_empty_history(self):
        p = TrafficPredictor()
        with self.assertRaises(ValueError):
            p.predict()

    def test_high_traffic(self):
        p = TrafficPredictor()
        self.assertEqual(p.traffic_level(30), "HIGH")


if __name__ == "__main__":
    unittest.main()