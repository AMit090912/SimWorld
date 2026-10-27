"""MCP server tools: schema, dispatch, and error handling."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("simworld_mcp_server", ROOT / "mcp_server" / "server.py")
server = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(server)


def test_tool_catalogue_is_well_formed():
    assert len(server.TOOLS) == 6
    names = {tool["name"] for tool in server.TOOLS}
    assert {
        "simworld_list_scenarios",
        "simworld_start_run",
        "simworld_run_experiment",
        "simworld_get_metrics",
        "simworld_explain_failure",
        "simworld_compare_runs",
    } == names
    for tool in server.TOOLS:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_initialize_handshake():
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["id"] == 1
    assert response["result"]["serverInfo"]["name"] == "simworld"
    assert response["result"]["capabilities"]["tools"] == {"listChanged": False}


def test_tools_list_returns_catalogue():
    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(response["result"]["tools"]) == 6


def test_unknown_tool_is_reported_as_error_not_crash():
    response = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope", "arguments": {}}}
    )
    assert response["error"]["code"] == -32601


def test_api_failure_is_reported_to_the_client(monkeypatch):
    def boom(*_args, **_kwargs):
        raise server.SimWorldError("SimWorld API 500: internal error")

    monkeypatch.setattr(server, "_request", boom)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "simworld_list_scenarios", "arguments": {}},
        }
    )
    assert response["result"]["isError"] is True
    assert "internal error" in response["result"]["content"][0]["text"]


def test_explain_failure_uses_recorded_evidence(monkeypatch):
    def fake_request(path, method="GET", body=None):
        if path.startswith("/api/runs/") and path.endswith("/replay"):
            return {
                "run": {"id": "abc123", "scenario_id": "city-logistics/standard", "seed": 7, "terminal_reason": "all_delivered"},
                "initial_snapshot": {"kind": "city_logistics", "packages": []},
                "steps": [
                    {
                        "step": 1,
                        "action": {"type": "move", "target": "9,9"},
                        "valid": False,
                        "reason": "Cannot move from 0,0 to 9,9: no direct road.",
                        "decision": {"code": "not_adjacent"},
                        "state": {
                            "kind": "city_logistics",
                            "vehicle": {"node": "0,0", "fuel_l": 8.0, "cargo": []},
                            "packages": [
                                {"id": "PKG-01", "dest_label": "Harbor", "status": "delivered", "late": True, "deadline_min": 10, "delivered_at_min": 40}
                            ],
                            "events": [
                                {
                                    "seq": 1,
                                    "step": 1,
                                    "type": "road_closure",
                                    "message": "Live road closure injected on 1,0|0,0.",
                                    "source": "live",
                                }
                            ],
                        },
                    }
                ],
                "evaluation": {"score": 42.0, "failures": ["1 package(s) not delivered."]},
            }
        raise AssertionError(path)

    monkeypatch.setattr(server, "_request", fake_request)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "simworld_explain_failure", "arguments": {"run_id": "abc123"}},
        }
    )
    text = response["result"]["content"][0]["text"]
    assert "not_adjacent" in text
    assert "Live road closure" in text
    assert "van at 0,0" in text
    assert "1 package(s) not delivered" in text
