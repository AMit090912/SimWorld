"""Full-run determinism and recorded configuration."""

from __future__ import annotations

from simworld.service import RunService


def run_to_completion(
    service: RunService,
    *,
    scenario_id: str = "city-logistics/standard",
    seed: int = 7,
    agent_id: str = "city-baseline",
    options: dict[str, str] | None = None,
) -> tuple[dict, dict, dict]:
    created = service.create_run(
        {
            "scenario_id": scenario_id,
            "seed": seed,
            "options": options or {},
            "agent": {"type": "builtin", "id": agent_id},
        }
    )
    run_id = created["run"]["id"]
    service._run_to_completion(run_id)
    final = service.get_run(run_id)
    replay = service.replay(run_id)
    return created, final, replay


def actions(replay: dict) -> list[dict]:
    return [step["action"] for step in replay["steps"]]


def stable_evaluation(evaluation: dict) -> dict:
    return {
        key: value
        for key, value in evaluation.items()
        if key not in {"agent_latency_ms", "agent_latency_p95_ms"}
    }


def deterministic_metrics(replay: dict) -> dict:
    evaluation = replay["evaluation"]
    metrics = evaluation
    return {
        "steps": replay["step_count"],
        "completion_rate": metrics["completion_rate"],
        "on_time_rate": metrics["on_time_rate"],
        "packages_delivered": metrics["packages_delivered"],
        "packages_late": metrics["packages_late"],
        "fuel_consumed_l": metrics["fuel_consumed_l"],
        "distance_km": metrics["distance_km"],
        "invalid_actions": metrics["invalid_actions"],
        "score": evaluation["score"],
        "components": evaluation["score_components"],
    }


def test_same_seed_and_agent_reproduce_identical_run(service: RunService):
    first_created, first_final, first_replay = run_to_completion(service)
    second_created, second_final, second_replay = run_to_completion(service)

    assert first_created["state"]["state_hash"] == second_created["state"]["state_hash"]
    assert actions(first_replay) == actions(second_replay)
    assert [
        step["state"]["state_hash"] for step in first_replay["steps"]
    ] == [
        step["state"]["state_hash"] for step in second_replay["steps"]
    ]
    assert first_final["state"]["state_hash"] == second_final["state"]["state_hash"]
    assert deterministic_metrics(first_replay) == deterministic_metrics(second_replay)
    assert stable_evaluation(first_final["evaluation"]) == stable_evaluation(
        second_final["evaluation"]
    )


def test_different_seed_changes_initial_state_and_run(service: RunService):
    first_created, _, _ = run_to_completion(service, seed=7)
    second_created, _, _ = run_to_completion(service, seed=8)

    assert first_created["state"]["state_hash"] != second_created["state"]["state_hash"]
    assert first_created["run"]["seed"] == 7
    assert second_created["run"]["seed"] == 8


def test_seed_and_options_are_recorded(service: RunService):
    created, final, _ = run_to_completion(
        service, seed=23, options={"fuel_supply": "scarce"}
    )
    run = final["run"]
    assert run["seed"] == 23
    assert run["options"]["fuel_supply"] == "scarce"
    assert run["config"]["options"]["fuel_supply"] == "scarce"
    assert created["state"]["seed"] == 23
    assert created["state"]["vehicle"]["fuel_capacity_l"] == 12.0
    assert created["state"]["vehicle"]["fuel_l"] == 6.5
