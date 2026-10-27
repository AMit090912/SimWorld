"""Dynamic city logistics environment.

A grid road network, one delivery van, packages with deadlines, fuel, and
scheduled disruptions. The world is a pure state machine: the same config,
seed, and action sequence always produce the same transitions.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from itertools import combinations
from typing import Any, Iterable

from .actions import Action, ApplyResult

STEP_MINUTES_DEFAULT = 2


def edge_id(a: str, b: str) -> str:
    """Canonical, order-independent edge identifier."""
    pa = tuple(int(v) for v in a.split(","))
    pb = tuple(int(v) for v in b.split(","))
    lo, hi = (pa, pb) if pa <= pb else (pb, pa)
    return f"{lo[0]},{lo[1]}|{hi[0]},{hi[1]}"


def parse_node(node: str) -> tuple[int, int]:
    try:
        x, y = node.split(",")
        return int(x), int(y)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid node id: {node!r}") from exc


class CityWorld:
    kind = "city_logistics"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.scenario_id: str = config["scenario_id"]
        self.seed: int = int(config["seed"])
        self.grid: int = int(config["grid"])
        self.depot: str = config["depot"]
        self.edge_km: float = float(config.get("edge_km", 0.55))
        self.step_minutes: int = int(config.get("step_minutes", STEP_MINUTES_DEFAULT))
        self.horizon_steps: int = int(config.get("horizon_steps", 150))
        self.fog_radius: int | None = config.get("fog_radius")

        self.edges: dict[str, dict[str, Any]] = self._build_edges(config.get("blocked_edges", []))
        self.adjacency: dict[str, list[str]] = self._build_adjacency()

        vehicle_cfg = config["vehicle"]
        self.vehicle: dict[str, Any] = {
            "node": self.depot,
            "fuel_l": float(vehicle_cfg["fuel_l"]),
            "fuel_capacity_l": float(vehicle_cfg["fuel_capacity_l"]),
            "consumption_l_per_km": float(vehicle_cfg.get("consumption_l_per_km", 0.3)),
            "capacity": int(vehicle_cfg.get("capacity", 3)),
            "cargo": [],
            "distance_km": 0.0,
        }
        self.initial_fuel_l = float(vehicle_cfg["fuel_l"])

        self.packages: dict[str, dict[str, Any]] = {}
        for pkg in config["packages"]:
            self.packages[pkg["id"]] = {
                "id": pkg["id"],
                "origin": pkg.get("origin", self.depot),
                "dest": pkg["dest"],
                "dest_label": pkg.get("dest_label", pkg["dest"]),
                "deadline_min": int(pkg["deadline_min"]),
                "weight_kg": float(pkg.get("weight_kg", 5)),
                "priority": pkg.get("priority", "standard"),
                "status": "at_depot",
                "delivered_at_min": None,
                "late": False,
            }

        self.stations: dict[str, float] = {
            s["node"]: float(s["stock_l"]) for s in config.get("stations", [])
        }
        self.initial_stations = dict(self.stations)

        self.trail: list[str] = [self.depot]
        self.step = 0
        self.time_min = 0
        self.status = "running"
        self.terminal_reason: str | None = None
        self.events: list[dict[str, Any]] = []
        self.event_plan: list[dict[str, Any]] = sorted(
            (dict(e) for e in config.get("event_plan", [])), key=lambda e: int(e["at_step"])
        )
        self.next_event_index = 0
        self.live_events: list[dict[str, Any]] = []
        self.stats: dict[str, Any] = {
            "invalid_actions": 0,
            "invalid_by_reason": {},
            "fuel_consumed_l": 0.0,
            "fuel_refueled_l": 0.0,
            "distance_km": 0.0,
            "pickups": 0,
            "waits": 0,
            "deliveries": 0,
            "on_time": 0,
        }
        self._event_seq = 0
        self._validate_initial_conditions()

    # ------------------------------------------------------------------ setup
    def _build_edges(self, blocked: Iterable[Iterable[str]]) -> dict[str, dict[str, Any]]:
        blocked_ids = {edge_id(str(pair[0]), str(pair[1])) for pair in blocked}
        edges: dict[str, dict[str, Any]] = {}
        for x in range(self.grid):
            for y in range(self.grid):
                node = f"{x},{y}"
                for nx, ny in ((x + 1, y), (x, y + 1)):
                    if nx >= self.grid or ny >= self.grid:
                        continue
                    other = f"{nx},{ny}"
                    eid = edge_id(node, other)
                    if eid in blocked_ids:
                        continue
                    edges[eid] = {"a": node, "b": other, "open": True, "km": self.edge_km}
        return edges

    def _build_adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {}
        for eid in sorted(self.edges):
            edge = self.edges[eid]
            adj.setdefault(edge["a"], []).append(edge["b"])
            adj.setdefault(edge["b"], []).append(edge["a"])
        for node in adj:
            adj[node].sort()
        return adj

    def _node_distance(self, start: str, limit: int) -> set[str]:
        seen = {start}
        queue = deque([(start, 0)])
        while queue:
            node, dist = queue.popleft()
            if dist >= limit:
                continue
            for neighbour in self.adjacency.get(node, []):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append((neighbour, dist + 1))
        return seen

    def _validate_initial_conditions(self) -> None:
        for pkg in self.packages.values():
            if pkg["dest"] not in self.adjacency:
                raise ValueError(f"Package {pkg['id']} destination is not on the road network.")
        reachable = self._node_distance(self.depot, self.grid * self.grid)
        for pkg in self.packages.values():
            if pkg["dest"] not in reachable:
                raise ValueError(
                    f"Package {pkg['id']} destination {pkg['dest']} is unreachable from the depot."
                )
        if self.depot not in self.adjacency:
            raise ValueError("Depot has no road connections.")

    # -------------------------------------------------------------- observation
    def _visible_nodes(self) -> set[str] | None:
        if self.fog_radius is None:
            return None
        return self._node_distance(self.vehicle["node"], int(self.fog_radius))

    def _edge_visible(self, eid: str, visible: set[str] | None) -> bool:
        if visible is None:
            return True
        edge = self.edges[eid]
        return edge["a"] in visible and edge["b"] in visible

    def visible_closed_edges(self) -> list[str]:
        visible = self._visible_nodes()
        return sorted(
            eid
            for eid, edge in self.edges.items()
            if not edge["open"] and self._edge_visible(eid, visible)
        )

    def legal_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        node = self.vehicle["node"]
        visible = self._visible_nodes()
        for neighbour in self.adjacency.get(node, []):
            eid = edge_id(node, neighbour)
            if not self.edges[eid]["open"] and self._edge_visible(eid, visible):
                continue
            actions.append({"type": "move", "target": neighbour})

        available = [
            p["id"]
            for p in self.packages.values()
            if p["status"] == "at_depot"
        ]
        free_slots = self.vehicle["capacity"] - len(self.vehicle["cargo"])
        if node == self.depot and free_slots > 0 and available:
            # Enumerate every loadable subset so the advertised action space is
            # complete for the van's remaining capacity.
            for size in range(1, min(free_slots, len(available)) + 1):
                for combo in combinations(available, size):
                    actions.append({"type": "pickup", "package_ids": list(combo)})

        for pid in self.vehicle["cargo"]:
            if self.packages[pid]["dest"] == node:
                actions.append({"type": "deliver", "package_id": pid})

        stock = self.stations.get(node, 0.0)
        if stock > 0 and self.vehicle["fuel_l"] < self.vehicle["fuel_capacity_l"] - 0.01:
            actions.append({"type": "refuel", "amount": 5.0})

        actions.append({"type": "wait"})
        return actions

    def observation(self) -> dict[str, Any]:
        visible = self._visible_nodes()
        closed = self.visible_closed_edges()
        cargo = []
        for pid in self.vehicle["cargo"]:
            pkg = self.packages[pid]
            cargo.append(
                {
                    "id": pkg["id"],
                    "dest": pkg["dest"],
                    "dest_label": pkg["dest_label"],
                    "deadline_min": pkg["deadline_min"],
                    "weight_kg": pkg["weight_kg"],
                }
            )

        packages = []
        for pkg in self.packages.values():
            entry = {
                "id": pkg["id"],
                "dest": pkg["dest"],
                "dest_label": pkg["dest_label"],
                "deadline_min": pkg["deadline_min"],
                "weight_kg": pkg["weight_kg"],
                "priority": pkg["priority"],
                "status": pkg["status"],
            }
            if pkg["delivered_at_min"] is not None:
                entry["delivered_at_min"] = pkg["delivered_at_min"]
                entry["late"] = pkg["late"]
            packages.append(entry)

        metrics = self.metrics()
        return {
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "step": self.step,
            "time_min": self.time_min,
            "horizon_steps": self.horizon_steps,
            "step_minutes": self.step_minutes,
            "objective": self.config.get("objective", "Deliver every package before its deadline."),
            "trail": list(self.trail),
            "vehicle": {
                "node": self.vehicle["node"],
                "fuel_l": round(self.vehicle["fuel_l"], 3),
                "fuel_capacity_l": self.vehicle["fuel_capacity_l"],
                "consumption_l_per_km": self.vehicle["consumption_l_per_km"],
                "capacity": self.vehicle["capacity"],
                "cargo": cargo,
                "distance_km": round(self.vehicle["distance_km"], 3),
            },
            "depot": self.depot,
            "edge_km": self.edge_km,
            "adjacency": {node: self.adjacency.get(node, []) for node in self.adjacency},
            "closed_edges": closed,
            "known_road_count": len(self.edges),
            "packages": packages,
            "stations": [
                {"node": node, "stock_l": round(stock, 2)} for node, stock in sorted(self.stations.items())
            ],
            "visible_nodes": sorted(visible) if visible is not None else None,
            "recent_events": self.events[-4:],
            "metrics": metrics,
            "legal_actions": self.legal_actions(),
        }

    # ------------------------------------------------------------------- rules
    def _adjacent_edge(self, node: str, target: str) -> dict[str, Any] | None:
        if target not in self.adjacency.get(node, []):
            return None
        return self.edges.get(edge_id(node, target))

    def apply(self, action: Action) -> ApplyResult:
        if self.status != "running":
            return ApplyResult.rejected("run_not_running", f"Run is {self.status}.")

        if action.type == "move":
            result = self._apply_move(action.target or "")
        elif action.type == "wait":
            result = ApplyResult.success("Vehicle waited.")
            self.stats["waits"] += 1
        elif action.type == "pickup":
            result = self._apply_pickup(action.package_ids)
        elif action.type == "deliver":
            result = self._apply_deliver(action.package_id or "")
        elif action.type == "refuel":
            result = self._apply_refuel(action.amount)
        else:
            result = ApplyResult.rejected(
                "wrong_environment",
                f"Action '{action.type}' is not supported in the city logistics environment.",
            )

        if not result.ok:
            self.stats["invalid_actions"] += 1
            by_reason = self.stats["invalid_by_reason"]
            by_reason[result.code] = by_reason.get(result.code, 0) + 1

        self._advance()
        self._check_terminal()
        return result

    def _apply_move(self, target: str) -> ApplyResult:
        edge = self._adjacent_edge(self.vehicle["node"], target)
        if edge is None:
            return ApplyResult.rejected(
                "not_adjacent",
                f"Cannot move from {self.vehicle['node']} to {target}: no direct road.",
            )
        if not edge["open"]:
            return ApplyResult.rejected(
                "road_closed", f"Road {edge_id(edge['a'], edge['b'])} is closed.", edge=edge_id(edge["a"], edge["b"])
            )
        required = edge["km"] * self.vehicle["consumption_l_per_km"]
        if self.vehicle["fuel_l"] + 1e-9 < required:
            return ApplyResult.rejected(
                "insufficient_fuel",
                f"Move needs {required:.3f} L but only {self.vehicle['fuel_l']:.3f} L remains.",
            )
        self.vehicle["node"] = target
        self.trail = (self.trail + [target])[-500:]
        self.vehicle["fuel_l"] = max(0.0, self.vehicle["fuel_l"] - required)
        self.vehicle["distance_km"] += edge["km"]
        self.stats["fuel_consumed_l"] += required
        self.stats["distance_km"] += edge["km"]
        return ApplyResult.success(
            f"Moved to {target}.", fuel_used_l=round(required, 3), location=target
        )

    def _apply_pickup(self, package_ids: tuple[str, ...]) -> ApplyResult:
        if self.vehicle["node"] != self.depot:
            return ApplyResult.rejected(
                "not_at_depot", "Packages can only be picked up at the depot."
            )
        if not package_ids:
            return ApplyResult.rejected("no_packages", "No package ids supplied.")
        unknown = [pid for pid in package_ids if pid not in self.packages]
        if unknown:
            return ApplyResult.rejected("package_not_found", f"Unknown package(s): {unknown}.")
        not_ready = [pid for pid in package_ids if self.packages[pid]["status"] != "at_depot"]
        if not_ready:
            return ApplyResult.rejected(
                "package_not_at_depot", f"Package(s) not available at the depot: {not_ready}."
            )
        free = self.vehicle["capacity"] - len(self.vehicle["cargo"])
        if len(package_ids) > free:
            return ApplyResult.rejected(
                "capacity_exceeded",
                f"Van has {free} free slot(s) but {len(package_ids)} package(s) were requested.",
            )
        for pid in package_ids:
            self.packages[pid]["status"] = "in_transit"
            self.vehicle["cargo"].append(pid)
        self.stats["pickups"] += len(package_ids)
        return ApplyResult.success(
            f"Loaded {len(package_ids)} package(s).", packages=list(package_ids)
        )

    def _apply_deliver(self, package_id: str) -> ApplyResult:
        pkg = self.packages.get(package_id)
        if pkg is None:
            return ApplyResult.rejected("package_not_found", f"Unknown package '{package_id}'.")
        if package_id not in self.vehicle["cargo"]:
            return ApplyResult.rejected(
                "package_not_in_cargo", f"Package '{package_id}' is not in the van."
            )
        if self.vehicle["node"] != pkg["dest"]:
            return ApplyResult.rejected(
                "wrong_location",
                f"Package '{package_id}' must be delivered at {pkg['dest']}, "
                f"van is at {self.vehicle['node']}.",
            )
        delivery_time = self.time_min + self.step_minutes
        late = delivery_time > pkg["deadline_min"]
        pkg["status"] = "delivered"
        pkg["delivered_at_min"] = delivery_time
        pkg["late"] = late
        self.vehicle["cargo"].remove(package_id)
        self.stats["deliveries"] += 1
        if not late:
            self.stats["on_time"] += 1
        return ApplyResult.success(
            f"Delivered {package_id} at {pkg['dest_label']}{' (late)' if late else ''}.",
            package_id=package_id,
            late=late,
            delivered_at_min=delivery_time,
        )

    def _apply_refuel(self, amount: float | None) -> ApplyResult:
        node = self.vehicle["node"]
        stock = self.stations.get(node, 0.0)
        if stock <= 0.01:
            return ApplyResult.rejected(
                "no_fuel_stock", f"No fuel available at {node}."
            )
        missing = self.vehicle["fuel_capacity_l"] - self.vehicle["fuel_l"]
        if missing <= 0.01:
            return ApplyResult.rejected("tank_full", "Fuel tank is already full.")
        requested = 5.0 if amount is None else float(amount)
        delivered = min(requested, missing, stock)
        if delivered <= 0:
            return ApplyResult.rejected("no_fuel_stock", "No fuel could be transferred.")
        self.vehicle["fuel_l"] += delivered
        self.stations[node] = round(stock - delivered, 3)
        self.stats["fuel_refueled_l"] += delivered
        return ApplyResult.success(
            f"Refuelled {delivered:.2f} L at {node}.", litres=round(delivered, 3)
        )

    # ------------------------------------------------------------------ events
    def _advance(self) -> None:
        self.step += 1
        self.time_min += self.step_minutes
        while (
            self.next_event_index < len(self.event_plan)
            and int(self.event_plan[self.next_event_index]["at_step"]) <= self.step
        ):
            event = self.event_plan[self.next_event_index]
            self.next_event_index += 1
            self._apply_event(event, source="plan")

    def _apply_event(self, event: dict[str, Any], source: str) -> None:
        event_type = event.get("type")
        message = event.get("message", "")
        severity = event.get("severity", "warning")
        payload: dict[str, Any] = {}

        if event_type in {"road_closure", "road_reopen"}:
            open_state = event_type == "road_reopen"
            changed = []
            for eid in event.get("edges", []):
                if eid in self.edges and self.edges[eid]["open"] != open_state:
                    self.edges[eid]["open"] = open_state
                    changed.append(eid)
            if not changed:
                return
            payload["edges"] = changed
        elif event_type == "deadline_change":
            pid = event.get("package_id")
            pkg = self.packages.get(pid)
            if pkg is None or pkg["status"] == "delivered":
                return
            delta = int(event.get("delta_min", 0))
            pkg["deadline_min"] = max(0, pkg["deadline_min"] + delta)
            payload = {"package_id": pid, "delta_min": delta, "deadline_min": pkg["deadline_min"]}
            if not message:
                message = f"Deadline for {pid} changed by {delta:+d} min."
        elif event_type == "station_stock":
            node = event.get("node")
            if node not in self.stations:
                return
            self.stations[node] = round(float(event.get("stock_l", 0.0)), 3)
            payload = {"node": node, "stock_l": self.stations[node]}
        else:
            return

        self._event_seq += 1
        record = {
            "seq": self._event_seq,
            "step": self.step,
            "time_min": self.time_min,
            "type": event_type,
            "severity": severity,
            "message": message,
            "payload": payload,
            "source": source,
        }
        self.events.append(record)
        if source == "live":
            # Live injections happen between ticks. Record the step so replay can
            # reconstruct them in order with the recorded actions.
            self.live_events.append({**event, "at_step": self.step})

    def inject(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Inject a live disruption. Returns the event record, or None if unusable."""
        before = len(self.events)
        self._apply_event({**event, "source": "live"}, source="live")
        if len(self.events) == before:
            return None
        return self.events[-1]

    # -------------------------------------------------------------- termination
    def _all_delivered(self) -> bool:
        return all(p["status"] == "delivered" for p in self.packages.values())

    def _check_terminal(self) -> None:
        if self.status != "running":
            return
        if self._all_delivered():
            self.status = "finished"
            self.terminal_reason = "all_delivered"
        elif self.step >= self.horizon_steps:
            self.status = "finished"
            self.terminal_reason = "horizon_reached"

    def terminal(self) -> tuple[bool, str | None]:
        return self.status != "running", self.terminal_reason

    def fail(self, reason: str) -> None:
        self.status = "failed"
        self.terminal_reason = reason

    # ---------------------------------------------------------------- snapshot
    def snapshot(self) -> dict[str, Any]:
        """Ground truth for observers, replay, and the UI. Never sent to agents."""
        return {
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "scenario_version": self.config.get("scenario_version"),
            "seed": self.seed,
            "step": self.step,
            "time_min": self.time_min,
            "horizon_steps": self.horizon_steps,
            "step_minutes": self.step_minutes,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "grid": self.grid,
            "depot": self.depot,
            "edge_km": self.edge_km,
            "fog_radius": self.fog_radius,
            "options": self.config.get("options", {}),
            "edges": [
                {"id": eid, "a": e["a"], "b": e["b"], "open": e["open"], "km": e["km"]}
                for eid, e in sorted(self.edges.items())
            ],
            "trail": list(self.trail),
            "vehicle": {
                "node": self.vehicle["node"],
                "fuel_l": round(self.vehicle["fuel_l"], 3),
                "fuel_capacity_l": self.vehicle["fuel_capacity_l"],
                "capacity": self.vehicle["capacity"],
                "cargo": list(self.vehicle["cargo"]),
                "distance_km": round(self.vehicle["distance_km"], 3),
            },
            "packages": [dict(p) for p in self.packages.values()],
            "stations": [
                {"node": node, "stock_l": round(stock, 2)}
                for node, stock in sorted(self.stations.items())
            ],
            "events": list(self.events),
            "metrics": self.metrics(),
            "state_hash": self.state_hash(),
        }

    # ----------------------------------------------------------------- metrics
    def metrics(self) -> dict[str, Any]:
        total = len(self.packages)
        delivered = sum(1 for p in self.packages.values() if p["status"] == "delivered")
        on_time = sum(
            1 for p in self.packages.values() if p["status"] == "delivered" and not p["late"]
        )
        late = delivered - on_time
        fuel_used = round(self.stats["fuel_consumed_l"], 3)
        return {
            "packages_total": total,
            "packages_delivered": delivered,
            "packages_on_time": on_time,
            "packages_late": late,
            "completion_rate": round(delivered / total, 4) if total else 0.0,
            "on_time_rate": round(on_time / total, 4) if total else 0.0,
            "on_time_rate_delivered": round(on_time / delivered, 4) if delivered else 0.0,
            "fuel_consumed_l": fuel_used,
            "fuel_refueled_l": round(self.stats["fuel_refueled_l"], 3),
            "fuel_remaining_l": round(self.vehicle["fuel_l"], 3),
            "distance_km": round(self.stats["distance_km"], 3),
            "invalid_actions": self.stats["invalid_actions"],
            "invalid_by_reason": dict(self.stats["invalid_by_reason"]),
            "pickups": self.stats["pickups"],
            "deliveries": self.stats["deliveries"],
            "waits": self.stats["waits"],
            "steps": self.step,
            "sim_minutes": self.time_min,
            "disruptions": len(self.events),
        }

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "config": self.config,
            "edges": self.edges,
            "trail": self.trail,
            "vehicle": self.vehicle,
            "packages": self.packages,
            "stations": self.stations,
            "step": self.step,
            "time_min": self.time_min,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "events": self.events,
            "event_plan": self.event_plan,
            "next_event_index": self.next_event_index,
            "live_events": self.live_events,
            "stats": self.stats,
            "event_seq": self._event_seq,
            "state_hash": self.state_hash(),
        }

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "CityWorld":
        world = cls(state["config"])
        world.edges = state["edges"]
        world.adjacency = world._build_adjacency()
        world.trail = state.get("trail", [world.depot])
        world.vehicle = state["vehicle"]
        world.packages = state["packages"]
        world.stations = state["stations"]
        world.step = state["step"]
        world.time_min = state["time_min"]
        world.status = state["status"]
        world.terminal_reason = state["terminal_reason"]
        world.events = state["events"]
        world.event_plan = state["event_plan"]
        world.next_event_index = state["next_event_index"]
        world.live_events = state.get("live_events", [])
        world.stats = state["stats"]
        world._event_seq = state.get("event_seq", len(world.events))
        return world

    def state_hash(self) -> str:
        payload = json.dumps(
            {
                "vehicle": self.vehicle,
                "packages": self.packages,
                "stations": self.stations,
                "edges": {k: v["open"] for k, v in sorted(self.edges.items())},
                "step": self.step,
                "status": self.status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]