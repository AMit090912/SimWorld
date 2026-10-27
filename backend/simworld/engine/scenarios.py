"""Scenario catalogue and reproducible initial-condition generation.

Scenario builders are the only place randomness enters a run. They turn a seed
and variation options into a fully explicit configuration; the engine itself
never draws a random number.
"""

from __future__ import annotations

import random
from typing import Any

from .city import CityWorld, edge_id
from .traffic import TrafficWorld

SCENARIO_VERSION = 1

CITY_DESTINATIONS = [
    {"node": "6,1", "label": "Harbor Market"},
    {"node": "2,6", "label": "Old Town Clinic"},
    {"node": "7,5", "label": "Foundry Gate"},
    {"node": "4,2", "label": "Civic Tower"},
    {"node": "1,3", "label": "North Docks"},
    {"node": "5,7", "label": "South Depot Annex"},
    {"node": "7,7", "label": "East Recycling"},
    {"node": "0,5", "label": "West School"},
]

CITY_BLOCKED_EDGES = [
    ["2,2", "3,2"],
    ["2,2", "2,3"],
    ["5,5", "6,5"],
    ["1,5", "1,6"],
    ["4,6", "5,6"],
]

CITY_BASE = {
    "grid": 8,
    "depot": "0,0",
    "edge_km": 0.55,
    "step_minutes": 2,
    "blocked_edges": CITY_BLOCKED_EDGES,
    "objective": (
        "Deliver all packages before their deadlines while keeping fuel in reserve. "
        "Plan around road closures and report only actions allowed by the engine."
    ),
}

TRAFFIC_OBJECTIVE = (
    "Maximise vehicle throughput and minimise waiting time across all intersections. "
    "Respect the minimum green time on every signal."
)

VARIATION_SCHEMA: dict[str, dict[str, Any]] = {
    "disruption_timing": {
        "label": "Disruption timing",
        "options": [
            {"value": "standard", "label": "As scheduled"},
            {"value": "early", "label": "Early (x0.6)"},
            {"value": "late", "label": "Late (x1.4)"},
        ],
        "default": "standard",
        "applies_to": ["city_logistics"],
    },
    "fuel_supply": {
        "label": "Fuel supply",
        "options": [
            {"value": "normal", "label": "Normal"},
            {"value": "scarce", "label": "Scarce (-1.5 L, half stock)"},
        ],
        "default": "normal",
        "applies_to": ["city_logistics"],
    },
    "deadline_pressure": {
        "label": "Deadline pressure",
        "options": [
            {"value": "normal", "label": "Normal"},
            {"value": "tight", "label": "Tight (-18%)"},
        ],
        "default": "normal",
        "applies_to": ["city_logistics"],
    },
    "visibility": {
        "label": "Observation range",
        "options": [
            {"value": "full", "label": "Full city view"},
            {"value": "limited", "label": "Local (2 hops)"},
        ],
        "default": "full",
        "applies_to": ["city_logistics"],
    },
    "demand": {
        "label": "Demand",
        "options": [
            {"value": "normal", "label": "Normal"},
            {"value": "surge", "label": "Surge (+40% arrivals)"},
        ],
        "default": "normal",
        "applies_to": ["traffic_control"],
    },
    "incidents": {
        "label": "Incidents",
        "options": [
            {"value": "normal", "label": "As scheduled"},
            {"value": "none", "label": "None"},
            {"value": "severe", "label": "Severe (+2)"},
        ],
        "default": "normal",
        "applies_to": ["traffic_control"],
    },
}

CITY_METRICS = [
    "completion_rate",
    "on_time_rate",
    "fuel_consumed_l",
    "distance_km",
    "invalid_actions",
    "agent_latency_ms",
    "recovery_steps",
]
TRAFFIC_METRICS = [
    "throughput_rate",
    "avg_wait_ticks",
    "avg_queue_length",
    "rule_violations",
    "invalid_actions",
    "agent_latency_ms",
]

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "city-logistics/standard",
        "version": SCENARIO_VERSION,
        "kind": "city_logistics",
        "name": "Riverside Standard Run",
        "tagline": "Seven drops, one van, a city that mostly behaves.",
        "description": (
            "The baseline dispatch shift. A single van works the Riverside grid with "
            "seven packages, a mid-route fuel stop, and one scheduled road closure. "
            "Use this run to establish a benchmark before turning up the pressure."
        ),
        "difficulty": "Calm",
        "objectives": [
            "Deliver all seven packages",
            "Hit as many deadlines as possible",
            "Avoid running the tank dry",
        ],
        "constraints": [
            "Van capacity: 3 packages",
            "Fuel is consumed per kilometre, not per move",
            "One scheduled closure is injected mid-shift",
        ],
        "variations": ["disruption_timing", "fuel_supply", "deadline_pressure", "visibility"],
        "default_options": {
            "disruption_timing": "standard",
            "fuel_supply": "normal",
            "deadline_pressure": "normal",
            "visibility": "full",
        },
        "params": {
            "package_count": 7,
            "deadline_base": 78,
            "deadline_jitter": 14,
            "horizon_steps": 150,
            "fuel_l": 8.0,
            "fuel_capacity_l": 12.0,
            "consumption_l_per_km": 0.3,
            "initial_fuel_boost": 0.0,
            "events": ["closure"],
            "fog_radius": None,
        },
    },
    {
        "id": "city-logistics/rush-hour",
        "version": SCENARIO_VERSION,
        "kind": "city_logistics",
        "name": "Rush Hour Crunch",
        "tagline": "Tighter deadlines, more packages, less margin.",
        "description": (
            "Eight packages with compressed deadlines and heavier traffic penalties. "
            "Batching deliveries is mandatory; a greedy nearest-first route will drop "
            "at least two deadlines."
        ),
        "difficulty": "Tight",
        "objectives": [
            "Deliver all eight packages",
            "Keep the on-time rate above 70%",
            "Refuel without stranding the van",
        ],
        "constraints": [
            "Van capacity: 3 packages",
            "Deadlines are 18% tighter than the standard shift",
            "One closure plus one deadline change are scheduled",
        ],
        "variations": ["disruption_timing", "fuel_supply", "deadline_pressure", "visibility"],
        "default_options": {
            "disruption_timing": "standard",
            "fuel_supply": "normal",
            "deadline_pressure": "normal",
            "visibility": "full",
        },
        "params": {
            "package_count": 8,
            "deadline_base": 62,
            "deadline_jitter": 10,
            "horizon_steps": 150,
            "fuel_l": 7.5,
            "fuel_capacity_l": 12.0,
            "consumption_l_per_km": 0.3,
            "initial_fuel_boost": 0.0,
            "events": ["closure", "deadline"],
            "fog_radius": None,
        },
    },
    {
        "id": "city-logistics/disruption-storm",
        "version": SCENARIO_VERSION,
        "kind": "city_logistics",
        "name": "Disruption Storm",
        "tagline": "Two closures, a deadline shock, and a fuel station running dry.",
        "description": (
            "The stress test. Two roads close mid-shift, one package deadline moves "
            "earlier, and a station's stock is cut. A disruption-aware plan must "
            "recompute routes instead of following a cached path."
        ),
        "difficulty": "Brutal",
        "objectives": [
            "Recover from each disruption and keep delivering",
            "Do not exhaust the tank",
            "Keep invalid actions at zero",
        ],
        "constraints": [
            "Van capacity: 3 packages",
            "Two scheduled closures, one deadline change, one fuel shortage",
            "Fuel stations have limited stock",
        ],
        "variations": ["disruption_timing", "fuel_supply", "deadline_pressure", "visibility"],
        "default_options": {
            "disruption_timing": "standard",
            "fuel_supply": "normal",
            "deadline_pressure": "normal",
            "visibility": "full",
        },
        "params": {
            "package_count": 7,
            "deadline_base": 74,
            "deadline_jitter": 12,
            "horizon_steps": 150,
            "fuel_l": 7.0,
            "fuel_capacity_l": 12.0,
            "consumption_l_per_km": 0.3,
            "initial_fuel_boost": 0.0,
            "events": ["closure", "closure", "deadline", "fuel"],
            "fog_radius": None,
        },
    },
    {
        "id": "city-logistics/low-visibility",
        "version": SCENARIO_VERSION,
        "kind": "city_logistics",
        "name": "Fog Over Riverside",
        "tagline": "You only see two blocks ahead. Closures are discovered the hard way.",
        "description": (
            "Observation range is limited to two road hops. Agents must probe, react to "
            "rejections, and avoid committing to long blind routes. The built-in "
            "disruption-aware agent has no special knowledge here either."
        ),
        "difficulty": "Hard",
        "objectives": [
            "Deliver all six packages",
            "Recover quickly from discovered closures",
            "Keep invalid actions low",
        ],
        "constraints": [
            "Observation radius: 2 hops",
            "Van capacity: 3 packages",
            "Two closures are hidden outside the initial view",
        ],
        "variations": ["disruption_timing", "fuel_supply", "deadline_pressure", "visibility"],
        "default_options": {
            "disruption_timing": "standard",
            "fuel_supply": "normal",
            "deadline_pressure": "normal",
            "visibility": "limited",
        },
        "params": {
            "package_count": 6,
            "deadline_base": 80,
            "deadline_jitter": 10,
            "horizon_steps": 150,
            "fuel_l": 8.0,
            "fuel_capacity_l": 12.0,
            "consumption_l_per_km": 0.3,
            "initial_fuel_boost": 0.0,
            "events": ["closure", "closure"],
            "fog_radius": 2,
        },
    },
    {
        "id": "traffic-control/steady",
        "version": SCENARIO_VERSION,
        "kind": "traffic_control",
        "name": "Steady Commuter Flow",
        "tagline": "Nine intersections, moderate demand, one incident.",
        "description": (
            "A balanced signal-control benchmark. Nine intersections feed a steady "
            "commuter flow. Phase switches are limited by a three-tick minimum green. "
            "Baseline fixed-cycle timing leaves measurable queue growth."
        ),
        "difficulty": "Calm",
        "objectives": [
            "Minimise average waiting time",
            "Keep throughput above 75%",
            "Zero safety-rule violations",
        ],
        "constraints": [
            "Minimum green: 3 ticks",
            "2 vehicles discharge per green tick",
            "Switching a phase burns that intersection's green tick",
        ],
        "variations": ["demand", "incidents"],
        "default_options": {"demand": "normal", "incidents": "normal"},
        "params": {
            "grid": 3,
            "horizon_steps": 120,
            "min_green": 3,
            "discharge_per_tick": 2,
            "arrival_probability": 0.62,
            "arrival_max": 2,
            "incidents": 1,
        },
    },
    {
        "id": "traffic-control/surge",
        "version": SCENARIO_VERSION,
        "kind": "traffic_control",
        "name": "Stadium Surge",
        "tagline": "Event traffic, two lane incidents, and no slack.",
        "description": (
            "Demand spikes around a stadium egress while two lane incidents block "
            "approaches. Fixed-cycle controllers collapse; adaptive control can hold "
            "the line if it respects minimum green times."
        ),
        "difficulty": "Hard",
        "objectives": [
            "Keep average wait under 8 ticks",
            "Clear at least 80% of arrivals",
            "Zero safety-rule violations",
        ],
        "constraints": [
            "Minimum green: 3 ticks",
            "High arrival density",
            "Two incidents block specific approaches",
        ],
        "variations": ["demand", "incidents"],
        "default_options": {"demand": "normal", "incidents": "normal"},
        "params": {
            "grid": 3,
            "horizon_steps": 120,
            "min_green": 3,
            "discharge_per_tick": 2,
            "arrival_probability": 0.8,
            "arrival_max": 3,
            "incidents": 2,
        },
    },
]

SCENARIO_BY_ID = {scenario["id"]: scenario for scenario in SCENARIOS}


def _city_edges(grid: int, blocked: list[list[str]]) -> list[str]:
    blocked_ids = {edge_id(pair[0], pair[1]) for pair in blocked}
    edges: list[str] = []
    for x in range(grid):
        for y in range(grid):
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx >= grid or ny >= grid:
                    continue
                eid = edge_id(f"{x},{y}", f"{nx},{ny}")
                if eid not in blocked_ids:
                    edges.append(eid)
    return edges


def _shift_time(value: int, timing: str) -> int:
    if timing == "early":
        return max(6, int(round(value * 0.6)))
    if timing == "late":
        return int(round(value * 1.4))
    return value


def build_city_config(
    scenario: dict[str, Any], seed: int, options: dict[str, Any]
) -> dict[str, Any]:
    params = scenario["params"]
    rng = random.Random(f"{scenario['id']}|{seed}|{SCENARIO_VERSION}")

    options = {**scenario["default_options"], **options}
    timing = options.get("disruption_timing", "standard")
    fuel_supply = options.get("fuel_supply", "normal")
    deadline_pressure = options.get("deadline_pressure", "normal")
    visibility = options.get("visibility", "full")

    pool = list(CITY_DESTINATIONS)
    rng.shuffle(pool)
    package_count = int(params["package_count"])
    chosen = pool[:package_count]

    package_specs = []
    for index, dest in enumerate(chosen):
        jitter = rng.randint(-int(params["deadline_jitter"]), int(params["deadline_jitter"]))
        deadline = max(30, int(params["deadline_base"]) + jitter)
        if deadline_pressure == "tight":
            deadline = max(24, int(round(deadline * 0.82)))
        package_specs.append(
            {
                "id": f"PKG-{index + 1:02d}",
                "dest": dest["node"],
                "dest_label": dest["label"],
                "deadline_min": deadline,
                "weight_kg": rng.choice([3, 4, 6, 8, 10]),
                "priority": "critical" if index < 2 else "standard",
                "origin": CITY_BASE["depot"],
            }
        )

    fuel_l = float(params["fuel_l"])
    if fuel_supply == "scarce":
        fuel_l = max(3.0, fuel_l - 1.5)

    station_stock = 14.0 if fuel_supply == "normal" else 7.0
    station_stock_2 = 5.0 if fuel_supply == "normal" else 2.0
    station_stock_3 = 3.0 if fuel_supply == "normal" else 1.0

    fog_radius = params.get("fog_radius")
    if visibility == "limited":
        fog_radius = 2
    elif visibility == "full":
        fog_radius = None

    edges = _city_edges(int(params.get("grid", CITY_BASE["grid"])), CITY_BASE["blocked_edges"])
    event_plan: list[dict[str, Any]] = []
    closure_slots = [28, 52]
    deadline_slot = 40
    fuel_slot = 36

    closure_index = 0
    for event_kind in params["events"]:
        if event_kind == "closure":
            at_step = _shift_time(closure_slots[closure_index % len(closure_slots)], timing)
            closure_index += 1
            picks = rng.sample(edges, 2)
            event_plan.append(
                {
                    "at_step": at_step,
                    "type": "road_closure",
                    "edges": addsorted_edges(picks),
                    "severity": "critical",
                    "message": "Road works: two blocks closed without notice.",
                }
            )
        elif event_kind == "deadline":
            at_step = _shift_time(deadline_slot, timing)
            target = rng.choice(package_specs)["id"]
            event_plan.append(
                {
                    "at_step": at_step,
                    "type": "deadline_change",
                    "package_id": target,
                    "delta_min": -12,
                    "severity": "warning",
                    "message": f"Customer moved the slot for {target} earlier by 12 minutes.",
                }
            )
        elif event_kind == "fuel":
            at_step = _shift_time(fuel_slot, timing)
            event_plan.append(
                {
                    "at_step": at_step,
                    "type": "station_stock",
                    "node": "3,3",
                    "stock_l": 0.0,
                    "severity": "warning",
                    "message": "Midtown fuel station reports a delivery failure and runs dry.",
                }
            )

    # A mid-shift reopening keeps the world dynamic for long runs.
    if closure_index and scenario["id"] != "city-logistics/low-visibility":
        first = next((e for e in event_plan if e["type"] == "road_closure"), None)
        if first:
            event_plan.append(
                {
                    "at_step": _shift_time(int(first["at_step"]) + 34, timing),
                    "type": "road_reopen",
                    "edges": first["edges"],
                    "severity": "info",
                    "message": "Road works cleared; the closed blocks are open again.",
                }
            )

    config = {
        "scenario_id": scenario["id"],
        "scenario_version": SCENARIO_VERSION,
        "kind": "city_logistics",
        "seed": seed,
        "options": {
            "disruption_timing": timing,
            "fuel_supply": fuel_supply,
            "deadline_pressure": deadline_pressure,
            "visibility": "limited" if fog_radius else "full",
        },
        "grid": int(params.get("grid", CITY_BASE["grid"])),
        "depot": CITY_BASE["depot"],
        "edge_km": CITY_BASE["edge_km"],
        "step_minutes": CITY_BASE["step_minutes"],
        "blocked_edges": CITY_BASE["blocked_edges"],
        "objective": CITY_BASE["objective"],
        "fog_radius": fog_radius,
        "horizon_steps": int(params["horizon_steps"]),
        "vehicle": {
            "capacity": 3,
            "fuel_l": round(fuel_l + float(params.get("initial_fuel_boost", 0.0)), 2),
            "fuel_capacity_l": float(params["fuel_capacity_l"]),
            "consumption_l_per_km": float(params["consumption_l_per_km"]),
        },
        "stations": [
            {"node": "0,0", "stock_l": station_stock},
            {"node": "3,3", "stock_l": station_stock_2},
            {"node": "6,6", "stock_l": station_stock_3},
        ],
        "packages": package_specs,
        "event_plan": sorted(event_plan, key=lambda e: int(e["at_step"])),
    }
    return config


def addsorted_edges(edges: list[str]) -> list[str]:
    return sorted(edges)


def build_traffic_config(
    scenario: dict[str, Any], seed: int, options: dict[str, Any]
) -> dict[str, Any]:
    params = scenario["params"]
    options = {**scenario["default_options"], **options}
    demand = options.get("demand", "normal")
    incidents = options.get("incidents", "normal")

    rng = random.Random(f"{scenario['id']}|{seed}|traffic|{SCENARIO_VERSION}")
    grid = int(params["grid"])
    horizon = int(params["horizon_steps"])
    probability = float(params["arrival_probability"])
    if demand == "surge":
        probability = min(0.98, probability * 1.4)
    arrival_max = int(params["arrival_max"]) + (1 if demand == "surge" else 0)

    nodes = [f"{x},{y}" for x in range(grid) for y in range(grid)]
    arrivals: list[dict[str, Any]] = []
    for tick in range(1, horizon + 1):
        # Mild rush-hour weighting in the middle of the run.
        peak = 1.15 if horizon * 0.3 <= tick <= horizon * 0.7 else 1.0
        for node in nodes:
            if rng.random() < probability * peak:
                approaches = rng.sample(["N", "S", "E", "W"], 2)
                arrivals.append(
                    {
                        "tick": tick,
                        "intersection": node,
                        "approaches": approaches,
                        "count": rng.randint(1, max(1, arrival_max - 1)),
                    }
                )

    incident_count = int(params.get("incidents", 0))
    if incidents == "none":
        incident_count = 0
    elif incidents == "severe":
        incident_count += 2

    event_plan: list[dict[str, Any]] = []
    for index in range(incident_count):
        at_step = rng.randint(int(horizon * 0.15), int(horizon * 0.8))
        node = rng.choice(nodes)
        approach = rng.choice(["N", "S", "E", "W"])
        event_plan.append(
            {
                "at_step": at_step,
                "type": "incident",
                "intersection": node,
                "approach": approach,
                "duration_ticks": rng.randint(8, 16),
                "severity": "critical",
                "message": f"Lane incident at {node} ({approach} approach).",
            }
        )

    return {
        "scenario_id": scenario["id"],
        "scenario_version": SCENARIO_VERSION,
        "kind": "traffic_control",
        "seed": seed,
        "options": {"demand": demand, "incidents": incidents},
        "grid": grid,
        "horizon_steps": horizon,
        "step_minutes": 1,
        "min_green": int(params["min_green"]),
        "discharge_per_tick": int(params["discharge_per_tick"]),
        "objective": TRAFFIC_OBJECTIVE,
        "arrivals": arrivals,
        "event_plan": sorted(event_plan, key=lambda e: int(e["at_step"])),
    }


def build_config(
    scenario_id: str, seed: int, options: dict[str, Any] | None = None
) -> dict[str, Any]:
    scenario = SCENARIO_BY_ID.get(scenario_id)
    if scenario is None:
        raise KeyError(f"Unknown scenario '{scenario_id}'.")
    allowed = set(scenario["variations"])
    supplied = {k: v for k, v in (options or {}).items() if v is not None}
    unknown = set(supplied) - allowed
    if unknown:
        raise ValueError(f"Variation(s) not supported by this scenario: {sorted(unknown)}")
    for key, value in supplied.items():
        valid = {opt["value"] for opt in VARIATION_SCHEMA[key]["options"]}
        if value not in valid:
            raise ValueError(f"Invalid value '{value}' for variation '{key}'.")
    if scenario["kind"] == "city_logistics":
        return build_city_config(scenario, seed, supplied)
    return build_traffic_config(scenario, seed, supplied)


def build_world(scenario_id: str, seed: int, options: dict[str, Any] | None = None):
    config = build_config(scenario_id, seed, options)
    if config["kind"] == "city_logistics":
        return CityWorld(config)
    return TrafficWorld(config)


def world_from_state(state: dict[str, Any]):
    if state.get("kind") == "city_logistics":
        return CityWorld.from_dict(state)
    if state.get("kind") == "traffic_control":
        return TrafficWorld.from_dict(state)
    raise ValueError(f"Unknown world kind: {state.get('kind')}")


def scenario_public(scenario: dict[str, Any]) -> dict[str, Any]:
    variations = []
    for key in scenario["variations"]:
        schema = VARIATION_SCHEMA[key]
        variations.append(
            {
                "key": key,
                "label": schema["label"],
                "default": scenario["default_options"].get(key, schema["default"]),
                "options": schema["options"],
            }
        )
    metrics = CITY_METRICS if scenario["kind"] == "city_logistics" else TRAFFIC_METRICS
    return {
        "id": scenario["id"],
        "version": scenario["version"],
        "kind": scenario["kind"],
        "name": scenario["name"],
        "tagline": scenario["tagline"],
        "description": scenario["description"],
        "difficulty": scenario["difficulty"],
        "objectives": scenario["objectives"],
        "constraints": scenario["constraints"],
        "variations": variations,
        "default_options": scenario["default_options"],
        "metrics": metrics,
        "horizon_steps": scenario["params"]["horizon_steps"],
        "default_seeds": [7, 11, 23, 42, 91],
    }


def list_scenarios() -> list[dict[str, Any]]:
    return [scenario_public(s) for s in SCENARIOS]