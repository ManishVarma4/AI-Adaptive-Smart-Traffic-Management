# Member 3 — Adaptive Signal Optimization (SUMO + TraCI)

This module builds a four-arm, signalized intersection and compares a fixed-time controller against a density-aware adaptive controller. It reuses Member 2's `get_lane_density_report(traci_connection)` function.

## Architecture

`Four-way SUMO junction -> Member 2 lane density report -> Member 3 signal timing -> TraCI traffic-light state`

The network has four incoming approaches (`inN`, `inS`, `inE`, `inW`) and four outgoing edges. The demonstration uses straight-through routes only. The controller discovers signal-link indices from TraCI rather than assuming a hard-coded link order.

## Requirements

- Eclipse SUMO, including `sumo`, `netconvert`, and TraCI Python tools
- Python 3.9+
- `SUMO_HOME` set to the SUMO installation directory, or SUMO binaries available on `PATH`

If `import traci` fails, add `%SUMO_HOME%\\tools` to `PYTHONPATH` on Windows or `$SUMO_HOME/tools` on macOS/Linux.

## Run

From the repository root:

```bash
python member3_signal_optimization/run_comparison.py
```

The script builds `four_way.net.xml` with `netconvert`, writes `traffic_demand.rou.xml`, then runs both controllers with the same demand and seed. It writes:

- `comparison_results.csv` — high-level performance metrics
- `green_decisions.csv` — green-duration decisions and demand at each phase switch

Optional safety cap:

```bash
python member3_signal_optimization/run_comparison.py --duration-cap 1400
```

## Controller behavior

- **Fixed-time baseline:** 30 s green for each axis, then 3 s yellow and 1 s all-red.
- **Adaptive:** alternates north/south and east/west to prevent starvation. It uses Member 2's vehicle count, halting count, and density class to choose a 10–40 s green duration. Yellow and all-red clearance are preserved.
- The current adaptive controller changes green duration, not phase order; this makes the baseline comparison transparent and fair.

## Metrics

- `vehicles_arrived`: throughput proxy; higher is generally better.
- `avg_inbound_queue_vehicles`: average total halting vehicles across four inbound lanes per simulation step; lower is better.
- `estimated_waiting_seconds_per_arrived_vehicle`: stopped-vehicle seconds divided by arrived vehicles; a simple estimate, not a formal SUMO tripinfo statistic.
- `unfinished_expected`: expected vehicles still in the simulation at the end; ideally zero.

Results are generated locally and are not prefilled because they depend on the SUMO version. Do not claim improvement until the generated CSVs confirm it.

## Hybrid YOLO + SUMO scope

The controller currently consumes SUMO lane measurements through Member 2. YOLO detections are not yet mapped to SUMO lane IDs. A camera calibration/mapping layer is still required before claiming real-camera counts directly control the simulated intersection.
