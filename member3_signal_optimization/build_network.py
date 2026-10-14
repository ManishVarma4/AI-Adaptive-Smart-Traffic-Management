"""Build a four-arm SUMO intersection with turning demand and emergency vehicles."""
from pathlib import Path
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def find_sumo_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    home = os.environ.get("SUMO_HOME")
    if home:
        for candidate in (Path(home) / "bin" / name, Path(home) / "bin" / f"{name}.exe"):
            if candidate.exists():
                return str(candidate)
    raise FileNotFoundError(
        f"Could not find {name}. Install SUMO and add its bin folder to PATH, or set SUMO_HOME."
    )



def write_routes(path: Path) -> None:
    """Write identical demand for both controllers, including emergency vehicles."""
    approaches = {
        "N": {"right": "inN outW", "straight": "inN outS", "left": "inN outE"},
        "S": {"right": "inS outE", "straight": "inS outN", "left": "inS outW"},
        "E": {"right": "inE outN", "straight": "inE outW", "left": "inE outS"},
        "W": {"right": "inW outS", "straight": "inW outE", "left": "inW outN"},
    }

    intervals = [
        (0, 300, {"N": 720, "S": 720, "E": 300, "W": 300}),
        (300, 600, {"N": 300, "S": 300, "E": 720, "W": 720}),
        (600, 900, {"N": 600, "S": 600, "E": 360, "W": 360}),
    ]

    shares = {"straight": 0.60, "left": 0.20, "right": 0.20}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<routes>",
        '    <vType id="car" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="13.89" speedFactor="1.0"/>',
        '    <vType id="emergency" vClass="emergency" accel="3.0" decel="6.0" sigma="0.2" length="5.5" minGap="2.5" maxSpeed="16.67" speedFactor="1.0"/>',
    ]

    # Define all routes before vehicles and flows.
    for approach, movements in approaches.items():
        for movement, edges in movements.items():
            lines.append(f'    <route id="r_{approach}_{movement}" edges="{edges}"/>')

    # Sort traffic flows and emergency vehicles by their start/departure time.
    # This prevents emergency vehicles from appearing after later-starting flows.
    events = []

    for interval_index, (begin, end, rates) in enumerate(intervals, start=1):
        flow_lines = [
            f'    <flow id="flow_{approach}_{movement}_{interval_index}" type="car" '
            f'route="r_{approach}_{movement}" begin="{begin}" end="{end}" '
            f'vehsPerHour="{round(total_rate * share)}" '
            f'departLane="best" departSpeed="max"/>'
            for approach, total_rate in rates.items()
            for movement, share in shares.items()
        ]

        events.append((begin, 0, flow_lines))

    emergency_vehicles = [
        (80, '    <vehicle id="ambulance_N_1" type="emergency" route="r_N_straight" depart="80" departLane="best" departSpeed="max"/>'),
        (390, '    <vehicle id="firetruck_E_1" type="emergency" route="r_E_straight" depart="390" departLane="best" departSpeed="max"/>'),
        (680, '    <vehicle id="ambulance_W_1" type="emergency" route="r_W_right" depart="680" departLane="best" departSpeed="max"/>'),
    ]

    for depart, vehicle_line in emergency_vehicles:
        events.append((depart, 1, [vehicle_line]))

    for event_time, _, event_lines in sorted(events, key=lambda event: (event[0], event[1])):
        lines.append(f"    <!-- Traffic event at {event_time}s -->")
        lines.extend(event_lines)

    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def build_network():
    netconvert = find_sumo_binary("netconvert")
    net = HERE / "four_way.net.xml"
    routes = HERE / "traffic_demand.rou.xml"
    command = [
        netconvert,
        "--node-files", str(HERE / "nodes.nod.xml"),
        "--edge-files", str(HERE / "edges.edg.xml"),
        "--output-file", str(net),
        "--no-turnarounds", "true",
        "--junctions.corner-detail", "5",
        "--geometry.remove", "true",
        "--tls.guess", "false",
    ]
    print("Building four-way signalized intersection...")
    subprocess.run(command, check=True)
    write_routes(routes)
    print(f"Network: {net}\nDemand:  {routes}")
    return net, routes


if __name__ == "__main__":
    build_network()
