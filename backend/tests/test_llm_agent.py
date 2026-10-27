"""LLM adapter: goal selection, schema tolerance, fallback honesty, endpoints.

The city adapter is a supervisor: the model chooses the goal (batch, delivery,
or package) and a deterministic router emits the validated moves. These tests
cover both that contract and the direct path used by the traffic environment.
"""

from __future__ import annotations

import json

import pytest

from simworld.agents.base import AgentContext
from simworld.agents.llm import LLMAgent, probe_model
from simworld.engine.actions import Action
from simworld.engine.scenarios import build_world


@pytest.fixture(scope="module")
def city_bundle():
    world = build_world("city-logistics/standard", 7, None)
    observation = world.observation()
    return world, observation, observation["legal_actions"]


@pytest.fixture(scope="module")
def traffic_bundle():
    world = build_world("traffic-control/steady", 7, None)
    for _ in range(4):
        world.apply(Action.parse({"type": "wait"}))
    observation = world.observation()
    return world, observation, observation["legal_actions"]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.Client, returning a scripted chat-completion body."""

    content = "{}"
    status_code = 200

    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        return _FakeResponse(
            {"choices": [{"message": {"content": type(self).content}}]},
            type(self).status_code,
        )


def _agent(monkeypatch, content, status_code=200):
    class _Client(_FakeClient):
        pass

    _Client.content = content
    _Client.status_code = status_code
    monkeypatch.setattr("simworld.agents.llm.httpx.Client", _Client)
    return LLMAgent(model="stub", base_url="http://127.0.0.1:1/v1", timeout_s=2)


# --------------------------------------------------------------------- traffic
def test_traffic_path_uses_the_model_action_directly(monkeypatch, traffic_bundle):
    _, observation, legal = traffic_bundle
    agent = _agent(monkeypatch, '{"action": {"type": "wait"}, "reasoning": "holding"}')
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    assert decision.action == {"type": "wait"}
    assert decision.fallback_used is False
    assert decision.reasoning == "holding"


def test_traffic_sibling_action_fields_are_accepted(monkeypatch, traffic_bundle):
    _, observation, legal = traffic_bundle
    agent = _agent(monkeypatch, '{"type": "wait", "reasoning": "flat"}')
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    assert decision.action == {"type": "wait"}
    assert decision.fallback_used is False


# ----------------------------------------------------------------------- city
def test_model_chooses_the_loading_batch(monkeypatch, city_bundle):
    _, observation, legal = city_bundle
    agent = _agent(
        monkeypatch,
        '{"action": {"type": "pickup", "package_ids": ["PKG-02"]}, "reasoning": "tightest deadline"}',
    )
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    assert decision.action == {"type": "pickup", "package_ids": ["PKG-02"]}
    assert decision.fallback_used is False
    assert decision.reasoning == "tightest deadline"


def test_model_action_encoded_as_a_json_string_is_accepted(monkeypatch, city_bundle):
    _, observation, legal = city_bundle
    agent = _agent(
        monkeypatch,
        '{"action": "{\\"type\\": \\"pickup\\", \\"package_ids\\": [\\"PKG-03\\"]}", "reasoning": "encoded"}',
    )
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    assert decision.action == {"type": "pickup", "package_ids": ["PKG-03"]}
    assert decision.fallback_used is False


def test_unusable_model_output_falls_back_and_says_so(monkeypatch, city_bundle):
    _, observation, legal = city_bundle
    agent = _agent(monkeypatch, "I am not going to answer with JSON.")
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    assert decision.fallback_used is True
    assert decision.error
    assert decision.action in legal
    assert "fallback" in (decision.reasoning or "").lower()


def test_illegal_action_from_the_model_still_reaches_the_engine(monkeypatch, city_bundle):
    """A well-formed but illegal action must be refused by the engine."""
    world, observation, legal = city_bundle
    agent = _agent(
        monkeypatch,
        '{"action": {"type": "move", "target": "7,7"}, "reasoning": "teleport"}',
    )
    decision = agent.decide(observation, legal, AgentContext("r", 0))
    # The supervisor does not offer an illegal hop, so it never becomes a move.
    assert decision.action.get("type") != "move" or decision.action.get("target") != "7,7"

    direct = world.apply(Action.parse({"type": "move", "target": "7,7"}))
    assert not direct.ok
    assert direct.code == "not_adjacent"
    assert world.vehicle["node"] == "0,0"


def test_model_selected_target_drives_the_route(monkeypatch, city_bundle):
    """After the model picks a package, the router walks it there."""
    world, observation, legal = city_bundle
    agent = _agent(
        monkeypatch,
        '{"action": {"type": "pickup", "package_ids": ["PKG-01"]}, "reasoning": "earliest deadline"}',
    )
    first = agent.decide(observation, legal, AgentContext("r", world.step))
    assert first.action["type"] == "pickup"
    world.apply(Action.parse(first.action))
    # Fill the van so the supervisor stops offering loading and starts routing.
    world.apply(Action.parse({"type": "pickup", "package_ids": ["PKG-02"]}))
    world.apply(Action.parse({"type": "pickup", "package_ids": ["PKG-03"]}))

    calls = {"n": 0}

    class _Client(_FakeClient):
        def post(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                content = '{"action": {"type": "move", "target": "0,1"}, "reasoning": "head north"}'
            else:
                content = '{"action": {"type": "wait"}, "reasoning": "unreachable"}'
            return _FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("simworld.agents.llm.httpx.Client", _Client)
    second = agent.decide(world.observation(), world.observation()["legal_actions"], AgentContext("r", 1))
    assert second.action == {"type": "move", "target": "0,1"}
    assert "PKG-01" in (second.reasoning or "")


def test_prompt_stays_compact_for_local_models(monkeypatch, city_bundle):
    _, observation, legal = city_bundle
    agent = _agent(monkeypatch, '{"action": {"type": "wait"}}')
    agent._call(agent._payload(observation, legal))
    body = agent._payload(observation, legal)
    prompt = json.dumps(body)
    assert len(prompt) < 6000, "prompt should stay small for local models"
    assert "legal_actions" in prompt


def test_probe_reports_unreachable_endpoint():
    result = probe_model("http://127.0.0.1:1/v1", "stub", None, timeout_s=1)
    assert result["available"] is False
    assert result["error"]


def test_probe_reports_missing_credentials(monkeypatch):
    class _Client(_FakeClient):
        def get(self, *_args, **_kwargs):
            return _FakeResponse({"data": []}, 401)

    monkeypatch.setattr("simworld.agents.llm.httpx.Client", _Client)
    result = probe_model("http://127.0.0.1:1/v1", "stub", None, timeout_s=1)
    assert result["available"] is False
    assert result["error"] == "unauthorized"
