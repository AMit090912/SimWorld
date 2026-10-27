"""City logistics engine rules, events, and determinism."""

from __future__ import annotations

import copy

import pytest

from simworld.engine.actions import Action, ActionFormatError
from simworld.engine.city import CityWorld, edge_id


def city_config(**overrides):
    config = {
        "scenario_id": "test/city",
        "scenario_version": 1,
        "kind": "city_logistics",
        "seed": 1,
        "grid": 3,
        "depot": "0,0",
        "edge_km": 0.5,
        "step_minutes": 2,
        "horizon_steps": 40,
        "blocked_edges": [],
        "objective": "Test objective",
        "fog_radius": None,
        "vehicle": {
            "capacity": 2,
            "fuel_l": 5.0,
            "fuel_capacity_l": 6.0,
            "consumption_l_per_km": 0.5,
        },
        "stations": [{"node": "0,0", "stock_l": 4.0}],
        "packages": [
            {
                "id": "P1",
                "dest": "2,2",
                "dest_label": "Test Drop",
                "deadline_min": 40,
                "weight_kg": 5,
                "origin": "0,0",
            }
        ],
        "event_plan": [],
    }
    config.update(overrides)
    return config


def move(world: CityWorld, target: str):
    return world.apply(Action.parse({"type": "move", "target": target}))


def test_valid_move_updates_position_fuel_and_distance():
    world = CityWorld(city_config())
    result = move(world, "0,1")
    assert result.ok
    assert world.vehicle["node"] == "0,1"
    assert world.vehicle["fuel_l"] == pytest.approx(4.75)
    assert world.stats["distance_km"] == pytest.approx(0.5)
    assert world.step == 1


def test_move_to_non_adjacent_node_is_rejected_and_costs_a_tick():
    world = CityWorld(city_config())
    result = move(world, "2,2")
    assert not result.ok
    assert result.code == "not_adjacent"
    assert world.vehicle["node"] == "0,0"
    assert world.step == 1
    assert world.metrics()["invalid_actions"] == 1


def test_move_without_enough_fuel_is_rejected():
    config = city_config()
    config["vehicle"]["fuel_l"] = 0.05
    world = CityWorld(config)
    result = move(world, "0,1")
    assert not result.ok
    assert result.code == "insufficient_fuel"
    assert world.vehicle["node"] == "0,0"
    assert world.metrics()["invalid_by_reason"] == {"insufficient_fuel": 1}


def test_pickup_then_delivery_hits_deadline():
    world = CityWorld(city_config())
    assert world.apply(Action.parse({"type": "pickup", "package_id": "P1"})).ok
    for target in ["0,1", "1,1", "2,1", "2,2"]:
        assert move(world, target).ok, target
    result = world.apply(Action.parse({"type": "deliver", "package_id": "P1"}))
    assert result.ok
    assert world.packages["P1"]["status"] == "delivered"
    assert world.packages["P1"]["late"] is False
    assert world.metrics()["packages_delivered"] == 1
    assert world.status == "finished"
    assert world.terminal_reason == "all_delivered"


def test_delivery_after_deadline_is_late():
    config = city_config()
    config["packages"][0]["deadline_min"] = 2
    world = CityWorld(config)
    world.apply(Action.parse({"type": "pickup", "package_id": "P1"}))
    for target in ["0,1", "1,1", "2,1", "2,2"]:
        move(world, target)
    result = world.apply(Action.parse({"type": "deliver", "package_id": "P1"}))
    assert result.ok
    assert result.details["late"] is True
    assert world.metrics()["on_time_rate"] == 0.0


def test_pickup_requires_depot_and_capacity():
    world = CityWorld(city_config())
    move(world, "0,1")
    remote = world.apply(Action.parse({"type": "pickup", "package_id": "P1"}))
    assert remote.code == "not_at_depot"

    config = city_config()
    config["packages"].append(
        {"id": "P2", "dest": "1,2", "dest_label": "Other", "deadline_min": 40}
    )
    config["packages"].append(
        {"id": "P3", "dest": "2,1", "dest_label": "Third", "deadline_min": 40}
    )
    world = CityWorld(config)
    result = world.apply(
        Action.parse({"type": "pickup", "package_ids": ["P1", "P2", "P3"]})
    )
    assert not result.ok
    assert result.code == "capacity_exceeded"


def test_delivery_requires_cargo_and_location():
    world = CityWorld(city_config())
    assert world.apply(Action.parse({"type": "deliver", "package_id": "P1"})).code == "package_not_in_cargo"
    world.apply(Action.parse({"type": "pickup", "package_id": "P1"}))
    assert world.apply(Action.parse({"type": "deliver", "package_id": "P1"})).code == "wrong_location"


def test_refuel_transfers_stock_and_caps_at_capacity():
    world = CityWorld(city_config())
    move(world, "0,1")
    move(world, "0,0")
    world.vehicle["fuel_l"] = 2.0
    result = world.apply(Action.parse({"type": "refuel", "amount": 5}))
    assert result.ok
    assert world.vehicle["fuel_l"] == pytest.approx(6.0)
    assert world.stations["0,0"] == pytest.approx(0.0)
    assert world.stats["fuel_refueled_l"] == pytest.approx(4.0)


def test_scheduled_closure_blocks_route():
    config = city_config()
    config["event_plan"] = [
        {
            "at_step": 1,
            "type": "road_closure",
            "edges": [edge_id("0,1", "0,2")],
            "message": "test closure",
        }
    ]
    world = CityWorld(config)
    assert move(world, "0,1").ok
    assert world.edges[edge_id("0,1", "0,2")]["open"] is False
    blocked = move(world, "0,2")
    assert blocked.code == "road_closed"
    assert world.events[0]["type"] == "road_closure"


def test_live_injection_and_reopen():
    world = CityWorld(city_config())
    record = world.inject(
        {
            "type": "road_closure",
            "edges": [edge_id("0,0", "0,1")],
            "message": "live",
        }
    )
    assert record is not None
    assert move(world, "0,1").code == "road_closed"
    world.inject({"type": "road_reopen", "edges": [edge_id("0,0", "0,1")]})
    assert move(world, "0,1").ok


def test_deadline_change_event():
    config = city_config()
    config["event_plan"] = [
        {"at_step": 1, "type": "deadline_change", "package_id": "P1", "delta_min": -15}
    ]
    world = CityWorld(config)
    assert move(world, "0,1").ok
    assert world.packages["P1"]["deadline_min"] == 25


def test_horizon_terminates_run():
    world = CityWorld(city_config(horizon_steps=2))
    move(world, "0,1")
    move(world, "0,0")
    assert world.status == "finished"
    assert world.terminal_reason == "horizon_reached"


def test_fog_limits_visible_closures():
    config = city_config(fog_radius=1)
    world = CityWorld(config)
    world.inject(
        {
            "type": "road_closure",
            "edges": [edge_id("2,1", "2,2")],
            "message": "far closure",
        }
    )
    assert world.visible_closed_edges() == []
    move(world, "0,1")
    move(world, "1,1")
    move(world, "2,1")
    assert edge_id("2,1", "2,2") in world.visible_closed_edges()


def test_identical_actions_reproduce_identical_state():
    scripts = [
        {"type": "pickup", "package_id": "P1"},
        {"type": "move", "target": "0,1"},
        {"type": "move", "target": "1,1"},
        {"type": "move", "target": "2,1"},
        {"type": "move", "target": "2,2"},
        {"type": "deliver", "package_id": "P1"},
    ]
    a = CityWorld(copy.deepcopy(city_config()))
    b = CityWorld(copy.deepcopy(city_config()))
    for script in scripts:
        a.apply(Action.parse(script))
        b.apply(Action.parse(script))
    assert a.state_hash() == b.state_hash()
    assert a.to_dict()["packages"] == b.to_dict()["packages"]

    c = CityWorld(copy.deepcopy(city_config()))
    c.apply(Action.parse({"type": "wait"}))
    c.apply(Action.parse(scripts[0]))
    for script in scripts[1:]:
        c.apply(Action.parse(script))
    assert c.state_hash() != a.state_hash()


def test_action_contract_rejects_unknown_fields():
    with pytest.raises(ActionFormatError) as exc:
        Action.parse({"type": "move", "target": "1,0", "teleport": True})
    assert exc.value.code == "malformed_action"
    with pytest.raises(ActionFormatError):
        Action.parse({"type": "explode"})
    with pytest.raises(ActionFormatError):
        Action.parse({"type": "pickup"})
    with pytest.raises(ActionFormatError):
        Action.parse({"type": "move", "target": "x" * 200})


def test_snapshot_is_ground_truth_and_serialisable():
    import json

    world = CityWorld(city_config())
    move(world, "0,1")
    snapshot = world.snapshot()
    json.dumps(snapshot)
    assert snapshot["vehicle"]["node"] == "0,1"
    assert snapshot["grid"] == 3
    assert len(snapshot["edges"]) == 12
    assert snapshot["state_hash"] == world.state_hash()