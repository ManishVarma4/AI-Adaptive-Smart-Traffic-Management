"""Demand scoring and fair approach selection for the SUMO signal controller."""
from dataclasses import dataclass

APPROACH_EDGES = {"N": "inN", "S": "inS", "E": "inE", "W": "inW"}
APPROACH_ORDER = ("N", "S", "E", "W")


@dataclass
class SignalGroups:
    tls_id: str
    approach_indices: dict[str, list[int]]
    signal_count: int


def discover_signal_groups(traci) -> SignalGroups:
    """Map SUMO traffic-light links to incoming approaches."""
    tls_ids = traci.trafficlight.getIDList()
    if not tls_ids:
        raise RuntimeError("No traffic light found. Check that node J is signalized.")
    tls_id = "J" if "J" in tls_ids else tls_ids[0]
    controlled = traci.trafficlight.getControlledLinks(tls_id)
    groups = {approach: [] for approach in APPROACH_ORDER}
    for index, link_group in enumerate(controlled):
        for link in link_group:
            if not link:
                continue
            lane_id = link[0]
            try:
                edge_id = traci.lane.getEdgeID(lane_id)
            except Exception:
                edge_id = lane_id.rsplit("_", 1)[0]
            for approach, incoming_edge in APPROACH_EDGES.items():
                if edge_id == incoming_edge:
                    groups[approach].append(index)
                    break
            else:
                continue
            break
    missing = [a for a, indices in groups.items() if not indices]
    if missing:
        raise RuntimeError(f"Could not map signal links for approaches: {missing}")
    return SignalGroups(tls_id, groups, len(controlled))


def make_state(groups: SignalGroups, active_approach: str, color: str = "G") -> str:
    """Activate one approach's movements; all other approaches stay red."""
    if active_approach not in groups.approach_indices:
        raise ValueError(f"Unknown approach: {active_approach}")
    state = ["r"] * groups.signal_count
    for index in groups.approach_indices[active_approach]:
        state[index] = color
    return "".join(state)


def approach_demand(report: dict, approach: str) -> float:
    """Score queue demand: moving vehicles + extra weight for stopped vehicles."""
    edge_id = APPROACH_EDGES[approach]
    total = 0.0
    for lane_id, data in report.items():
        if lane_id.rsplit("_", 1)[0] != edge_id:
            continue
        vehicles = int(data.get("vehicles", 0))
        halting = int(data.get("halting", 0))
        density = str(data.get("density", "LOW")).upper()
        bonus = {"EMPTY": 0, "LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(density, 0)
        total += vehicles + 2.0 * halting + bonus
    return total


def adaptive_green_seconds(demand: float, minimum: int = 10, maximum: int = 40) -> int:
    """Map demand to a bounded green time."""
    demand = max(0.0, float(demand))
    green = minimum + (maximum - minimum) * demand / (demand + 25.0)
    return max(minimum, min(maximum, int(round(green))))


def choose_next_approach(
    report: dict,
    last_served: dict[str, float],
    now: float,
    emergency_approaches: set[str],
    previous_emergency_service: bool,
    max_red_wait: float = 90.0,
) -> tuple[str, bool]:
    """Choose next approach with emergency priority and starvation prevention.

    Emergency priority is served at most once consecutively if any non-emergency
    approach has reached the max-red-wait threshold. Otherwise, overdue approaches
    are served first (oldest first); remaining ties are broken by demand and stable
    N/S/E/W order.
    """
    overdue = [
        a for a in APPROACH_ORDER
        if now - last_served[a] >= max_red_wait
    ]
    if emergency_approaches and not (
        previous_emergency_service and overdue
    ):
        # If multiple emergency approaches are waiting, choose the oldest waiting one.
        selected = max(emergency_approaches, key=lambda a: (now - last_served[a], -APPROACH_ORDER.index(a)))
        return selected, True

    if overdue:
        selected = max(overdue, key=lambda a: (now - last_served[a], -APPROACH_ORDER.index(a)))
        return selected, False

    selected = max(
        APPROACH_ORDER,
        key=lambda a: (
            approach_demand(report, a),
            now - last_served[a],
            -APPROACH_ORDER.index(a),
        ),
    )
    return selected, False
