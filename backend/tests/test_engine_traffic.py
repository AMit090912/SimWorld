"""Traffic control engine rules and determinism."""

from __future__ import annotations

import copy

import pytest

from simworld.engine.actions import Action
from simworld.engine.traffic import TrafficWorld


def traffic_config(**overrides):
    config = {
        "scenario_id": "test/traffic",
        "scenario_version": 1,
        "kind": "traffic_control",
        "seed": 3,
        "grid": 2,
        "horizon_steps": 12,
        "step_minutes": 1,
        "min_green": 3,
        "discharge_per_tick": 2,
        "objective": "test",
        "arrivals": [],
        "event_plan": [],
    }
    config.update(overrides)
    return config


def test_minimum_green_blocks_early_switch_and_counts_violation():
    world = TrafficWorld(traffic_config())
    result = world.apply(
        Action.parse({"type": "set_phase", "intersection": "0,0", "phase": "EW"})
    )
    assert not result.ok
    assert result.code == "phase_too_soon"
    assert world.metrics()["rule_violations"] == 1
    assert world.signals["0,0"]["phase"] == "NS"


def test_switch_allowed_after_minimum_green():
    world = TrafficWorld(traffic_config())
    for _ in range(3):
        world.apply(Action.parse({"type": "wait"}))
    result = world.apply(
        Action.parse({"type": "set_phase", "intersection": "0,0", "phase": "EW"})
    )
    assert result.ok
    assert world.signals["0,0"]["phase"] == "EW"
    assert world.metrics()["phase_changes"] == 1


def test_green_discharges_and_wait_is_measured():
    config = traffic_config(
        arrivals=[{"tick": 1, "intersection": "0,0", "approaches": ["N"], "count": 2}]
    )
    world = TrafficWorld(config)
    world.apply(Action.parse({"type": "wait"}))
    metrics = world.metrics()
    assert metrics["vehicles_arrived"] == 2
    assert metrics["vehicles_discharged"] == 2
    assert metrics["avg_wait_ticks"] == 0.0
    assert world.queues["0,0"]["N"] == []


def test_wrong_phase_leaves_queue_waiting():
    config = traffic_config(
        arrivals=[{"tick": 1, "intersection": "0,0", "approaches": ["N"], "count": 1}]
    )
    world = TrafficWorld(config)
    world.signals["0,0"]["phase"] = "EW"
    world.apply(Action.parse({"type": "wait"}))
    assert len(world.queues["0,0"]["N"]) == 1
    assert world.metrics()["vehicles_discharged"] == 0


def test_incident_blocks_approach():
    config = traffic_config(
        arrivals=[{"tick": 1, "intersection": "0,0", "approaches": ["N"], "count": 2}],
        event_plan=[
            {
                "at_step": 1,
                "type": "incident",
                "intersection": "0,0",
                "approach": "N",
                "duration_ticks": 4,
                "message": "lane blocked",
            }
        ],
    )
    world = TrafficWorld(config)
    world.apply(Action.parse({"type": "wait"}))
    assert len(world.queues["0,0"]["N"]) == 2
    assert world.metrics()["vehicles_discharged"] == 0
    assert world.active_incidents[0]["approach"] == "N"


def test_horizon_terminates():
    world = TrafficWorld(traffic_config(horizon_steps=2))
    world.apply(Action.parse({"type": "wait"}))
    world.apply(Action.parse({"type": "wait"}))
    assert world.status == "finished"
    assert world.terminal_reason == "horizon_reached"


def test_city_actions_are_rejected_in_traffic_world():
    world = TrafficWorld(traffic_config())
    result = world.apply(Action.parse({"type": "move", "target": "0,1"}))
    assert not result.ok
    assert result.code == "wrong_environment"


def test_traffic_is_deterministic():
    config = traffic_config(
        arrivals=[
            {"tick": 1, "intersection": "0,0", "approaches": ["N"], "count": 2},
            {"tick": 2, "intersection": "0,1", "approaches": ["E"], "count": 1},
        ]
    )
    script = [
        {"type": "wait"},
        {"type": "wait"},
        {"type": "wait"},
        {"type": "set_phase", "intersection": "0,1", "phase": "EW"},
    ]
    a = TrafficWorld(copy.deepcopy(config))
    b = TrafficWorld(copy.deepcopy(config))
    for step in script:
        a.apply(Action.parse(step))
        b.apply(Action.parse(step))
    assert a.state_hash() == b.state_hash()
    assert a.metrics() == b.metrics()


def test_snapshot_contains_signal_truth():
    world = TrafficWorld(traffic_config())
    snapshot = world.snapshot()
    assert snapshot["grid"] == 2
    assert len(snapshot["intersections"]) == 4
    assert {i["phase"] for i in snapshot["intersections"]} == {"NS"}
    assert snapshot["metrics"]["rule_violations"] == 0