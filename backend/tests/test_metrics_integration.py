"""Metrics must reconcile with recorded transitions, not demo values."""

from __future__ import annotations

import pytest

from simworld.service import RunService


def run_baseline(service: RunService) -> tuple[dict, dict]:
    created = service.create_run(
        {
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        }
    )
    run_id = created["run"]["id"]
    service._run_to_completion(run_id)
    return service.get_run(run_id), service.replay(run_id)


def test_city_metrics_reconcile_with_steps(service: RunService):
    final, replay = run_baseline(service)
    initial = replay["initial_state"]
    config = replay["run"]["config"]
    consumption = float(config["vehicle"]["consumption_l_per_km"])

    node = initial["vehicle"]["node"]
    distance = 0.0
    fuel = 0.0
    moves = 0
    for step in replay["steps"]:
        action = step["action"]
        if not step["valid"] or action["type"] != "move":
            continue
        target = action["target"]
        edge = next(
            (
                edge
                for edge in initial["edges"].values()
                if {edge["a"], edge["b"]} == {node, target}
            ),
            None,
        )
        if edge is None:
            continue
        distance += float(edge["km"])
        fuel += float(edge["km"]) * consumption
        node = target
        moves += 1

    final_state = final["state"]
    metrics = final_state["metrics"]
    packages = final_state["packages"]
    delivered = [p for p in packages if p["status"] == "delivered"]
    on_time = [p for p in delivered if not p["late"]]
    assert metrics["packages_total"] == len(packages) == 7
    assert metrics["packages_delivered"] == len(delivered) == 7
    assert metrics["packages_on_time"] == len(on_time)
    assert metrics["packages_late"] == len(delivered) - len(on_time)
    assert metrics["completion_rate"] == pytest.approx(len(delivered) / len(packages), abs=1e-4)
    assert metrics["on_time_rate"] == pytest.approx(len(on_time) / len(packages), abs=1e-4)
    assert metrics["distance_km"] == pytest.approx(distance, abs=1e-3)
    assert metrics["fuel_consumed_l"] == pytest.approx(fuel, abs=1e-3)
    assert metrics["fuel_remaining_l"] == pytest.approx(final_state["vehicle"]["fuel_l"], abs=1e-3)
    assert metrics["invalid_actions"] == 0
    assert moves > 0

    evaluation = final["evaluation"]
    completion = min(1.0, max(0.0, metrics["completion_rate"]))
    on_time_score = min(1.0, max(0.0, metrics["on_time_rate"]))
    budget = float(config["vehicle"]["fuel_capacity_l"]) * 0.75
    efficiency = min(1.0, max(0.0, 1.0 - metrics["fuel_consumed_l"] / budget))
    compliance = 1.0
    reliability = 1.0
    expected = 100 * (
        0.50 * completion
        + 0.20 * on_time_score
        + 0.15 * efficiency
        + 0.10 * compliance
        + 0.05 * reliability
    )
    assert evaluation["score"] == pytest.approx(expected, abs=0.01)
    assert evaluation["score_components"]["completion"] == pytest.approx(completion, abs=1e-4)
    assert evaluation["score_components"]["on_time"] == pytest.approx(on_time_score, abs=1e-4)
    assert evaluation["score_components"]["fuel_efficiency"] == pytest.approx(efficiency, abs=1e-4)
    assert evaluation == replay["evaluation"]


def test_completed_run_has_consistent_terminal_metadata(service: RunService):
    final, replay = run_baseline(service)
    run = final["run"]
    assert run["status"] == "finished"
    assert run["terminal_reason"] == "all_delivered"
    assert run["steps"] == replay["step_count"] == final["state"]["step"]
    assert run["score"] == final["evaluation"]["score"]
    assert run["duration_ms"] is not None
    assert final["state"]["status"] == "finished"


def test_zero_package_evaluation_is_finite():
    from simworld.evaluation import evaluate_run

    metrics = {
        "packages_total": 0,
        "packages_delivered": 0,
        "packages_on_time": 0,
        "packages_late": 0,
        "completion_rate": 0.0,
        "on_time_rate": 0.0,
        "fuel_consumed_l": 0.0,
        "invalid_actions": 0,
        "invalid_by_reason": {},
        "fuel_remaining_l": 1.0,
    }
    result = evaluate_run("city_logistics", metrics, [], [], [])
    assert result["score"] >= 0
    assert result["score_components"]["completion"] == 0.0
    assert result["failures"] == ["No objective failures recorded."]


def test_traffic_metrics_reconcile_with_engine(service: RunService):
    created = service.create_run(
        {
            "scenario_id": "traffic-control/steady",
            "seed": 7,
            "agent": {"type": "builtin", "id": "traffic-adaptive"},
        }
    )
    run_id = created["run"]["id"]
    service._run_to_completion(run_id)
    final = service.get_run(run_id)
    replay = service.replay(run_id)
    state = final["state"]
    metrics = state["metrics"]
    evaluation = final["evaluation"]

    assert state["status"] == "finished"
    assert state["terminal_reason"] == "horizon_reached"
    assert metrics["steps"] == state["horizon_steps"]
    assert metrics["vehicles_arrived"] > 0
    assert metrics["vehicles_discharged"] > 0
    assert metrics["throughput_rate"] == pytest.approx(
        round(metrics["vehicles_discharged"] / metrics["vehicles_arrived"], 4),
        abs=1e-4,
    )
    assert metrics["avg_wait_ticks"] >= 0
    assert metrics["max_wait_ticks"] >= metrics["avg_wait_ticks"]
    assert metrics["avg_queue_length"] >= 0
    assert metrics["rule_violations"] == 0
    assert metrics["invalid_actions"] == 0
    assert replay["step_count"] == metrics["steps"]
    assert replay["evaluation"] == evaluation

    throughput = min(1.0, max(0.0, metrics["throughput_rate"]))
    wait_score = min(1.0, max(0.0, 1.0 - metrics["avg_wait_ticks"] / 20.0))
    congestion = min(1.0, max(0.0, 1.0 - metrics["avg_queue_length"] / 8.0))
    expected = 100 * (0.45 * throughput + 0.30 * wait_score + 0.15 * congestion + 0.05 + 0.05)
    assert evaluation["score"] == pytest.approx(expected, abs=0.01)
    assert evaluation["score_components"]["throughput"] == pytest.approx(throughput, abs=1e-4)
    assert evaluation["score_components"]["wait"] == pytest.approx(wait_score, abs=1e-4)
    assert evaluation["score_components"]["congestion"] == pytest.approx(congestion, abs=1e-4)
