"""Agent adapters: protocol validation, failures, timeouts, SSRF, and fallbacks."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from simworld.agents.base import AgentContext, AgentError
from simworld.agents.builtins import make_builtin
from simworld.agents.external import ExternalAgent, validate_endpoint
from simworld.agents.llm import LLMAgent
from simworld.engine.actions import Action
from simworld.engine.scenarios import build_world


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silence test server logs
        pass

    def _send(self, code: int, body: bytes, content_type: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send(200, json.dumps({"data": [{"id": "stub-model"}]}).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        path = self.path
        if path.startswith("/valid"):
            action = body["legal_actions"][0]
            self._send(200, json.dumps({"action": action, "reasoning": "first legal"}).encode())
        elif path.startswith("/malformed"):
            self._send(200, b"not json", "text/plain")
        elif path.startswith("/missing-action"):
            self._send(200, json.dumps({"reasoning": "forgot"}).encode())
        elif path.startswith("/bad-action"):
            self._send(200, json.dumps({"action": {"type": "teleport"}}).encode())
        elif path.startswith("/rule-invalid"):
            self._send(
                200,
                json.dumps(
                    {"action": {"type": "move", "target": "7,7"}, "reasoning": "teleport-ish"}
                ).encode(),
            )
        elif path.startswith("/timeout"):
            time.sleep(0.9)
            self._send(200, json.dumps({"action": {"type": "wait"}}).encode())
        elif path.startswith("/error"):
            self._send(500, b'{"error":"boom"}')
        elif path.startswith("/huge"):
            payload = json.dumps({"action": {"type": "wait"}, "reasoning": "x" * 70000}).encode()
            self._send(200, payload)
        elif path.startswith("/chat/pickup"):
            content = json.dumps(
                {"action": {"type": "pickup", "package_ids": ["PKG-01"]}, "reasoning": "earliest deadline"}
            )
            self._send(
                200,
                json.dumps(
                    {"choices": [{"message": {"role": "assistant", "content": content}}]}
                ).encode(),
            )
        elif path.startswith("/chat/completions"):
            content = json.dumps(
                {"action": {"type": "wait"}, "reasoning": "model says wait"}
            )
            self._send(
                200,
                json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": content}}
                        ]
                    }
                ).encode(),
            )
        elif path.startswith("/chat-bad"):
            self._send(
                200,
                json.dumps(
                    {"choices": [{"message": {"content": "I refuse to output JSON."}}]}
                ).encode(),
            )
        else:
            self._send(404, b"{}")


@pytest.fixture(scope="module")
def stub_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def city_world_obs():
    world = build_world("city-logistics/standard", 7, None)
    observation = world.observation()
    return world, observation, observation["legal_actions"]


def test_external_agent_returns_valid_action(stub_server, city_world_obs):
    world, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/valid", timeout_ms=1000, allow_loopback=True)
    decision = agent.decide(observation, legal, AgentContext("run", 0))
    assert decision.action in legal
    assert decision.latency_ms > 0
    assert decision.reasoning == "first legal"


def test_external_malformed_json_is_rejected(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/malformed", allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_bad_json"


def test_external_missing_action_is_rejected(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/missing-action", allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_bad_response"


def test_external_action_schema_is_enforced(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/bad-action", allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_bad_action"


def test_rule_invalid_action_reaches_engine_and_is_blocked(stub_server, city_world_obs):
    world, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/rule-invalid", allow_loopback=True)
    decision = agent.decide(observation, legal, AgentContext("run", 0))
    assert decision.action == {"type": "move", "target": "7,7"}
    before = world.state_hash()
    result = world.apply(Action.parse(decision.action))
    assert not result.ok
    assert result.code in {"not_adjacent", "road_closed"}
    assert world.state_hash() != before  # only the clock/step advanced
    assert world.vehicle["node"] == "0,0"
    assert world.metrics()["invalid_actions"] == 1


def test_external_timeout(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/timeout", timeout_ms=250, allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_timeout"


def test_external_http_error(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/error", allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_http_error"


def test_external_oversized_response(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url=f"{stub_server}/huge", allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_response_too_large"


def test_unreachable_agent_reports_cleanly(city_world_obs):
    _, observation, legal = city_world_obs
    agent = ExternalAgent(url="http://127.0.0.1:1/agent", timeout_ms=300, allow_loopback=True)
    with pytest.raises(AgentError) as exc:
        agent.decide(observation, legal, AgentContext("run", 0))
    assert exc.value.code == "agent_unreachable"


def test_loopback_and_metadata_targets_are_blocked(stub_server):
    with pytest.raises(AgentError) as exc:
        validate_endpoint(stub_server + "/valid", allow_loopback=False)
    assert exc.value.code == "endpoint_blocked"
    with pytest.raises(AgentError) as exc:
        validate_endpoint("http://169.254.169.254/latest/meta-data", allow_loopback=True)
    assert exc.value.code == "endpoint_blocked"
    with pytest.raises(AgentError):
        validate_endpoint("http://10.0.0.5/agent", allow_loopback=True)
    with pytest.raises(AgentError):
        validate_endpoint("file:///etc/passwd", allow_loopback=True)
    with pytest.raises(AgentError):
        validate_endpoint("http://user:pass@example.com/agent", allow_loopback=True)


def test_llm_agent_uses_openai_compatible_response(stub_server, city_world_obs):
    """The stub returns a wait action; the supervisor honours it at the depot."""
    _, observation, legal = city_world_obs
    agent = LLMAgent(
        model="stub-model",
        base_url=f"{stub_server}/chat/pickup",
        api_key="test-key",
        timeout_s=3,
    )
    decision = agent.decide(observation, legal, AgentContext("run", 0))
    assert decision.action == {"type": "pickup", "package_ids": ["PKG-01"]}
    assert decision.fallback_used is False
    assert decision.reasoning == "earliest deadline"
    assert decision.latency_ms > 0


def test_llm_agent_falls_back_honestly(stub_server, city_world_obs):
    _, observation, legal = city_world_obs
    agent = LLMAgent(
        model="stub-model",
        base_url=f"{stub_server}/chat-bad",
        api_key=None,
        timeout_s=3,
    )
    decision = agent.decide(observation, legal, AgentContext("run", 0))
    assert decision.fallback_used is True
    assert decision.error
    assert decision.action in legal
    assert "fallback" in (decision.reasoning or "").lower()


def test_builtin_city_agent_completes_standard_run():
    world = build_world("city-logistics/standard", 7, None)
    agent = make_builtin("city-baseline")
    for _ in range(200):
        observation = world.observation()
        decision = agent.decide(observation, observation["legal_actions"], AgentContext("run", world.step))
        world.apply(Action.parse(decision.action))
        if world.status != "running":
            break
    metrics = world.metrics()
    assert metrics["packages_delivered"] == metrics["packages_total"]
    assert metrics["invalid_actions"] == 0


def test_traffic_builtin_agents_are_rule_compliant():
    for agent_id in ("traffic-adaptive", "traffic-fixed"):
        world = build_world("traffic-control/steady", 7, None)
        agent = make_builtin(agent_id)
        for _ in range(150):
            observation = world.observation()
            decision = agent.decide(
                observation, observation["legal_actions"], AgentContext("run", world.step)
            )
            world.apply(Action.parse(decision.action))
            if world.status != "running":
                break
        metrics = world.metrics()
        assert metrics["rule_violations"] == 0
        assert metrics["invalid_actions"] == 0
        assert metrics["steps"] == world.horizon_steps


def test_builtin_agent_rejects_wrong_environment():
    with pytest.raises(KeyError):
        make_builtin("does-not-exist")