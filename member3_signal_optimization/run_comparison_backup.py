"""Compare fixed-time and emergency-aware adaptive SUMO signal control."""
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
        "Cannot import TraCI. Set SUMO_HOME and ensure SUMO_HOME/tools is available."
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

INBOUND_EDGES = set(APPROACH_EDGES.values())


def find_emergency_approaches(conn) -> set[str]:
    """Find approaches currently carrying an active emergency vehicle."""
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
            # A vehicle may be in a junction/internal edge during a step.
            continue
    return found


def run_one(mode: str, net_file: Path, route_file: Path,
            duration_cap: int = 1500, gui: bool = False) -> dict:
    sumo = find_sumo_binary("sumo-gui" if gui else "sumo")
    cmd = [
        sumo, "-n", str(net_file), "-r", str(route_file),
        "--no-step-log", "true", "--duration-log.disable", "true",
        "--time-to-teleport", "-1", "--waiting-time-memory", "1000",
        "--seed", "42",
    ]
    if gui:
        cmd.extend(["--start", "--delay", "50"])

    label = f"member3_{mode}"
    traci.start(cmd, label=label)
    conn = traci.getConnection(label)
    try:
        groups = discover_signal_groups(conn)
        current_approach = "N"
        green_seconds = 30 if mode == "fixed" else 20
        yellow_seconds, all_red_seconds = 3, 1
        phase, phase_remaining = "green", green_seconds
        conn.trafficlight.setRedYellowGreenState(
            groups.tls_id, make_state(groups, current_approach, "G")
        )

        now = conn.simulation.getTime()
        last_served = {a: now for a in APPROACH_ORDER}
        last_served[current_approach] = now
        step_count = total_halting_per_step = stopped_vehicle_steps = 0
        arrived_count = departed_count = adaptive_decisions = 0
        emergency_priority_decisions = starvation_preventions = 0
        previous_was_emergency = False
        green_log = []

        while conn.simulation.getMinExpectedNumber() > 0 and step_count < duration_cap:
            conn.simulationStep()
            step_count += 1
            now = conn.simulation.getTime()
            report = get_lane_density_report(conn)
            inbound = [lane for lane in report if lane.rsplit("_", 1)[0] in INBOUND_EDGES]
            total_halting_per_step += sum(int(report[lane]["halting"]) for lane in inbound)
            vehicle_ids = conn.vehicle.getIDList()
            stopped_vehicle_steps += sum(
                1 for vehicle_id in vehicle_ids
                if conn.vehicle.getSpeed(vehicle_id) < 0.1
            )
            arrived_count += len(conn.simulation.getArrivedIDList())
            departed_count += len(conn.simulation.getDepartedIDList())

            phase_remaining -= 1
            if phase_remaining > 0:
                continue

            if phase == "green":
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id, make_state(groups, current_approach, "y")
                )
                phase, phase_remaining = "yellow", yellow_seconds
            elif phase == "yellow":
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id, "r" * groups.signal_count
                )
                phase, phase_remaining = "all_red", all_red_seconds
            else:
                report = get_lane_density_report(conn)
                emergency_approaches = find_emergency_approaches(conn)
                starvation_used = False
                if mode == "fixed":
                    # Fixed baseline stays cyclic and ignores emergency priority.
                    current_approach = APPROACH_ORDER[
                        (APPROACH_ORDER.index(current_approach) + 1) % len(APPROACH_ORDER)
                    ]
                    green_seconds = 30
                    was_emergency = False
                else:
                    overdue_before = {
                        a for a in APPROACH_ORDER
                        if now - last_served[a] >= 90.0
                    }
                    current_approach, was_emergency = choose_next_approach(
                        report, last_served, now, emergency_approaches,
                        previous_was_emergency, max_red_wait=90.0,
                    )
                    starvation_used = current_approach in overdue_before and not was_emergency
                    if was_emergency:
                        emergency_priority_decisions += 1
                    if starvation_used:
                        starvation_preventions += 1
                    green_seconds = adaptive_green_seconds(approach_demand(report, current_approach))
                    adaptive_decisions += 1
                previous_was_emergency = was_emergency
                last_served[current_approach] = now
                demand = approach_demand(report, current_approach)
                green_log.append({
                    "time_s": round(now, 1),
                    "approach": current_approach,
                    "green_s": green_seconds,
                    "approach_demand": round(demand, 2),
                    "emergency_present": int(current_approach in emergency_approaches),
                    "emergency_priority_used": int(was_emergency),
                    "starvation_prevention_used": int(starvation_used),
                })
                conn.trafficlight.setRedYellowGreenState(
                    groups.tls_id, make_state(groups, current_approach, "G")
                )
                phase, phase_remaining = "green", green_seconds

        unfinished = conn.simulation.getMinExpectedNumber()
        return {
            "controller": mode,
            "simulation_seconds": round(conn.simulation.getTime(), 1),
            "steps": step_count,
            "vehicles_departed": departed_count,
            "vehicles_arrived": arrived_count,
            "unfinished_expected": unfinished,
            "avg_inbound_queue_vehicles": round(total_halting_per_step / max(step_count, 1), 3),
            "estimated_stopped_vehicle_steps_per_arrival": round(stopped_vehicle_steps / max(arrived_count, 1), 3),
            "adaptive_green_decisions": adaptive_decisions,
            "emergency_priority_decisions": emergency_priority_decisions,
            "starvation_prevention_decisions": starvation_preventions,
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
    fields = [
        "controller", "time_s", "approach", "green_s", "approach_demand",
        "emergency_present", "emergency_priority_used", "starvation_prevention_used",
    ]
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
    parser.add_argument("--duration-cap", type=int, default=1500)
    parser.add_argument("--gui", action="store_true", help="Show SUMO GUI")
    args = parser.parse_args()
    net_file, route_file = build_network()
    results = []
    for mode in ("fixed", "adaptive"):
        print(f"\nRunning {mode.upper()} controller...")
        result = run_one(mode, net_file, route_file, args.duration_cap, gui=args.gui)
        results.append(result)
        for key, value in result.items():
            if key != "green_log":
                print(f"  {key}: {value}")
    write_outputs(results)
    print("\nAdaptive mode uses emergency priority plus a 90-second red-wait threshold.")
    print("Validate signal safety and repeat runs before making performance claims.")


if __name__ == "__main__":
    main()
