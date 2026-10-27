"""SimWorld MCP server (stdio).

Exposes the evaluation workflow as Model Context Protocol tools so an Alan
agent (or any MCP client) can run reproducible experiments and read the
evidence. This server is dependency-free: it speaks JSON-RPC over stdio and
calls the SimWorld HTTP API.

    python mcp_server/server.py

Environment:
    SIMWORLD_API_URL   default http://127.0.0.1:8000
    MCP_RUN_TIMEOUT_S  default 900
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

API = os.getenv("SIMWORLD_API_URL", "http://127.0.0.1:8000").rstrip("/")
RUN_TIMEOUT = float(os.getenv("MCP_RUN_TIMEOUT_S", "900"))
PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "simworld_list_scenarios",
        "description": "List SimWorld environments, scenarios, objectives, constraints, and variation axes.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "simworld_start_run",
        "description": (
            "Launch one reproducible SimWorld run and wait for it to finish. Returns the score, "
            "component metrics, component breakdown, and failure list produced from recorded transitions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "seed": {"type": "integer", "minimum": 0},
                "agent_id": {
                    "type": "string",
                    "description": "Built-in agent id, e.g. city-baseline, city-greedy, city-blind, traffic-adaptive, traffic-fixed.",
                },
                "options": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Scenario variation values, e.g. {\"disruption_timing\":\"early\"}.",
                },
            },
            "required": ["scenario_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "simworld_run_experiment",
        "description": (
            "Run the same scenarios and seeds across multiple agents and return aggregate mean/std "
            "scores plus per-run evidence. This is the defensible way to compare strategies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "seeds": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 10},
                "agent_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                "options": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["scenario_id", "seeds", "agent_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "simworld_get_metrics",
        "description": "Return stored metrics and configuration for an existing run.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "simworld_explain_failure",
        "description": (
            "Explain a run from recorded evidence: failures, invalid actions, disruption timeline, "
            "late deliveries, and where the agent was at the first failure."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "simworld_compare_runs",
        "description": "Compare two to four recorded runs on score and component metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4}
            },
            "required": ["run_ids"],
            "additionalProperties": False,
        },
    },
]


class SimWorldError(RuntimeError):
    pass


def _request(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise SimWorldError(f"SimWorld API {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SimWorldError(
            f"Cannot reach SimWorld at {API}. Start the backend and try again. ({exc})"
        ) from exc


def _wait_run(run_id: str) -> dict[str, Any]:
    deadline = time.time() + RUN_TIMEOUT
    while time.time() < deadline:
        payload = _request(f"/api/runs/{run_id}")
        if payload["run"]["status"] in {"finished", "failed", "paused"}:
            return payload
        time.sleep(0.4)
    raise SimWorldError(f"Run {run_id} did not finish within {RUN_TIMEOUT:.0f}s.")


def _start_run(scenario_id: str, seed: int, agent_id: str, options: dict[str, str]) -> dict[str, Any]:
    created = _request(
        "/api/runs",
        "POST",
        {
            "scenario_id": scenario_id,
            "seed": seed,
            "options": options,
            "agent": {"type": "builtin", "id": agent_id},
        },
    )
    run_id = created["run"]["id"]
    _request(f"/api/runs/{run_id}/start", "POST", {"delay_ms": 0})
    return _wait_run(run_id)


def _summary(payload: dict[str, Any]) -> str:
    run = payload["run"]
    evaluation = payload["evaluation"]
    lines = [
        f"Run {run['id']} · {run['scenario_id']} · seed {run['seed']} · {run['agent']['label']}",
        f"Status: {run['status']} ({run.get('terminal_reason') or 'n/a'})",
        f"Score: {evaluation['score']:.1f}/100",
        "",
        "Component metrics:",
    ]
    for key, value in evaluation.items():
        if isinstance(value, (int, float)) and key not in {"score"}:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Score components:")
    for key, value in evaluation.get("score_components", {}).items():
        lines.append(f"- {key}: {value:.0%}")
    lines.append("")
    lines.append("Failures:")
    for failure in evaluation.get("failures", []):
        lines.append(f"- {failure}")
    return "\n".join(lines)


def tool_list_scenarios(_args: dict[str, Any]) -> str:
    payload = _request("/api/scenarios")
    lines = ["SimWorld scenarios (all execute real engine rules):", ""]
    for scenario in payload["scenarios"]:
        lines.append(f"## {scenario['name']} — {scenario['id']}")
        lines.append(f"{scenario['tagline']} · {scenario['difficulty']} · {scenario['horizon_steps']} ticks")
        lines.append(f"Objectives: {'; '.join(scenario['objectives'])}")
        lines.append(
            "Variations: "
            + ", ".join(
                f"{variation['label']} ({', '.join(option['value'] for option in variation['options'])})"
                for variation in scenario["variations"]
            )
        )
        lines.append("")
    return "\n".join(lines)


def tool_start_run(args: dict[str, Any]) -> str:
    scenario_id = str(args.get("scenario_id", ""))
    seed = int(args.get("seed", 7))
    agent_id = str(args.get("agent_id", "city-baseline"))
    options = {str(k): str(v) for k, v in (args.get("options") or {}).items()}
    payload = _start_run(scenario_id, seed, agent_id, options)
    return _summary(payload)


def tool_run_experiment(args: dict[str, Any]) -> str:
    scenario_id = str(args.get("scenario_id", ""))
    seeds = [int(seed) for seed in args.get("seeds", [])]
    agent_ids = [str(agent) for agent in args.get("agent_ids", [])]
    options = {str(k): str(v) for k, v in (args.get("options") or {}).items()}
    experiment = _request(
        "/api/experiments",
        "POST",
        {
            "scenario_id": scenario_id,
            "seeds": seeds,
            "agents": [{"type": "builtin", "id": agent} for agent in agent_ids],
            "options": options,
        },
    )
    deadline = time.time() + RUN_TIMEOUT
    while time.time() < deadline and experiment["status"] == "running":
        time.sleep(1.0)
        experiment = _request(f"/api/experiments/{experiment['id']}")
    if experiment["status"] != "finished":
        raise SimWorldError(f"Experiment {experiment['id']} ended as {experiment['status']}: {experiment.get('error')}")

    aggregate = experiment["aggregate"]
    lines = [
        f"Experiment {experiment['id']} · {experiment['scenario_id']}",
        f"Seeds: {', '.join(str(seed) for seed in seeds)} · runs: {aggregate['overall']['runs']}",
        "",
        "| Agent | Mean score | Std | Completion | On time | Invalid | Latency |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, block in aggregate["by_agent"].items():
        metrics = block["metrics"]

        def mean(key: str) -> str:
            entry = metrics.get(key)
            return "—" if not entry else f"{entry['mean']:.2f}"

        lines.append(
            f"| {label} | {block['scores']['mean']:.1f} | ±{block['scores']['std']:.1f} | "
            f"{mean('completion_rate')} | {mean('on_time_rate')} | {mean('invalid_actions')} | "
            f"{mean('agent_latency_ms')} ms |"
        )
    lines.extend(["", "Per-run evidence:"])
    for run in aggregate["runs"]:
        lines.append(
            f"- {run['id']} · seed {run['seed']} · {run['agent']} · score {run['score']} · {run['status']}"
        )
    return "\n".join(lines)


def tool_get_metrics(args: dict[str, Any]) -> str:
    run_id = str(args.get("run_id", ""))
    payload = _request(f"/api/runs/{run_id}")
    return _summary(payload)


def tool_explain_failure(args: dict[str, Any]) -> str:
    run_id = str(args.get("run_id", ""))
    replay = _request(f"/api/runs/{run_id}/replay")
    evaluation = replay["evaluation"]
    steps = replay["steps"]
    lines = [
        f"Failure analysis for run {run_id} ({replay['run']['scenario_id']}, seed {replay['run']['seed']})",
        f"Score {evaluation['score']:.1f} · terminal: {replay['run'].get('terminal_reason')}",
        "",
        "Objective failures:",
    ]
    for failure in evaluation.get("failures", []):
        lines.append(f"- {failure}")

    disruptions = [step for step in steps for event in step["state"].get("events", []) if event.get("source") == "live"]
    invalid = [step for step in steps if not step["valid"]]
    if invalid:
        lines.append("")
        lines.append(f"Invalid actions ({len(invalid)}):")
        for step in invalid[:8]:
            decision = step.get("decision") or {}
            lines.append(
                f"- step {step['step']} · {json.dumps(step['action'])} · {decision.get('code')}: {step['reason']}"
            )
        first = invalid[0]
        state = first["state"]
        if state.get("kind") == "city_logistics":
            lines.append(
                f"  van at {state['vehicle']['node']} with {state['vehicle']['fuel_l']:.2f} L and "
                f"{len(state['vehicle']['cargo'])} package(s) on board when the rejection happened."
            )

    final = steps[-1]["state"] if steps else replay["initial_snapshot"]
    if final.get("kind") == "city_logistics":
        late = [pkg for pkg in final.get("packages", []) if pkg.get("late")]
        pending = [pkg for pkg in final.get("packages", []) if pkg.get("status") != "delivered"]
        if late:
            lines.extend(["", "Late deliveries:"])
            for pkg in late:
                lines.append(
                    f"- {pkg['id']} → {pkg['dest_label']} · due {pkg['deadline_min']} min · "
                    f"delivered {pkg.get('delivered_at_min')}"
                )
        if pending:
            lines.extend(["", "Never delivered:"])
            for pkg in pending:
                lines.append(f"- {pkg['id']} → {pkg['dest_label']} ({pkg['status']}) · due {pkg['deadline_min']} min")

    timeline = [event for step in steps for event in step["state"].get("events", [])]
    unique: dict[tuple[int, str], dict[str, Any]] = {}
    for event in timeline:
        unique[(event["seq"], event["message"])] = event
    if unique:
        lines.extend(["", "Event timeline:"])
        for event in sorted(unique.values(), key=lambda item: item["seq"]):
            lines.append(f"- t{event['step']} · {event['type']} · {event['message']} ({event['source']})")

    if len(lines) <= 3:
        lines.append("- No objective failures recorded. The run still has per-step evidence in replay.")
    return "\n".join(lines)


def tool_compare_runs(args: dict[str, Any]) -> str:
    run_ids = [str(run_id) for run_id in args.get("run_ids", [])]
    runs = []
    for run_id in run_ids:
        payload = _request(f"/api/runs/{run_id}")
        runs.append(payload)
    keys = ["score", "completion_rate", "on_time_rate", "fuel_consumed_l", "invalid_actions", "agent_latency_ms"]
    lines = ["| Metric | " + " | ".join(run["run"]["id"] for run in runs) + " |",
             "| --- | " + " | ".join("---" for _ in runs) + " |"]
    for key in keys:
        row = []
        for run in runs:
            value = run["evaluation"].get(key)
            row.append("—" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value))
        lines.append(f"| {key} | " + " | ".join(row) + " |")
    lines.append("")
    for run in runs:
        lines.append(f"- {run['run']['id']} · seed {run['run']['seed']} · {run['run']['agent']['label']}")
    return "\n".join(lines)


TOOL_HANDLERS = {
    "simworld_list_scenarios": tool_list_scenarios,
    "simworld_start_run": tool_start_run,
    "simworld_run_experiment": tool_run_experiment,
    "simworld_get_metrics": tool_get_metrics,
    "simworld_explain_failure": tool_explain_failure,
    "simworld_compare_runs": tool_compare_runs,
}


def _result(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "simworld", "version": "0.1.0"},
                "instructions": (
                    "Use these tools to run real, reproducible agent evaluations. "
                    "Report only metrics returned by the tools."
                ),
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return _error(request_id, -32601, f"Unknown tool '{name}'.")
        try:
            text = handler(params.get("arguments") or {})
            return _result(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except (SimWorldError, ValueError, KeyError, TypeError) as exc:
            return _result(
                request_id,
                {"content": [{"type": "text", "text": f"SimWorld tool error: {exc}"}], "isError": True},
            )
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    print("simworld MCP server ready", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
            print(json.dumps(response), flush=True)
            continue
        try:
            response = handle(message)
        except Exception as exc:  # noqa: BLE001 - keep the MCP loop alive
            response = _error(message.get("id"), -32603, f"Internal error: {exc}")
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()