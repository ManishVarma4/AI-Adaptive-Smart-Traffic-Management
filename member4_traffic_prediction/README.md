# Member 4 — Traffic Prediction

## Overview
This module predicts short-term traffic vehicle counts from historical observations and classifies predicted traffic levels as LOW, MEDIUM, or HIGH.

## Features
- Weighted moving-average traffic prediction
- Traffic-level classification
- CSV-based input and prediction output
- Evaluation using MAE, RMSE, and predictions within five vehicles
- Unit tests for the traffic predictor

## Project Files
- `traffic_predictor.py` — implements the traffic prediction model
- `traffic_data.csv` — sample traffic observations
- `traffic_pipeline.py` — generates predictions from the sample data
- `predictions.csv` — generated prediction results
- `evaluate_model.py` — evaluates prediction performance
- `evaluate_trend.py` — evaluates the predictions saved by the pipeline
- `test_traffic_predictor.py` — unit tests
- `README.md` — project documentation

## How to Run
Run these commands from the project root:

```bash
python -m unittest discover -s member4_traffic_prediction -p "test_*.py"
python member4_traffic_prediction/traffic_pipeline.py
python member4_traffic_prediction/evaluate_trend.py
```

## Sample Evaluation
On the provided sample dataset, the pipeline produced:

- MAE: 7.00 vehicles
- RMSE: 7.53 vehicles
- Predictions within five vehicles: 36.4%

These results use a small sample dataset and do not guarantee real-world performance.

## Limitations
- Evaluation uses a small sample dataset.
- Predictions depend on the supplied historical observations.
- Live SUMO integration is not included in this version.
