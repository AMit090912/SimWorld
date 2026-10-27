"""A complete, dependency-free SimWorld external agent.

Run it, then point SimWorld at http://127.0.0.1:9100/agent:

    python examples/external_agent.py --port 9100

The agent implements the same protocol documented in README.md. It is
deliberately small: route to the most urgent package, load batches at the
depot, refuel when low, and pick the highest-pressure signal in traffic mode.
"""

from __future__ import annotations

import argparse
import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PROTOCOL = "simworld.agent.v1"
MAX_BODY = 256 * 1024


def edge_key(a: str, b: str) -> str:
    key = lambda node: tuple(int(part) for part in node.split(","))
    lo, hi = sorted((a, b), key=key)
    return f"{lo}|{hi}"


def bfs(adjacency: dict[str, list[str]], start: str, goal: str, closed: set[str]) -> list[str] | None:
    if start == goal:
        return [start]
    seen = {start}
    queue: deque[list[str]] = deque([[start]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for neighbour in adjacency.get(node, []):
            if neighbour in seen or edge_key(node, neighbour) in closed:
                continue
            if neighbour == goal:
                return path + [neighbour]
            seen.add(neighbour)
            queue.append(path + [neighbour])
    return None


def choose_city(observation: dict[str, Any], legal: list[dict[str, Any]]) -> dict[str, Any]:
    vehicle = observation["vehicle"]
    node = vehicle["node"]
    packages = {pkg["id"]: pkg for pkg in observation["packages"]}
    cargo = [pkg["id"] for pkg in vehicle["cargo"]]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for action in legal:
        by_type.setdefault(action["type"], []).append(action)

    deliver = by_type.get("deliver", [])
    if deliver:
        deliver.sort(key=lambda a: packages[a["package_id"]]["deadline_min"])
        return deliver[0]

    low_fuel = vehicle["fuel_l"] < vehicle["fuel_capacity_l"] * 0.3
    if low_fuel and by_type.get("refuel"):
        return by_type["refuel"][0]

    pickups = by_type.get("pickup", [])
    if pickups and node == observation["depot"]:
        # Prefer the largest load, then the earliest deadline.
        pickups.sort(
            key=lambda action: (
                -len(action.get("package_ids", [action.get("package_id")])),
                min(packages[pid]["deadline_min"] for pid in action.get("package_ids", [action.get("package_id")])),
            )
        )
        return pickups[0]

    adjacency = observation["adjacency"]
    closed = set(observation.get("closed_edges", []))
    targets = [packages[pid] for pid in cargo if packages[pid]["status"] != "delivered"]
    if not targets:
        targets = [pkg for pkg in packages.values() if pkg["status"] == "at_depot"]
    if not targets:
        return {"type": "wait"}

    best: tuple[int, int, dict[str, Any]] | None = None
    for pkg in targets:
        route = bfs(adjacency, node, pkg["dest"], closed)
        if route and len(route) > 1:
            candidate = (pkg["deadline_min"], len(route), pkg)
            if best is None or candidate[:2] < best[:2]:
                best = candidate

    # A low tank outranks the delivery plan: reach a station with stock first.
    if low_fuel:
        stations = [station for station in observation.get("stations", []) if station["stock_l"] > 0.01]
        station_routes = []
        for station in stations:
            route = bfs(adjacency, node, station["node"], closed)
            if route and len(route) > 1:
                station_routes.append((len(route), station["node"], route))
        if station_routes:
            station_routes.sort()
            return {"type": "move", "target": station_routes[0][2][1]}

    if best is not None:
        return {"type": "move", "target": bfs(adjacency, node, best[2]["dest"], closed)[1]}
    return {"type": "wait"}


def choose_traffic(observation: dict[str, Any], legal: list[dict[str, Any]]) -> dict[str, Any]:
    switches = [action for action in legal if action["type"] == "set_phase"]
    if not switches:
        return {"type": "wait"}
    by_key = {(action["intersection"], action["phase"]): action for action in switches}
    best: tuple[float, dict[str, Any]] | None = None
    for intersection in observation["intersections"]:
        queues = intersection["queues"]
        ns = queues.get("N", 0) + queues.get("S", 0)
        ew = queues.get("E", 0) + queues.get("W", 0)
        if ns == ew:
            continue
        desired = "NS" if ns > ew else "EW"
        action = by_key.get((intersection["id"], desired))
        if action is None:
            continue
        pressure = abs(ns - ew) + 0.2 * intersection["oldest_wait_ticks"]
        if best is None or pressure > best[0]:
            best = (pressure, action)
    return best[1] if best else {"type": "wait"}


class Handler(BaseHTTPRequestHandler):
    server_version = "SimWorldExampleAgent/1.0"

    def log_message(self, *_args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        if self.path in {"/", "/health"}:
            self._send(200, {"ok": True, "protocol": PROTOCOL, "agent": "example"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": "bad body"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if payload.get("protocol") != PROTOCOL:
                self._send(400, {"error": f"expected protocol {PROTOCOL}"})
                return
            observation = payload["observation"]
            legal = payload["legal_actions"]
            if observation.get("kind") == "city_logistics":
                action = choose_city(observation, legal)
                reasoning = "Serve the earliest deadline, load batches at the depot, refuel when low."
            elif observation.get("kind") == "traffic_control":
                action = choose_traffic(observation, legal)
                reasoning = "Switch the intersection with the largest opposing queue pressure."
            else:
                self._send(400, {"error": "unknown environment"})
                return
            self._send(200, {"action": action, "reasoning": reasoning})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": f"invalid request: {exc}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="SimWorld example external agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SimWorld example agent listening on http://{args.host}:{args.port}/agent")
    print("Configure this URL in the Agents screen or POST /api/agents/test.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()