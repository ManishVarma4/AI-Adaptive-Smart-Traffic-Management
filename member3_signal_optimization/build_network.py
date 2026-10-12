"""Build a four-arm, signalized SUMO intersection and traffic demand."""
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
    # Both controllers use this exact demand and random seed.
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<routes>
    <vType id="car" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="13.89" speedFactor="1.0"/>
    <route id="r_N_S" edges="inN outS"/>
    <route id="r_S_N" edges="inS outN"/>
    <route id="r_E_W" edges="inE outW"/>
    <route id="r_W_E" edges="inW outE"/>
    <!-- First interval: north/south demand is higher. -->
    <flow id="NS_N_1" type="car" route="r_N_S" begin="0" end="300" vehsPerHour="720" departLane="best" departSpeed="max"/>
    <flow id="NS_S_1" type="car" route="r_S_N" begin="0" end="300" vehsPerHour="720" departLane="best" departSpeed="max"/>
    <flow id="EW_E_1" type="car" route="r_E_W" begin="0" end="300" vehsPerHour="300" departLane="best" departSpeed="max"/>
    <flow id="EW_W_1" type="car" route="r_W_E" begin="0" end="300" vehsPerHour="300" departLane="best" departSpeed="max"/>
    <!-- Second interval: east/west demand is higher. -->
    <flow id="NS_N_2" type="car" route="r_N_S" begin="300" end="600" vehsPerHour="300" departLane="best" departSpeed="max"/>
    <flow id="NS_S_2" type="car" route="r_S_N" begin="300" end="600" vehsPerHour="300" departLane="best" departSpeed="max"/>
    <flow id="EW_E_2" type="car" route="r_E_W" begin="300" end="600" vehsPerHour="720" departLane="best" departSpeed="max"/>
    <flow id="EW_W_2" type="car" route="r_W_E" begin="300" end="600" vehsPerHour="720" departLane="best" departSpeed="max"/>
    <!-- Third interval returns to north/south-heavy demand. -->
    <flow id="NS_N_3" type="car" route="r_N_S" begin="600" end="900" vehsPerHour="600" departLane="best" departSpeed="max"/>
    <flow id="NS_S_3" type="car" route="r_S_N" begin="600" end="900" vehsPerHour="600" departLane="best" departSpeed="max"/>
    <flow id="EW_E_3" type="car" route="r_E_W" begin="600" end="900" vehsPerHour="360" departLane="best" departSpeed="max"/>
    <flow id="EW_W_3" type="car" route="r_W_E" begin="600" end="900" vehsPerHour="360" departLane="best" departSpeed="max"/>
</routes>
'''
    path.write_text(xml, encoding="utf-8")


def build_network():
    netconvert = find_sumo_binary("netconvert")
    net = HERE / "four_way.net.xml"
    routes = HERE / "traffic_demand.rou.xml"
    command = [netconvert, "--node-files", str(HERE / "nodes.nod.xml"),
               "--edge-files", str(HERE / "edges.edg.xml"), "--output-file", str(net),
               "--no-turnarounds", "true", "--junctions.corner-detail", "5",
               "--geometry.remove", "true", "--tls.guess", "false"]
    print("Building four-way signalized intersection...")
    subprocess.run(command, check=True)
    write_routes(routes)
    print(f"Network: {net}\nDemand:  {routes}")
    return net, routes


if __name__ == "__main__":
    build_network()
