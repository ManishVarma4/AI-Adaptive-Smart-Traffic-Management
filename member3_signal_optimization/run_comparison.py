"""Run identical four-way traffic demand with fixed-time and adaptive signal timing."""
from __future__ import annotations
import argparse
import csv
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def configure_sumo_python() -> None:
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
        "Cannot import TraCI. Install SUMO, set SUMO_HOME, and ensure SUMO_HOME/tools is on PYTHONPATH."
    ) from exc

from build_network import build_network, find_sumo_binary
from signal_controller import adaptive_green_seconds, axis_demand, discover_signal_groups, make_state
from member2_density_estimation.density_module import get_lane_density_report

INBOUND_EDGES = {"inN", "inS", "inE", "inW"}


def run_one(mode: str, net_file: Path, route_file: Path, duration_cap: int = 1250) -> dict:
    sumo = find_sumo_binary("sumo")
    cmd = [sumo, "-n", str(net_file), "-r", str(route_file),
           "--no-step-log", "true", "--duration-log.disable", "true",
           "--time-to-teleport", "-1", "--waiting-time-memory", "1000", "--seed", "42"]
    label = f"member3_{mode}"
    traci.start(cmd, label=label)
    conn = traci.getConnection(label)
    try:
        groups = discover_signal_groups(conn)
        current_axis = "NS"
        green_seconds = 30 if mode == "fixed" else 20
        yellow_seconds, all_red_seconds = 3, 1
        phase, phase_remaining = "green", green_seconds
        conn.trafficlight.setRedYellowGreenState(groups.tls_id, make_state(groups, current_axis, "G"))

        step_count = total_halting_per_step = total_waiting_vehicle_seconds = 0
        arrived_count = departed_count = adaptive_decisions = 0
        green_log = []

        while conn.simulation.getMinExpectedNumber() > 0 and step_count < duration_cap:
            conn.simulationStep()
            step_count += 1
            now = conn.simulation.getTime()
            # Member 2's reusable module is the source of live lane density data.
            report = get_lane_density_report(conn)
            inbound = [lane for lane in report if lane.rsplit("_", 1)[0] in INBOUND_EDGES]
            total_halting_per_step += sum(int(report[lane]["halting"]) for lane in inbound)
            vehicle_ids = conn.vehicle.getIDList()
            total_waiting_vehicle_seconds += sum(
                1 for vehicle_id in vehicle_ids if conn.vehicle.getSpeed(vehicle_id) < 0.1
            )
            arrived_count += len(conn.simulation.getArrivedIDList())
            departed_count += len(conn.simulation.getDepartedIDList())

            phase_remaining -= 1
            if phase_remaining > 0:
                continue

            if phase == "green":
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id, make_state(groups, current_axis, "y")
                )
                phase, phase_remaining = "yellow", yellow_seconds
            elif phase == "yellow":
                conn.trafficlight.setRedYellowGreenState(groups.tls_id, "r" * groups.signal_count)
                phase, phase_remaining = "all_red", all_red_seconds
            else:
                # Alternate axes to guarantee service to both directions; adapt green length.
                current_axis = "EW" if current_axis == "NS" else "NS"
                report = get_lane_density_report(conn)
                if mode == "fixed":
                    green_seconds = 30
                else:
                    green_seconds = adaptive_green_seconds(axis_demand(report, current_axis))
                    adaptive_decisions += 1
                green_log.append({
                    "time_s": round(now, 1), "axis": current_axis, "green_s": green_seconds,
                    "ns_demand": round(axis_demand(report, "NS"), 2),
                    "ew_demand": round(axis_demand(report, "EW"), 2),
                })
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id, make_state(groups, current_axis, "G")
                )
                phase, phase_remaining = "green", green_seconds

        unfinished = conn.simulation.getMinExpectedNumber()
        avg_queue = total_halting_per_step / max(step_count, 1)
        avg_wait = total_waiting_vehicle_seconds / max(arrived_count, 1)
        return {
            "controller": mode,
            "simulation_seconds": round(conn.simulation.getTime(), 1),
            "steps": step_count,
            "vehicles_departed": departed_count,
            "vehicles_arrived": arrived_count,
            "unfinished_expected": unfinished,
            "avg_inbound_queue_vehicles": round(avg_queue, 3),
            "estimated_waiting_seconds_per_arrived_vehicle": round(avg_wait, 3),
            "adaptive_green_decisions": adaptive_decisions,
            "green_log": green_log,
        }
    finally:
        conn.close()


def write_outputs(results: list[dict]) -> None:
    metrics_path = HERE / "comparison_results.csv"
    keys = [key for key in results[0] if key != "green_log"]
    with metrics_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        for result in results:
            writer.writerow({key: result[key] for key in keys})

    log_path = HERE / "green_decisions.csv"
    fields = ["controller", "time_s", "axis", "green_s", "ns_demand", "ew_demand"]
    with log_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for item in result["green_log"]:
                writer.writerow({"controller": result["controller"], **item})
    print(f"\nMetrics saved to: {metrics_path}")
    print(f"Green decisions saved to: {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-cap", type=int, default=1250,
                        help="Safety cap in simulation seconds (default: 1250)")
    args = parser.parse_args()
    net_file, route_file = build_network()
    results = []
    for mode in ("fixed", "adaptive"):
        print(f"\nRunning {mode.upper()} controller on identical demand...")
        result = run_one(mode, net_file, route_file, args.duration_cap)
        results.append(result)
        for key, value in result.items():
            if key != "green_log":
                print(f"  {key}: {value}")
    write_outputs(results)
    print("\nCompare queue and waiting metrics (lower is better) and vehicles_arrived (higher is better).")
    print("Results are experimental; do not claim improvement until the generated CSVs confirm it.")


if __name__ == "__main__":
    main()
