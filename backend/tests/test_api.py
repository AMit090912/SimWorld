"""HTTP API integration tests against the real application."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from simworld.api.app import create_app
from simworld.config import Settings


def poll_run(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["state"]["status"] != "running":
            return payload
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_scenarios_and_metrics(client: TestClient):
    health = client.get("/api/health").json()
    assert health["ok"] is True

    scenarios = client.get("/api/scenarios").json()["scenarios"]
    assert len(scenarios) == 6
    kinds = {s["kind"] for s in scenarios}
    assert kinds == {"city_logistics", "traffic_control"}
    for scenario in scenarios:
        assert scenario["objectives"] and scenario["constraints"]

    detail = client.get("/api/scenarios/city-logistics/standard")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Riverside Standard Run"

    preview = client.get("/api/scenarios/city-logistics/standard/preview?seed=3").json()
    assert preview["snapshot"]["seed"] == 3
    assert len(preview["snapshot"]["edges"]) > 50

    metrics = client.get("/api/metrics").json()["metrics"]
    keys = {m["key"] for m in metrics}
    assert {"completion_rate", "invalid_actions", "agent_latency_ms", "avg_wait_ticks"} <= keys

    agents = client.get("/api/agents").json()
    assert len(agents["builtin"]) == 5
    assert {mode["type"] for mode in agents["modes"]} == {"external", "llm"}


def test_missing_model_credentials_are_reported_not_faked(client: TestClient):
    status = client.get("/api/agents/llm/status").json()
    assert status["base_url"] == "http://127.0.0.1:9/v1"
    assert status["api_key_configured"] is False
    assert status["probe"]["available"] is False
    assert "error" in status["probe"]


def test_run_create_step_start_and_replay(client: TestClient):
    created = client.post(
        "/api/runs",
        json={
            "scenario_id": "city-logistics/standard",
            "seed": 7,
            "agent": {"type": "builtin", "id": "city-baseline"},
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    run_id = payload["run"]["id"]
    assert payload["state"]["step"] == 0
    assert payload["run"]["config"]["seed"] == 7

    stepped = client.post(f"/api/runs/{run_id}/step").json()
    assert stepped["state"]["step"] == 1
    assert stepped["last_step"]["ok"] is True

    started = client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
    assert started.status_code == 200
    final = poll_run(client, run_id)
    assert final["run"]["status"] == "finished"
    assert final["evaluation"]["packages_delivered"] == 7
    assert final["evaluation"]["score"] > 0

    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert replay["step_count"] == final["state"]["step"]
    assert replay["steps"][0]["action"] is not None
    assert replay["initial_state"]["step"] == 0
    assert replay["evaluation"]["score"] == final["evaluation"]["score"]


def test_pause_and_reset_endpoints(client: TestClient):
    created = client.post(
        "/api/runs",
        json={"scenario_id": "city-logistics/disruption-storm", "seed": 11,
              "agent": {"type": "builtin", "id": "city-greedy"}},
    ).json()
    run_id = created["run"]["id"]
    client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 250})
    time.sleep(0.4)
    paused = client.post(f"/api/runs/{run_id}/pause").json()
    assert paused["run"]["status"] in {"paused", "finished"}
    reset = client.post(f"/api/runs/{run_id}/reset").json()
    assert reset["run"]["status"] == "ready"
    assert reset["state"]["step"] == 0
    assert reset["state"]["metrics"]["invalid_actions"] == 0


def test_disruption_endpoint_changes_state_and_event_feed(client: TestClient):
    created = client.post(
        "/api/runs",
        json={"scenario_id": "city-logistics/standard", "seed": 7,
              "agent": {"type": "builtin", "id": "city-baseline"}},
    ).json()
    run_id = created["run"]["id"]
    client.post(f"/api/runs/{run_id}/step")
    disrupted = client.post(f"/api/runs/{run_id}/disrupt", json={"type": "road_closure"})
    assert disrupted.status_code == 200, disrupted.text
    data = disrupted.json()
    assert data["injected"]["type"] == "road_closure"
    assert data["injected"]["source"] == "live"
    assert any(not edge["open"] for edge in data["state"]["edges"])
    assert data["evaluation"]["disruption_count"] >= 1

    traffic = client.post(
        "/api/runs",
        json={"scenario_id": "traffic-control/steady", "seed": 7,
              "agent": {"type": "builtin", "id": "traffic-adaptive"}},
    ).json()
    traffic_id = traffic["run"]["id"]
    client.post(f"/api/runs/{traffic_id}/step")
    incident = client.post(f"/api/runs/{traffic_id}/disrupt", json={"type": "incident"})
    assert incident.status_code == 200
    assert incident.json()["injected"]["type"] == "incident"


def test_agent_connection_test_endpoint(client: TestClient):
    ok = client.post(
        "/api/agents/test",
        json={
            "scenario_id": "city-logistics/standard",
            "agent": {"type": "builtin", "id": "city-baseline"},
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["engine_accepted"] is True
    assert body["action_was_offered"] is True

    missing_url = client.post(
        "/api/agents/test", json={"agent": {"type": "external"}}
    )
    assert missing_url.status_code == 400
    assert missing_url.json()["code"] == "invalid_agent"

    blocked = client.post(
        "/api/agents/test",
        json={"agent": {"type": "external", "url": "http://10.0.0.1/agent"}},
    )
    assert blocked.status_code == 200
    assert blocked.json()["ok"] is False
    assert blocked.json()["code"] == "endpoint_blocked"


def test_experiment_endpoint_aggregates_real_runs(client: TestClient):
    response = client.post(
        "/api/experiments",
        json={
            "scenario_id": "city-logistics/standard",
            "seeds": [7, 11],
            "agents": [
                {"type": "builtin", "id": "city-baseline"},
                {"type": "builtin", "id": "city-greedy"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    experiment_id = response.json()["id"]
    deadline = time.time() + 90
    final = None
    while time.time() < deadline:
        current = client.get(f"/api/experiments/{experiment_id}").json()
        if current["status"] in {"finished", "failed"}:
            final = current
            break
        time.sleep(0.1)
    assert final is not None
    assert final["status"] == "finished", final.get("error")
    assert final["completed_runs"] == 4
    assert final["aggregate"]["overall"]["runs"] == 4
    assert len(final["aggregate"]["by_agent"]) == 2
    for run in final["aggregate"]["runs"]:
        assert run["metrics"]["score"] is not None
        assert run["metrics"]["steps"] > 0


def test_error_responses_are_clear(client: TestClient):
    assert client.get("/api/runs/doesnotexist").status_code == 404
    assert client.get("/api/scenarios/unknown/scenario").status_code == 404
    bad = client.post("/api/runs", json={"scenario_id": "nope/nope"})
    assert bad.status_code == 400
    assert "Unknown scenario" in bad.json()["detail"]
    invalid_seed = client.post(
        "/api/runs", json={"scenario_id": "city-logistics/standard", "seed": -5}
    )
    assert invalid_seed.status_code == 422
    bad_variation = client.post(
        "/api/runs",
        json={
            "scenario_id": "city-logistics/standard",
            "options": {"visibility": "nonsense"},
        },
    )
    assert bad_variation.status_code == 400
    assert "Invalid value" in bad_variation.json()["detail"]


def test_payload_limit(client: TestClient):
    huge = "x" * (300 * 1024)
    response = client.post(
        "/api/runs",
        content=b'{"scenario_id":"' + huge.encode() + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_run_history_and_stats(client: TestClient):
    created = client.post(
        "/api/runs",
        json={"scenario_id": "traffic-control/steady", "seed": 7,
              "agent": {"type": "builtin", "id": "traffic-adaptive"}},
    ).json()
    run_id = created["run"]["id"]
    client.post(f"/api/runs/{run_id}/start", json={"delay_ms": 0})
    final = poll_run(client, run_id)
    assert final["state"]["terminal_reason"] == "horizon_reached"

    runs = client.get("/api/runs").json()
    assert runs["total"] >= 1
    assert runs["runs"][0]["scenario_id"] == "traffic-control/steady"
    assert "state" not in runs["runs"][0]

    stats = client.get("/api/stats").json()
    assert stats["runs"] >= 1
    assert stats["scenarios"] == 6


def test_spa_fallback_never_serves_files_outside_static_dir(tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>app shell</html>", encoding="utf-8")
    (static / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")

    settings = Settings(
        db_path=str(tmp_path / "api.db"),
        environment="production",
        allow_loopback_agents=False,
        max_agent_timeout_ms=10000,
        llm_base_url="http://127.0.0.1:11434/v1",
        llm_model="test-model",
        llm_api_key=None,
        llm_provider="openai_compatible",
        llm_timeout_s=5.0,
        cors_origins=(),
        static_dir=str(static),
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            asset = client.get("/app.js")
            assert asset.status_code == 200
            assert "console.log" in asset.text

            for path in ("/..%2fsecret.txt", "/%2e%2e/secret.txt"):
                escaped = client.get(path)
                assert escaped.status_code == 200
                assert "SECRET" not in escaped.text
                assert "app shell" in escaped.text
    finally:
        app.state.store.close()