"""Service lifecycle, replay, disruption injection, and experiments."""

from __future__ import annotations

import time

import pytest

from simworld.engine.actions import Action
from simworld.engine.scenarios import build_world, world_from_state
from simworld.service import RunService


def wait_until(fn, timeout=30.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not met before timeout")


def test_run_lifecycle_step_pause_reset(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    assert created["run"]["status"] == "ready"
    assert created["state"]["step"] == 0

    stepped = service.step(run_id)
    assert stepped["state"]["step"] == 1
    assert stepped["state"]["vehicle"]["cargo"] != []
    assert service.store.get_steps(run_id)[0]["valid"] is True

    paused = service.pause(run_id)
    assert paused["run"]["status"] in {"paused", "ready"}

    service.reset(run_id)
    reset = service.get_run(run_id)
    assert reset["state"]["step"] == 0
    assert reset["run"]["status"] == "ready"
    assert reset["state"]["vehicle"]["cargo"] == []
    assert service.store.get_steps(run_id) == []


def test_autoplay_finishes_and_persists_metrics(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    service.start(run_id, delay_ms=0)
    final = wait_until(
        lambda: (
            service.get_run(run_id)
            if service.get_run(run_id)["state"]["status"] != "running"
            else None
        )
    )
    assert final["state"]["status"] == "finished"
    assert final["run"]["score"] > 0
    assert final["evaluation"]["packages_delivered"] == 7
    stored = service.store.get_run(run_id)
    assert stored["metrics"]["score"] == final["run"]["score"]
    assert len(service.store.get_steps(run_id)) == final["state"]["step"]


def test_live_disruption_changes_world_and_reset_clears_it(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    service.step(run_id)
    disrupted = service.inject_disruption(run_id, {"type": "road_closure"})
    closed = [
        edge for edge in disrupted["state"]["edges"] if not edge["open"]
    ]
    assert closed, "closure should close at least one road"
    assert disrupted["injected"]["source"] == "live"
    assert any(event["source"] == "live" for event in disrupted["state"]["events"])

    service.reset(run_id)
    after = service.get_run(run_id)
    assert [e for e in after["state"]["edges"] if not e["open"]] == []
    assert after["state"]["events"] == []


def test_replay_reconstructs_exact_transitions(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/disruption-storm",
            "seed": 11,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    service._run_to_completion(run_id)

    replay = service.replay(run_id)
    assert replay["step_count"] > 0
    world = world_from_state(replay["initial_state"])
    for step in replay["steps"]:
        world.apply(Action.parse(step["action"]))
        assert world.state_hash() == step["state"]["state_hash"], step["step"]

    final_snapshot = replay["steps"][-1]["state"]
    assert world.state_hash() == final_snapshot["state_hash"]
    assert world.status != "running"
    assert replay["evaluation"]["score"] > 0


def test_replay_reconstructs_live_disruptions(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    for _ in range(5):
        service.step(run_id)
    injected = service.inject_disruption(run_id, {"type": "road_closure"})
    assert injected["injected"]["source"] == "live"
    for _ in range(8):
        service.step(run_id)

    replay = service.replay(run_id)
    assert replay["live_events"], "live events must be exposed for reconstruction"
    by_step: dict[int, list[dict]] = {}
    for event in replay["live_events"]:
        by_step.setdefault(int(event["at_step"]), []).append(event)

    world = world_from_state(replay["initial_state"])
    for step in replay["steps"]:
        world.apply(Action.parse(step["action"]))
        # The step snapshot was persisted before the between-tick injection, so
        # compare first, then apply any live events recorded at this step.
        assert world.state_hash() == step["state"]["state_hash"], f"step {step['step']} diverged"
        for event in by_step.get(step["step"], []):
            world.inject({k: v for k, v in event.items() if k not in {"at_step", "source"}})

    assert replay["live_events"][0]["at_step"] == 5


def test_same_seed_and_agent_reproduce_identical_initial_state(service: RunService):
    first = service.create_run(
        {"scenario_id": "city-logistics/rush-hour", "seed": 23, "agent": {"type": "builtin", "id": "city-greedy"}}
    )
    second = service.create_run(
        {"scenario_id": "city-logistics/rush-hour", "seed": 23, "agent": {"type": "builtin", "id": "city-greedy"}}
    )
    assert first["state"]["state_hash"] == second["state"]["state_hash"]


def test_different_strategies_diverge_on_same_seed(service: RunService):
    metrics = {}
    for agent_id in ("city-baseline", "city-greedy", "city-blind"):
        created = service.create_run(
            {
                "scenario_id": "city-logistics/standard",
                "seed": 7,
                "agent": {"type": "builtin", "id": agent_id},
            }
        )
        run_id = created["run"]["id"]
        service._run_to_completion(run_id)
        metrics[agent_id] = service.get_run(run_id)["evaluation"]
    assert metrics["city-baseline"]["score"] > metrics["city-blind"]["score"]
    assert metrics["city-blind"]["invalid_actions"] > 0
    assert metrics["city-baseline"]["invalid_actions"] == 0


def test_agent_failure_uses_safe_fallback_without_corrupting_world(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "external", "url": "http://127.0.0.1:1/agent", "timeout_ms": 300},
        }
    )
    run_id = created["run"]["id"]
    result = service.step(run_id)
    assert result["last_step"]["agent_error"]
    assert result["last_step"]["ok"] is True
    assert result["last_step"]["action"]["type"] in {"pickup", "wait"}
    assert result["state"]["vehicle"]["node"] == "0,0"
    assert result["evaluation"]["agent_errors"] == 1
    assert result["evaluation"]["agent_fallbacks"] == 1


def test_agent_unavailable_terminates_after_three_errors(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "external", "url": "http://127.0.0.1:1/agent", "timeout_ms": 300},
        }
    )
    run_id = created["run"]["id"]
    for _ in range(3):
        service.step(run_id)
    snapshot = service.get_run(run_id)
    assert snapshot["state"]["status"] == "failed"
    assert snapshot["state"]["terminal_reason"] == "agent_unavailable"
    assert snapshot["run"]["status"] == "failed"


def test_experiment_runs_all_combinations_and_aggregates(service: RunService):
    experiment = service.create_experiment(
        {
            "scenario_id": "city-logistics/standard",
            "seeds": [7, 11],
            "agents": [
                {"type": "builtin", "id": "city-baseline"},
                {"type": "builtin", "id": "city-greedy"},
            ],
        }
    )
    experiment_id = experiment["id"]

    def finished():
        current = service.get_experiment(experiment_id)
        if current and current["status"] in {"finished", "failed"}:
            return current
        return None

    final = wait_until(finished, timeout=60)
    assert final["status"] == "finished", final.get("error")
    assert final["completed_runs"] == 4
    assert len(final["runs"]) == 4
    assert final["aggregate"]["overall"]["runs"] == 4
    assert len(final["aggregate"]["by_agent"]) == 2
    assert all(run["metrics"]["score"] is not None for run in final["runs"])


def test_scenario_variations_are_applied_and_validated():
    world = build_world(
        "city-logistics/standard",
        7,
        {"fuel_supply": "scarce", "deadline_pressure": "tight", "visibility": "limited"},
    )
    assert world.fog_radius == 2
    assert world.vehicle["fuel_l"] == pytest.approx(6.5)
    assert world.config["options"]["fuel_supply"] == "scarce"

    with pytest.raises(ValueError):
        build_world("city-logistics/standard", 7, {"bogus": "x"})
    with pytest.raises(ValueError):
        build_world("traffic-control/steady", 7, {"fuel_supply": "scarce"})
    with pytest.raises(KeyError):
        build_world("nope/nothing", 7, None)


def test_reload_run_from_database(settings, tempfile_free_store):
    store = tempfile_free_store
    service = RunService(store, settings)
    created = service.create_run(
        {"scenario_id": "city-logistics/standard", "seed": 7, "agent": {"type": "builtin", "id": "city-baseline"}}
    )
    run_id = created["run"]["id"]
    service.step(run_id)

    fresh = RunService(store, settings)
    snapshot = fresh.get_run(run_id)
    assert snapshot["state"]["step"] == 1
    stepped = fresh.step(run_id)
    assert stepped["state"]["step"] == 2