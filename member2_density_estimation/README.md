# Member 2 — Traffic Density Estimation

## Objective
Estimate traffic conditions using SUMO and TraCI simulation data.

## Implemented
- Lane-wise vehicle count extraction
- Lane occupancy, halting vehicle count, and mean speed
- Prototype density classification: EMPTY, LOW, MEDIUM, HIGH
- Reusable Python module: `density_module.py`
- CSV density report
- Basic and heavy-traffic simulation tests

## Current Limitations
- Density thresholds require further validation.
- Current SUMO network is a 2×2 grid, not the final four-way signalized intersection.
- YOLO detections are not yet mapped to SUMO lanes.
- Integration with Member 3's adaptive signal controller is pending.

## Files
- `density_module.py`
- `density_report.csv`
- `Member2_Traffic_Density_Estimation.ipynb`

## Integration Interface
The function `get_lane_density_report(traci)` returns lane-wise vehicle count, halting count, mean speed, and density classification while the SUMO TraCI simulation is running.
