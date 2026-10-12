"""Member 3: fair, density-aware signal timing for a four-way SUMO junction."""
from dataclasses import dataclass

NS_EDGES = {"inN", "inS"}
EW_EDGES = {"inE", "inW"}


@dataclass
class SignalGroups:
    tls_id: str
    ns_indices: list[int]
    ew_indices: list[int]
    signal_count: int


def discover_signal_groups(traci) -> SignalGroups:
    """Discover signal-link indices dynamically; do not hard-code SUMO link order."""
    tls_ids = traci.trafficlight.getIDList()
    if not tls_ids:
        raise RuntimeError("No traffic-light logic found. Check that central node J is signalized.")
    tls_id = "J" if "J" in tls_ids else tls_ids[0]
    controlled = traci.trafficlight.getControlledLinks(tls_id)
    ns, ew = [], []
    for signal_index, link_group in enumerate(controlled):
        incoming_edges = set()
        for link in link_group:
            if not link:
                continue
            incoming_lane = link[0]
            try:
                incoming_edges.add(traci.lane.getEdgeID(incoming_lane))
            except Exception:
                incoming_edges.add(incoming_lane.rsplit("_", 1)[0])
        if incoming_edges & NS_EDGES:
            ns.append(signal_index)
        elif incoming_edges & EW_EDGES:
            ew.append(signal_index)
    if not ns or not ew:
        raise RuntimeError(f"Unable to map TLS links to approaches: NS={ns}, EW={ew}, TLS={tls_id}")
    return SignalGroups(tls_id, ns, ew, len(controlled))


def make_state(groups: SignalGroups, active_axis: str, color: str = "G") -> str:
    state = ["r"] * groups.signal_count
    active = groups.ns_indices if active_axis == "NS" else groups.ew_indices
    for idx in active:
        state[idx] = color
    return "".join(state)


def axis_demand(report: dict, axis: str) -> float:
    """Weight stopped vehicles more heavily than moving vehicles."""
    edge_set = NS_EDGES if axis == "NS" else EW_EDGES
    total = 0.0
    for lane_id, data in report.items():
        edge_id = lane_id.rsplit("_", 1)[0]
        if edge_id not in edge_set:
            continue
        vehicles = int(data.get("vehicles", 0))
        halting = int(data.get("halting", 0))
        density = data.get("density", "LOW")
        bonus = {"EMPTY": 0, "LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(density, 0)
        total += vehicles + 2.0 * halting + bonus
    return total



def adaptive_green_seconds(
    demand: float,
    minimum: int = 10,
    maximum: int = 40
) -> int:
    """Map demand to green duration with diminishing returns."""
    import math

    demand = max(0.0, demand)

    # Green time grows smoothly instead of hitting 40 seconds too quickly.
    green = minimum + (maximum - minimum) * (
        demand / (demand + 40.0)
    )

    return max(minimum, min(maximum, int(round(green))))
