"""API validation, concurrency, and failure behavior."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def wait_finished(client: TestClient, run_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["run"]["status"] in {"finished", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def create(client: TestClient, scenario_id: str = "city-logistics/standard") -> str:
    response = client.post(
        "/api/runs",
        json={
            "scenario_id": scenario_id,
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run"]["id"]


def test_malformed_and_incomplete_requests_are_rejected(client: TestClient):
    assert client.post("/api/runs", content=b"{", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/runs", json={}).status_code == 422
    assert client.post("/api/experiments", json={}).status_code == 422
    assert client.post("/api/runs", json={"scenario_id": "nope/nope"}).status_code == 400
    assert client.get("/api/runs/not-a-run").status_code == 404
    assert client.post("/api/runs/not-a-run/step").status_code == 404
    assert client.put("/api/health").status_code == 405
    assert client.get("/api/nope").status_code == 404


def test_invalid_agent_and_experiment_configuration_are_rejected(client: TestClient):
    bad = client.post(
        "/api/runs",
        json={
            "scenario_id": "city-logistics/standard",
            "agent": {"type": "external", "url": "file:///etc/passwd"},
        },
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_endpoint"

    too_many = client.post(
        "/api/experiments",
        json={
            "scenario_id": "city-logistics/standard",
            "seeds": list(range(1, 12)),
            "agents": [{"type": "builtin", "id": "city-baseline"}],
        },
    )
    assert too_many.status_code == 422


def test_disruption_validation_does_not_mutate_state(client: TestClient):
    run_id = create(client)
    ready_hash = client.get(f"/api/runs/{run_id}").json()["state"]["state_hash"]
    stopped = client.post(f"/api/runs/{run_id}/disrupt", json={"type": "bogus"})
    assert stopped.status_code in {400, 200}
    if stopped.status_code == 200:
        assert stopped.json()["injected"]["type"] == "bogus"
    client.post(f"/api/runs/{run_id}/step")
    before = client.get(f"/api/runs/{run_id}").json()["state"]["state_hash"]
    unknown = client.post(
        f"/api/runs/{run_id}/disrupt",
        json={"type": "road_closure", "edges": ["not-a-road"]},
    )
    assert unknown.status_code == 400
    assert client.get(f"/api/runs/{run_id}").json()["state"]["state_hash"] == before
    assert ready_hash


def test_two_runs_can_execute_concurrently_without_cross_talk(client: TestClient):
    first = create(client)
    second = create(client, "city-logistics/rush-hour")
    assert first != second
    assert client.post(f"/api/runs/{first}/start", json={"delay_ms": 0}).status_code == 200
    assert client.post(f"/api/runs/{second}/start", json={"delay_ms": 0}).status_code == 200
    first_final = wait_finished(client, first)
    second_final = wait_finished(client, second)
    assert first_final["state"]["scenario_id"] == "city-logistics/standard"
    assert second_final["state"]["scenario_id"] == "city-logistics/rush-hour"
    assert first_final["state"]["state_hash"] != second_final["state"]["state_hash"]
    assert first_final["run"]["id"] != second_final["run"]["id"]


def test_repeated_start_does_not_duplicate_steps(client: TestClient):
    run_id = create(client)
    client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
    client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
    final = wait_finished(client, run_id)
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert final["run"]["status"] == "finished"
    assert final["run"]["steps"] == replay["step_count"]
    assert len({step["step"] for step in replay["steps"]}) == len(replay["steps"])


def test_invalid_json_does_not_expose_stack_trace(client: TestClient):
    response = client.post(
        "/api/runs",
        content=b'{"scenario_id": "city-logistics/standard",',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text
    assert "internal" not in response.text.lower()


def test_pause_resume_reset_and_restart_a_run(client: TestClient):
    run_id = create(client)
    client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 50})
    deadline = time.time() + 10
    while time.time() < deadline:
        current = client.get(f"/api/runs/{run_id}").json()
        if current["run"]["steps"] >= 1:
            break
        time.sleep(0.02)
    paused = client.post(f"/api/runs/{run_id}/pause").json()
    assert paused["run"]["status"] in {"paused", "finished"}
    if paused["run"]["status"] == "paused":
        paused_steps = paused["run"]["steps"]
        resumed = client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
        assert resumed.status_code == 200
        final = wait_finished(client, run_id)
        assert final["run"]["status"] == "finished"
        assert final["run"]["steps"] >= paused_steps

    reset = client.post(f"/api/runs/{run_id}/reset").json()
    assert reset["run"]["status"] == "ready"
    assert reset["state"]["step"] == 0
    assert reset["state"]["vehicle"]["cargo"] == []
    assert client.get(f"/api/runs/{run_id}/replay").json()["step_count"] == 0

    restarted = client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
    assert restarted.status_code == 200
    final_again = wait_finished(client, run_id)
    assert final_again["run"]["status"] == "finished"
    assert final_again["evaluation"]["packages_delivered"] == 7
