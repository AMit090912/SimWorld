"""Live disruption behavior and validation."""

from __future__ import annotations

import pytest

from simworld.service import RunService


def create(service: RunService, scenario_id: str = "city-logistics/standard", agent_id: str = "city-baseline") -> str:
    return service.create_run(
        {
            "scenario_id": scenario_id,
            "seed": 7,
            "agent": {"type": "builtin", "id": agent_id},
        }
    )["run"]["id"]


def test_deadline_change_updates_package_and_event(service: RunService):
    run_id = create(service)
    service.step(run_id)
    before = service.get_run(run_id)
    injected = service.inject_disruption(run_id, {"type": "deadline_change", "delta_min": -7})
    record = injected["injected"]
    package_id = record["payload"]["package_id"]
    old = next(p for p in before["state"]["packages"] if p["id"] == package_id)["deadline_min"]
    updated = next(p for p in injected["state"]["packages"] if p["id"] == package_id)
    assert record["type"] == "deadline_change"
    assert record["source"] == "live"
    assert updated["deadline_min"] == max(0, old - 7)
    assert any(event["type"] == "deadline_change" for event in injected["state"]["events"])


def test_fuel_cut_empties_a_real_station(service: RunService):
    run_id = create(service)
    service.step(run_id)
    injected = service.inject_disruption(run_id, {"type": "fuel_cut"})
    record = injected["injected"]
    node = record["payload"]["node"]
    station = next(s for s in injected["state"]["stations"] if s["node"] == node)
    assert record["type"] == "station_stock"
    assert station["stock_l"] == 0.0
    assert any(event["type"] == "station_stock" for event in injected["state"]["events"])


def test_traffic_incident_is_applied(service: RunService):
    run_id = create(service, "traffic-control/steady", "traffic-adaptive")
    service.step(run_id)
    injected = service.inject_disruption(run_id, {"type": "incident", "duration_ticks": 3})
    record = injected["injected"]
    assert record["type"] == "incident"
    assert record["payload"]["intersection"] in {i["id"] for i in injected["state"]["intersections"]}
    assert injected["state"]["incidents"]


def test_traffic_surge_adds_queues(service: RunService):
    run_id = create(service, "traffic-control/steady", "traffic-adaptive")
    service.step(run_id)
    before = sum(
        sum(intersection["queues"].values())
        for intersection in service.get_run(run_id)["state"]["intersections"]
    )
    injected = service.inject_disruption(run_id, {"type": "surge", "count": 2})
    record = injected["injected"]
    after = sum(
        sum(intersection["queues"].values())
        for intersection in injected["state"]["intersections"]
    )
    assert record["type"] == "surge"
    assert after - before == 8
    assert any(event["type"] == "surge" for event in injected["state"]["events"])


def test_closure_changes_the_agent_route(service: RunService):
    run_id = create(service)
    service.step(run_id)
    injected = service.inject_disruption(
        run_id, {"type": "road_closure", "edges": ["0,0|0,1"]}
    )
    edge = next(e for e in injected["state"]["edges"] if e["id"] == "0,0|0,1")
    assert edge["open"] is False
    next_step = service.step(run_id)
    assert next_step["last_step"]["ok"] is True
    assert next_step["last_step"]["action"]["type"] == "move"
    assert next_step["last_step"]["action"]["target"] != "0,1"


def test_invalid_disruptions_are_rejected_without_state_change(service: RunService):
    run_id = create(service)
    service.step(run_id)
    before = service.get_run(run_id)["state"]["state_hash"]
    with pytest.raises(ValueError):
        service.inject_disruption(run_id, {"type": "bogus"})
    with pytest.raises(ValueError):
        service.inject_disruption(
            run_id, {"type": "road_closure", "edges": ["not-a-road"]}
        )
    assert service.get_run(run_id)["state"]["state_hash"] == before


def test_traffic_only_disruptions_are_rejected_on_city(service: RunService):
    run_id = create(service)
    service.step(run_id)
    with pytest.raises(ValueError):
        service.inject_disruption(run_id, {"type": "incident"})
    assert not any(
        event["type"] == "incident"
        for event in service.get_run(run_id)["state"]["events"]
    )
