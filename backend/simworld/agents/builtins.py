"""Built-in deterministic agents.

These are real strategies over the same observation/action interface external
agents use. They are deliberately independent of each other so comparisons mean
something.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from .base import AgentContext, Decision


def _bfs(
    adjacency: dict[str, list[str]], start: str, goal: str, blocked: set[str]
) -> list[str] | None:
    if start == goal:
        return [start]
    seen = {start}
    queue: deque[list[str]] = deque([[start]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for neighbour in adjacency.get(node, []):
            if neighbour in seen:
                continue
            key = "|".join(sorted((node, neighbour), key=lambda n: tuple(int(v) for v in n.split(","))))
            if key in blocked:
                continue
            if neighbour == goal:
                return path + [neighbour]
            seen.add(neighbour)
            queue.append(path + [neighbour])
    return None


def _hops(
    adjacency: dict[str, list[str]], start: str, goal: str, blocked: set[str]
) -> int | None:
    path = _bfs(adjacency, start, goal, blocked)
    return None if path is None else len(path) - 1


def _wait() -> Decision:
    return Decision(action={"type": "wait"}, reasoning="No productive action available.")


class CityBaselineAgent:
    """Deadline-, fuel-, and disruption-aware dispatcher."""

    id = "city-baseline"
    label = "Disruption-Aware Dispatcher"
    kind = "builtin"
    environments = ["city_logistics"]

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        vehicle = observation["vehicle"]
        node = vehicle["node"]
        cargo: list[str] = [c["id"] for c in vehicle["cargo"]]
        packages = {p["id"]: p for p in observation["packages"]}
        stations = {s["node"]: float(s["stock_l"]) for s in observation["stations"]}
        adjacency = observation["adjacency"]
        blocked = set(observation["closed_edges"])
        step_minutes = observation["step_minutes"]
        now = observation["time_min"]
        fuel = float(vehicle["fuel_l"])
        capacity = int(vehicle["capacity"])
        consumption = float(vehicle["consumption_l_per_km"])
        edge_km = float(observation["edge_km"])
        depot = observation["depot"]

        def path(a: str, b: str, avoid: set[str] | None = None) -> list[str] | None:
            return _bfs(adjacency, a, b, blocked if avoid is None else avoid)

        # 1. Deliver immediately when standing on a package destination.
        ready = [pid for pid in cargo if packages[pid]["dest"] == node]
        if ready:
            ready.sort(key=lambda pid: packages[pid]["deadline_min"])
            target = packages[ready[0]]
            return Decision(
                action={"type": "deliver", "package_id": ready[0]},
                reasoning=f"At {target['dest_label']}; deliver {ready[0]} due at "
                f"t+{max(0, target['deadline_min'] - now)} min.",
            )

        def load_batch(available: list[dict[str, Any]], slots: int) -> list[str]:
            if slots <= 0 or not available:
                return []
            remaining = list(available)

            def dist_to(pkg: dict[str, Any], origin: str) -> int:
                hops = _hops(adjacency, origin, pkg["dest"], blocked)
                return hops if hops is not None else 999

            first = min(remaining, key=lambda p: (p["deadline_min"], dist_to(p, depot)))
            batch = [first["id"]]
            remaining = [p for p in remaining if p["id"] != first["id"]]
            last = first["dest"]
            while remaining and len(batch) < slots:
                nxt = min(
                    remaining,
                    key=lambda p: (dist_to(p, last), p["deadline_min"]),
                )
                batch.append(nxt["id"])
                remaining = [p for p in remaining if p["id"] != nxt["id"]]
                last = nxt["dest"]
            return sorted(batch)

        # 2. Refuel when idle at a station and tanks are low.
        if node in stations and stations[node] > 0.01 and fuel < vehicle["fuel_capacity_l"] * 0.5:
            if any(pid for pid in cargo) or time_to_spare(observation):
                return Decision(
                    action={"type": "refuel", "amount": 5.0},
                    reasoning=f"Fuel at {fuel:.2f} L; topping up at station {node}.",
                )

        targets = [packages[pid] for pid in cargo]
        if not targets:
            available = [p for p in packages.values() if p["status"] == "at_depot"]
            if not available:
                return _wait()
            if node == depot:
                batch = load_batch(available, capacity - len(cargo))
                if batch:
                    return Decision(
                        action={"type": "pickup", "package_ids": batch},
                        reasoning=f"Load {', '.join(batch)} for the next delivery loop.",
                    )
            to_depot = path(node, depot)
            if to_depot and len(to_depot) > 1:
                return Decision(
                    action={"type": "move", "target": to_depot[1]},
                    reasoning="No cargo; returning to the depot for the next batch.",
                )
            return _wait()

        scored = []
        for pkg in targets:
            route = path(node, pkg["dest"])
            if route is None:
                continue
            # Earliest-deadline-first, with distance only as a tie-breaker.
            # Using position-dependent slack here makes the target oscillate
            # between two drops as the van moves.
            scored.append((pkg["deadline_min"], len(route), pkg["id"], route))
        if not scored:
            return _wait()
        scored.sort()
        _, _, target_id, route = scored[0]
        target = packages[target_id]
        required_fuel = max(0, len(route) - 1) * edge_km * consumption

        # 3. Fuel routing: only divert when the current plan does not fit.
        if fuel < required_fuel + 0.55:
            if node in stations and stations[node] > 0.01:
                return Decision(
                    action={"type": "refuel", "amount": 5.0},
                    reasoning=(
                        f"Next leg needs {required_fuel:.2f} L but the tank holds {fuel:.2f} L. "
                        f"Refuelling at {node} first."
                    ),
                )
            options = []
            for station, stock in stations.items():
                if stock <= 0.01:
                    continue
                station_route = path(node, station)
                if station_route is None:
                    continue
                cost = max(0, len(station_route) - 1) * edge_km * consumption
                if fuel >= cost + 0.25:
                    options.append((len(station_route), station, station_route))
            if options:
                options.sort()
                _, station, station_route = options[0]
                return Decision(
                    action={"type": "move", "target": station_route[1]},
                    reasoning=(
                        f"Low fuel ({fuel:.2f} L). Diverting to station {station} before "
                        f"delivering {target_id}."
                    ),
                )

        if len(route) > 1:
            next_node = route[1]
            return Decision(
                action={"type": "move", "target": next_node},
                reasoning=(
                    f"Route to {target['dest_label']} for {target_id} "
                    f"({len(route) - 1} hops, slack {target['deadline_min'] - now} min)."
                ),
            )
        return _wait()


def time_to_spare(observation: dict[str, Any]) -> bool:
    return observation["step"] < observation["horizon_steps"] * 0.55


class CityGreedyAgent(CityBaselineAgent):
    """Nearest-delivery batching with live closures, but no deadline planning."""

    id = "city-greedy"
    label = "Greedy Nearest Delivery"
    kind = "builtin"
    environments = ["city_logistics"]

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        vehicle = observation["vehicle"]
        node = vehicle["node"]
        cargo: list[str] = [c["id"] for c in vehicle["cargo"]]
        packages = {p["id"]: p for p in observation["packages"]}
        adjacency = observation["adjacency"]
        blocked = set(observation["closed_edges"])
        depot = observation["depot"]
        capacity = int(vehicle["capacity"])

        ready = [pid for pid in cargo if packages[pid]["dest"] == node]
        if ready:
            return Decision(
                action={"type": "deliver", "package_id": ready[0]},
                reasoning="Standing on a drop-off; deliver the first package in the van.",
            )

        if not cargo:
            available = [p for p in packages.values() if p["status"] == "at_depot"]
            if not available:
                return _wait()
            if node != depot:
                route = _bfs(adjacency, node, depot, blocked)
                if route and len(route) > 1:
                    return Decision(
                        action={"type": "move", "target": route[1]},
                        reasoning="Empty van; head back to the depot.",
                    )
                return _wait()
            ranked = sorted(
                available,
                key=lambda p: (_hops(adjacency, depot, p["dest"], blocked) or 999, p["id"]),
            )
            batch = sorted(p["id"] for p in ranked[:capacity])
            return Decision(
                action={"type": "pickup", "package_ids": batch},
                reasoning="Load the nearest drops to the depot.",
            )

        stations = {s["node"]: float(s["stock_l"]) for s in observation["stations"]}
        if (
            node in stations
            and stations[node] > 0.01
            and vehicle["fuel_l"] < vehicle["fuel_capacity_l"] * 0.55
        ):
            return Decision(
                action={"type": "refuel", "amount": 5.0},
                reasoning="Passing a station below 55% fuel; top up while here.",
            )

        ranked = []
        for pid in cargo:
            pkg = packages[pid]
            hops = _hops(adjacency, node, pkg["dest"], blocked)
            if hops is not None:
                ranked.append((hops, pid, pkg))
        if not ranked:
            return _wait()
        ranked.sort()
        _, _, pkg = ranked[0]
        route = _bfs(adjacency, node, pkg["dest"], blocked)
        if route and len(route) > 1:
            consumption = float(vehicle["consumption_l_per_km"])
            edge_km = float(observation["edge_km"])
            required = (len(route) - 1) * edge_km * consumption
            if vehicle["fuel_l"] < required + 0.45:
                if node in stations and stations[node] > 0.01:
                    return Decision(
                        action={"type": "refuel", "amount": 5.0},
                        reasoning="Next leg exceeds the remaining fuel; refuel here.",
                    )
                options = []
                for station, stock in stations.items():
                    if stock <= 0.01:
                        continue
                    station_route = _bfs(adjacency, node, station, blocked)
                    if station_route is None:
                        continue
                    cost = max(0, len(station_route) - 1) * edge_km * consumption
                    if vehicle["fuel_l"] >= cost + 0.2:
                        options.append((len(station_route), station, station_route))
                if options:
                    options.sort()
                    _, station, station_route = options[0]
                    return Decision(
                        action={"type": "move", "target": station_route[1]},
                        reasoning=f"Fuel low; detour to station {station}.",
                    )
            return Decision(
                action={"type": "move", "target": route[1]},
                reasoning=f"Nearest drop is {pkg['dest_label']} ({len(route) - 1} hops).",
            )
        return _wait()


class CityBlindAgent:
    """Static shortest-path baseline that ignores closures and fuel state."""

    id = "city-blind"
    label = "Static Shortest Path (blind)"
    kind = "builtin"
    environments = ["city_logistics"]

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        vehicle = observation["vehicle"]
        node = vehicle["node"]
        cargo = [c["id"] for c in vehicle["cargo"]]
        packages = {p["id"]: p for p in observation["packages"]}
        adjacency = observation["adjacency"]
        depot = observation["depot"]
        capacity = int(vehicle["capacity"])

        ready = [pid for pid in cargo if packages[pid]["dest"] == node]
        if ready:
            return Decision(
                action={"type": "deliver", "package_id": ready[0]},
                reasoning="Deliver at current node.",
            )

        if not cargo:
            available = [p for p in packages.values() if p["status"] == "at_depot"]
            if not available:
                return _wait()
            if node != depot:
                route = _bfs(adjacency, node, depot, set())
                if route and len(route) > 1:
                    return Decision(
                        action={"type": "move", "target": route[1]},
                        reasoning="Return to depot on the static route.",
                    )
                return _wait()
            ranked = sorted(
                available,
                key=lambda p: (_hops(adjacency, depot, p["dest"], set()) or 999, p["id"]),
            )
            batch = sorted(p["id"] for p in ranked[:capacity])
            return Decision(
                action={"type": "pickup", "package_ids": batch},
                reasoning="Load the three closest drops (ignores deadlines).",
            )

        if cargo:
            ranked = []
            for pid in cargo:
                pkg = packages[pid]
                hops = _hops(adjacency, node, pkg["dest"], set())
                if hops is not None:
                    ranked.append((hops, pid, pkg))
            if not ranked:
                return _wait()
            ranked.sort()
            _, _, pkg = ranked[0]
            route = _bfs(adjacency, node, pkg["dest"], set())
            if route and len(route) > 1:
                return Decision(
                    action={"type": "move", "target": route[1]},
                    reasoning="Follow the cached static route; no disruption awareness.",
                )
        return _wait()


class TrafficAdaptiveAgent:
    id = "traffic-adaptive"
    label = "Adaptive Pressure Controller"
    kind = "builtin"
    environments = ["traffic_control"]

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        legal_switches = {
            (a["intersection"], a["phase"]): a
            for a in legal_actions
            if a.get("type") == "set_phase"
        }
        best: tuple[float, dict[str, Any], str] | None = None
        for item in observation["intersections"]:
            queues = item["queues"]
            ns = queues.get("N", 0) + queues.get("S", 0)
            ew = queues.get("E", 0) + queues.get("W", 0)
            if ns == ew:
                continue
            desired = "NS" if ns > ew else "EW"
            if desired == item["phase"]:
                continue
            candidate = legal_switches.get((item["id"], desired))
            if candidate is None:
                continue
            pressure = abs(ns - ew) + 0.25 * item["oldest_wait_ticks"]
            if best is None or pressure > best[0]:
                best = (pressure, candidate, desired)
        if best:
            _, action, desired = best
            return Decision(
                action=action,
                reasoning=f"Highest opposing-queue pressure; switch {action['intersection']} to {desired}.",
            )
        return Decision(action={"type": "wait"}, reasoning="All useful switches are inside minimum green.")


class TrafficFixedAgent:
    id = "traffic-fixed"
    label = "Fixed-Cycle Timer"
    kind = "builtin"
    environments = ["traffic_control"]

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        switches = [
            a for a in legal_actions if a.get("type") == "set_phase"
        ]
        by_intersection = {a["intersection"]: a for a in switches}
        for item in observation["intersections"]:
            if item["green_for_ticks"] >= 6 and item["id"] in by_intersection:
                action = by_intersection[item["id"]]
                return Decision(
                    action=action,
                    reasoning=f"Fixed cycle: {item['id']} has held {item['phase']} for 6 ticks.",
                )
        return Decision(action={"type": "wait"}, reasoning="Hold phases until the fixed interval elapses.")


BUILTIN_AGENTS: dict[str, type] = {
    "city-baseline": CityBaselineAgent,
    "city-greedy": CityGreedyAgent,
    "city-blind": CityBlindAgent,
    "traffic-adaptive": TrafficAdaptiveAgent,
    "traffic-fixed": TrafficFixedAgent,
}

AGENT_METADATA = [
    {
        "id": "city-baseline",
        "label": "Disruption-Aware Dispatcher",
        "kind": "builtin",
        "environments": ["city_logistics"],
        "description": "Deadline-aware batching, live-closure routing, and fuel planning.",
        "traits": ["deadline-aware", "reroutes on closures", "plans refuelling"],
    },
    {
        "id": "city-greedy",
        "label": "Greedy Nearest Delivery",
        "kind": "builtin",
        "environments": ["city_logistics"],
        "description": "Loads the nearest drops and always serves the closest next stop.",
        "traits": ["nearest-first", "reroutes on closures", "no deadline planning"],
    },
    {
        "id": "city-blind",
        "label": "Static Shortest Path (blind)",
        "kind": "builtin",
        "environments": ["city_logistics"],
        "description": "Cached static routes, no disruption or fuel awareness. A failure baseline.",
        "traits": ["static route", "ignores closures", "ignores fuel"],
    },
    {
        "id": "traffic-adaptive",
        "label": "Adaptive Pressure Controller",
        "kind": "builtin",
        "environments": ["traffic_control"],
        "description": "Switches the intersection with the largest opposing queue pressure.",
        "traits": ["queue-aware", "respects min green"],
    },
    {
        "id": "traffic-fixed",
        "label": "Fixed-Cycle Timer",
        "kind": "builtin",
        "environments": ["traffic_control"],
        "description": "Rotates phases on a fixed interval regardless of demand.",
        "traits": ["fixed interval", "demand-blind"],
    },
]


def default_builtin_for(kind: str) -> str:
    return "city-baseline" if kind == "city_logistics" else "traffic-adaptive"


def make_builtin(agent_id: str):
    cls = BUILTIN_AGENTS.get(agent_id)
    if cls is None:
        raise KeyError(f"Unknown built-in agent '{agent_id}'.")
    return cls()