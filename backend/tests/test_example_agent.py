"""The documented external-agent example must satisfy the real protocol."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from examples.external_agent import Handler, choose_city, choose_traffic
from simworld.agents.base import AgentContext
from simworld.agents.external import ExternalAgent
from simworld.engine.actions import Action
from simworld.engine.scenarios import build_world


def test_example_agent_picks_a_legal_action_for_city():
    world = build_world("city-logistics/standard", 7, None)
    observation = world.observation()
    action = choose_city(observation, observation["legal_actions"])
    assert action in observation["legal_actions"]
    result = world.apply(Action.parse(action))
    assert result.ok


def test_example_agent_delivers_before_anything_else():
    world = build_world("city-logistics/standard", 7, None)
    world.apply(Action.parse({"type": "pickup", "package_id": "PKG-01"}))
    world.apply(Action.parse({"type": "move", "target": "0,1"}))
    observation = world.observation()
    action = choose_city(observation, observation["legal_actions"])
    assert action["type"] == "move"


def test_example_agent_handles_traffic():
    world = build_world("traffic-control/steady", 7, None)
    for _ in range(4):
        world.apply(Action.parse({"type": "wait"}))
    observation = world.observation()
    action = choose_traffic(observation, observation["legal_actions"])
    assert action in observation["legal_actions"]


@pytest.fixture(scope="module")
def example_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/agent"
    server.shutdown()
    server.server_close()


def test_example_agent_completes_a_real_run(example_server):
    world = build_world("city-logistics/standard", 7, None)
    agent = ExternalAgent(url=example_server, timeout_ms=2000, allow_loopback=True)
    for _ in range(200):
        observation = world.observation()
        decision = agent.decide(observation, observation["legal_actions"], AgentContext("example", world.step))
        result = world.apply(Action.parse(decision.action))
        assert result.ok, result.message
        if world.status != "running":
            break
    metrics = world.metrics()
    assert metrics["packages_delivered"] == metrics["packages_total"]
    assert metrics["invalid_actions"] == 0


def test_example_agent_rejects_a_bad_protocol(example_server):
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        example_server,
        data=json.dumps({"protocol": "wrong", "observation": {}, "legal_actions": []}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 400
