
"""Compare fixed-time and adaptive SUMO traffic signal controllers."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def configure_sumo_python():
    home = os.environ.get("SUMO_HOME")
    if home:
        tools = str(Path(home) / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)


configure_sumo_python()

try:
    import traci
except ImportError as exc:
    raise SystemExit(
        "Cannot import TraCI. Set SUMO_HOME and ensure "
        "SUMO_HOME/tools is available."
    ) from exc

from build_network import build_network, find_sumo_binary
from signal_controller import (
    APPROACH_EDGES,
    APPROACH_ORDER,
    approach_demand,
    adaptive_green_seconds,
    choose_next_approach,
    discover_signal_groups,
    make_state,
)
from member2_density_estimation.density_module import get_lane_density_report
from member4_traffic_prediction.traffic_predictor import TrafficPredictor
from dashboard import start_dashboard, update_dashboard


DIRECTIONS = ("N", "S", "E", "W")
INBOUND_EDGES = set(APPROACH_EDGES.values())


def find_emergency_approaches(conn):
    """Find emergency vehicles in the SUMO simulation."""
    found = set()

    for vehicle_id in conn.vehicle.getIDList():
        try:
            if conn.vehicle.getTypeID(vehicle_id) != "emergency":
                continue

            edge_id = conn.vehicle.getRoadID(vehicle_id)

            for approach, inbound_edge in APPROACH_EDGES.items():
                if edge_id == inbound_edge:
                    found.add(approach)
                    break
        except Exception:
            # A vehicle may temporarily be on an internal junction edge.
            continue

    return found


def load_camera_data(csv_path):
    """Load the prepared camera traffic-state CSV."""
    if not csv_path or not Path(csv_path).is_file():
        raise FileNotFoundError(
            f"Camera CSV not found: {csv_path}\n"
            "Run the camera pipeline and traffic-state preparation first."
        )

    snapshots = {}

    with Path(csv_path).open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        required = {"timestamp_s"}
        for direction in DIRECTIONS:
            required.add(f"normal_count_{direction}")
            required.add(f"emergency_count_{direction}")

        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Camera CSV missing columns: {sorted(missing)}"
            )

        for row in reader:
            timestamp = float(row["timestamp_s"])
            snapshot = {}

            for direction in DIRECTIONS:
                normal = int(float(row[f"normal_count_{direction}"]))
                emergency = int(float(row[f"emergency_count_{direction}"]))

                if normal < 0 or emergency < 0:
                    raise ValueError("Vehicle counts cannot be negative.")

                snapshot[direction] = {
                    "normal": normal,
                    "emergency": emergency,
                    "total": normal + emergency,
                }

            if timestamp in snapshots:
                raise ValueError(
                    f"Duplicate timestamp {timestamp} in camera CSV."
                )

            snapshots[timestamp] = snapshot

    if not snapshots:
        raise ValueError("Camera CSV contains no snapshots.")

    return sorted(snapshots.items())


def get_camera_snapshot(snapshots, simulation_time):
    """Return the latest camera snapshot at or before simulation time."""
    eligible = [
        snapshot
        for timestamp, snapshot in snapshots
        if timestamp <= simulation_time
    ]

    return eligible[-1] if eligible else None


def camera_demand(snapshot, approach):
    """Use detected vehicle count as a basic demand score."""
    return float(snapshot[approach]["total"])


def run_one(
    mode,
    net_file,
    route_file,
    duration_cap=1500,
    gui=False,
    source="sumo",
    camera_csv=None,
    seed=42,
):
    """Run one controller using SUMO measurements or camera replay."""

    snapshots = load_camera_data(camera_csv) if source == "camera" else []

    sumo = find_sumo_binary("sumo-gui" if gui else "sumo")

    cmd = [
        sumo,
        "-n", str(net_file),
        "-r", str(route_file),
        "--no-step-log", "true",
        "--duration-log.disable", "true",
        "--time-to-teleport", "-1",
        "--waiting-time-memory", "1000",
        "--seed", str(seed),
    ]

    if gui:
        view_settings = HERE / "sumo_viewsetting.xml"

        if view_settings.is_file():
            cmd.extend([
                "--gui-settings-file",
                str(view_settings)
            ])
        else:
            print(f"Warning: View settings not found: {view_settings}")

        cmd.extend(["--start", "--delay", "50"])

    label = f"member3_{mode}_{source}"
    traci.start(cmd, label=label)
    conn = traci.getConnection(label)

    try:
        groups = discover_signal_groups(conn)

        current_approach = "N"
        green_seconds = 30 if mode == "fixed" else 20
        yellow_seconds = 3
        all_red_seconds = 1

        phase = "green"
        phase_remaining = green_seconds

        conn.trafficlight.setRedYellowGreenState(
            groups.tls_id,
            make_state(groups, current_approach, "G"),
        )

        now = conn.simulation.getTime()
        last_served = {a: now for a in APPROACH_ORDER}
        last_served[current_approach] = now

        step_count = 0
        total_halting_per_step = 0
        stopped_vehicle_steps = 0
        arrived_count = 0
        departed_count = 0

        adaptive_decisions = 0
        emergency_priority_decisions = 0
        starvation_preventions = 0

        previous_was_emergency = False
        green_log = []
        dashboard_events = []
        dashboard_history = []

        predictor = TrafficPredictor(history_size=5)
        next_prediction_sample = 0.0
        prediction_interval = 300.0

        predicted_count = 0
        predicted_level = "LOW"

        while (
            conn.simulation.getMinExpectedNumber() > 0
            and step_count < duration_cap
        ):
            conn.simulationStep()
            step_count += 1
            now = conn.simulation.getTime()

            # SUMO metrics remain available in both modes for evaluation.
            report = get_lane_density_report(conn)

            inbound = [
                lane for lane in report
                if lane.rsplit("_", 1)[0] in INBOUND_EDGES
            ]

            total_halting_per_step += sum(
                int(report[lane]["halting"]) for lane in inbound
            )

            vehicle_ids = conn.vehicle.getIDList()
            stopped_vehicle_steps += sum(
                1 for vehicle_id in vehicle_ids
                if conn.vehicle.getSpeed(vehicle_id) < 0.1
            )

            arrived_count += len(conn.simulation.getArrivedIDList())
            departed_count += len(conn.simulation.getDepartedIDList())

            # Camera mode replays recorded observations against SUMO time.
            snapshot = (
                get_camera_snapshot(snapshots, now)
                if source == "camera"
                else None
            )

            if source == "sumo":
                observed_count = sum(
                    int(report[lane]["vehicles"]) for lane in inbound
                )
            elif snapshot is not None:
                observed_count = sum(
                    snapshot[a]["total"] for a in DIRECTIONS
                )
            else:
                observed_count = None

            if (
                observed_count is not None
                and now >= next_prediction_sample
            ):
                predictor.update(observed_count)
                predicted_count = predictor.predict()
                predicted_level = predictor.traffic_level(predicted_count)
                next_prediction_sample = now + prediction_interval

            # Publish live measurements to the local browser dashboard.
            direction_metrics = {}
            for approach, label in zip(DIRECTIONS, ("NORTH", "SOUTH", "EAST", "WEST")):
                edge_id = APPROACH_EDGES[approach]
                lane_rows = [
                    row for lane_id, row in report.items()
                    if lane_id.rsplit("_", 1)[0] == edge_id
                ]
                sumo_vehicles = sum(int(row.get("vehicles", 0)) for row in lane_rows)
                queue = sum(int(row.get("halting", 0)) for row in lane_rows)
                if source == "camera" and snapshot is not None:
                    visible_vehicles = int(snapshot[approach]["total"])
                else:
                    visible_vehicles = sumo_vehicles
                signal = "RED"
                if approach == current_approach:
                    signal = "GREEN" if phase == "green" else ("YELLOW" if phase == "yellow" else "RED")
                direction_metrics[label] = {
                    "vehicles": visible_vehicles,
                    "queue": queue,
                    "signal": signal,
                    "passed": 0,
                }
            dashboard_history.append({
                "time_s": round(now, 1),
                "queue": sum(item["queue"] for item in direction_metrics.values()),
            })
            update_dashboard({
                "status": f"Running {mode} controller",
                "controller": mode,
                "source": source,
                "time_s": round(now, 1),
                "step": step_count,
                "vehicles_passed": arrived_count,
                "vehicles_departed": departed_count,
                "vehicles_in_network": len(vehicle_ids),
                "decision_count": adaptive_decisions if mode == "adaptive" else len(green_log),
                "predicted_count": predicted_count,
                "predicted_level": predicted_level,
                "phase": phase,
                "active_direction": current_approach,
                "green_remaining": max(0, phase_remaining),
                "directions": direction_metrics,
                "events": dashboard_events[-100:],
                "history": dashboard_history[-180:],
            })

            phase_remaining -= 1

            if phase_remaining > 0:
                continue

            if phase == "green":
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id,
                    make_state(groups, current_approach, "y"),
                )
                phase = "yellow"
                phase_remaining = yellow_seconds
                continue

            if phase == "yellow":
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id,
                    "r" * groups.signal_count,
                )
                phase = "all_red"
                phase_remaining = all_red_seconds
                continue

            # All-red interval is over. Select the next approach.
            report = get_lane_density_report(conn)
            starvation_used = False
            was_emergency = False
            prediction_adjustment = 0

            if source == "sumo":
                emergency_approaches = find_emergency_approaches(conn)
            elif snapshot is not None:
                emergency_approaches = {
                    a for a in DIRECTIONS
                    if snapshot[a]["emergency"] > 0
                }
            else:
                emergency_approaches = set()

            if mode == "fixed":
                # Preserve the original fixed-time cyclic baseline.
                current_approach = APPROACH_ORDER[
                    (APPROACH_ORDER.index(current_approach) + 1)
                    % len(APPROACH_ORDER)
                ]
                green_seconds = 30

            else:
                overdue = {
                    a for a in APPROACH_ORDER
                    if now - last_served[a] >= 90.0
                }

                if source == "camera" and snapshot is not None:
                    emergency_candidates = [
                        a for a in APPROACH_ORDER
                        if a in emergency_approaches
                        and not (
                            previous_was_emergency
                            and a == current_approach
                        )
                    ]

                    if emergency_candidates:
                        current_approach = max(
                            emergency_candidates,
                            key=lambda a: camera_demand(snapshot, a),
                        )
                        was_emergency = True
                    else:
                        overdue_candidates = [
                            a for a in APPROACH_ORDER if a in overdue
                        ]
                        candidates = (
                            overdue_candidates
                            if overdue_candidates
                            else list(APPROACH_ORDER)
                        )

                        current_approach = max(
                            candidates,
                            key=lambda a: camera_demand(snapshot, a),
                        )
                        starvation_used = current_approach in overdue

                    base_green = max(
                        10,
                        min(
                            40,
                            int(10 + camera_demand(snapshot, current_approach)),
                        ),
                    )

                elif source == "camera":
                    # No camera sample is available at this simulation time.
                    current_approach = APPROACH_ORDER[
                        (APPROACH_ORDER.index(current_approach) + 1)
                        % len(APPROACH_ORDER)
                    ]
                    base_green = 20

                else:
                    current_approach, was_emergency = choose_next_approach(
                        report,
                        last_served,
                        now,
                        emergency_approaches,
                        previous_was_emergency,
                        max_red_wait=90.0,
                    )

                    starvation_used = (
                        current_approach in overdue and not was_emergency
                    )

                    base_green = adaptive_green_seconds(
                        approach_demand(report, current_approach)
                    )

                if was_emergency:
                    emergency_priority_decisions += 1

                if starvation_used:
                    starvation_preventions += 1

                prediction_adjustment = {
                    "LOW": -2,
                    "MEDIUM": 0,
                    "HIGH": 2,
                }[predicted_level]

                green_seconds = max(
                    10,
                    min(40, base_green + prediction_adjustment),
                )
                adaptive_decisions += 1

            previous_was_emergency = was_emergency
            last_served[current_approach] = now

            if source == "camera" and snapshot is not None:
                demand = camera_demand(snapshot, current_approach)
            else:
                demand = approach_demand(report, current_approach)

            decision_reason = []
            if was_emergency:
                decision_reason.append("Emergency priority")
            if starvation_used:
                decision_reason.append("Starvation prevention")
            if prediction_adjustment:
                decision_reason.append(f"Prediction {prediction_adjustment:+d}s")
            if not decision_reason:
                decision_reason.append("Demand-based" if mode == "adaptive" else "Fixed-time cycle")
            dashboard_events.append({
                "time_s": round(now, 1),
                "approach": current_approach,
                "green_s": green_seconds,
                "demand": round(demand, 2),
                "reason": ", ".join(decision_reason),
            })
            update_dashboard({
                "status": f"Running {mode} controller",
                "controller": mode,
                "source": source,
                "time_s": round(now, 1),
                "step": step_count,
                "vehicles_passed": arrived_count,
                "vehicles_departed": departed_count,
                "vehicles_in_network": len(conn.vehicle.getIDList()),
                "decision_count": adaptive_decisions if mode == "adaptive" else len(green_log) + 1,
                "predicted_count": predicted_count,
                "predicted_level": predicted_level,
                "phase": "green",
                "active_direction": current_approach,
                "green_remaining": green_seconds,
                "directions": direction_metrics,
                "events": dashboard_events[-100:],
                "history": dashboard_history[-180:],
            })

            green_log.append({
                "time_s": round(now, 1),
                "approach": current_approach,
                "green_s": green_seconds,
                "approach_demand": round(demand, 2),
                "predicted_count": (
                    predicted_count if mode == "adaptive" else ""
                ),
                "predicted_level": (
                    predicted_level if mode == "adaptive" else ""
                ),
                "prediction_adjustment_s": (
                    prediction_adjustment if mode == "adaptive" else ""
                ),
                "emergency_present": int(
                    current_approach in emergency_approaches
                ),
                "emergency_priority_used": int(was_emergency),
                "starvation_prevention_used": int(starvation_used),
                "source": source,
            })

            conn.trafficlight.setRedYellowGreenState(
                groups.tls_id,
                make_state(groups, current_approach, "G"),
            )
            phase = "green"
            phase_remaining = green_seconds

        return {
            "controller": mode,
            "source": source,
            "simulation_seconds": round(conn.simulation.getTime(), 1),
            "steps": step_count,
            "vehicles_departed": departed_count,
            "vehicles_arrived": arrived_count,
            "unfinished_expected": conn.simulation.getMinExpectedNumber(),
            "avg_inbound_queue_vehicles": round(
                total_halting_per_step / max(step_count, 1), 3
            ),
            "estimated_stopped_vehicle_steps_per_arrival": round(
                stopped_vehicle_steps / max(arrived_count, 1), 3
            ),
            "adaptive_green_decisions": adaptive_decisions,
            "emergency_priority_decisions": emergency_priority_decisions,
            "starvation_prevention_decisions": starvation_preventions,
            "green_log": green_log,
        }

    finally:
        conn.close()


def write_outputs(results):
    if not results:
        print("No results to write.")
        return

    metrics_path = HERE / "comparison_results.csv"
    metric_fields = [
        key for key in results[0] if key != "green_log"
    ]

    with metrics_path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=metric_fields)
        writer.writeheader()
        for result in results:
            writer.writerow({
                key: result[key] for key in metric_fields
            })

    log_path = HERE / "green_decisions.csv"
    fields = [
        "controller",
        "source",
        "time_s",
        "approach",
        "green_s",
        "approach_demand",
        "predicted_count",
        "predicted_level",
        "prediction_adjustment_s",
        "emergency_present",
        "emergency_priority_used",
        "starvation_prevention_used",
    ]

    with log_path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for result in results:
            for item in result["green_log"]:
                writer.writerow({
                    "controller": result["controller"],
                    **item,
                })

    print(f"\nMetrics saved to: {metrics_path}")
    print(f"Green decisions saved to: {log_path}")


def choose_source():
    """Show the startup menu and return the selected input source."""
    print("\n" + "=" * 48)
    print(" AI ADAPTIVE SMART TRAFFIC MANAGEMENT")
    print("=" * 48)
    print("Choose traffic input mode:\n")
    print("A) SUMO Simulation")
    print("B) Camera Video Replay")
    print("=" * 48)

    while True:
        choice = input("Enter your choice (A/B): ").strip().upper()

        if choice == "A":
            print("\nSelected: SUMO Simulation")
            return "sumo"

        if choice == "B":
            print("\nSelected: Camera Video Replay")
            return "camera"

        print("Invalid choice. Please enter A or B.")


def prepare_camera_data():
    """Run the detection and CSV preparation scripts for camera mode."""
    member1_dir = ROOT / "member1_vehicle_detection"
    detection_script = member1_dir / "camera_traffic_pipeline.py"
    preparation_script = member1_dir / "prepare_traffic_state.py"

    for script in (detection_script, preparation_script):
        if not script.is_file():
            raise FileNotFoundError(f"Required script not found: {script}")

    print("\nStep 1/2: Processing the four camera videos...")
    subprocess.run(
        [sys.executable, str(detection_script)],
        cwd=str(ROOT),
        check=True,
    )

    print("\nStep 2/2: Preparing traffic-state CSV...")
    subprocess.run(
        [sys.executable, str(preparation_script)],
        cwd=str(ROOT),
        check=True,
    )

    camera_csv = (
        member1_dir / "output" / "traffic_state_by_timestamp.csv"
    )

    if not camera_csv.is_file():
        raise FileNotFoundError(
            f"Prepared camera CSV was not created: {camera_csv}"
        )

    return camera_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-cap", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Show the SUMO GUI",
    )
    args = parser.parse_args()

    dashboard_url = start_dashboard(open_browser=True)
    print(f"Live dashboard: {dashboard_url}")
    update_dashboard({"status": "Dashboard open — waiting for input selection"})

    source = choose_source()
    camera_csv = prepare_camera_data() if source == "camera" else None

    net_file, route_file = build_network()
    results = []

    for mode in ("fixed", "adaptive"):
        print(
            f"\nRunning {mode.upper()} controller "
            f"with source={source}..."
        )

        result = run_one(
            mode,
            net_file,
            route_file,
            duration_cap=args.duration_cap,
            gui=args.gui,
            source=source,
            camera_csv=camera_csv,
            seed=args.seed,
        )
        results.append(result)

        for key, value in result.items():
            if key != "green_log":
                print(f"  {key}: {value}")

    write_outputs(results)
    update_dashboard({"status": "Run completed", "controller": "Comparison complete"})

    print("\nRun completed.")
    print(f"Input mode: {source.upper()}")
    print("Validate timing, emergency labels and signal safety.")
    print("Camera mode replays recorded data in SUMO; it does not")
    print("directly control real-world traffic signals.")


if __name__ == "__main__":
    main()
