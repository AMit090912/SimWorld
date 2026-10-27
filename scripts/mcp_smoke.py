"""Protocol smoke test for the SimWorld MCP server.

Starts the stdio server, performs the MCP handshake, lists tools, then runs a
real scenario and a two-by-two experiment through the tools.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    process = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "mcp_server", "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert process.stdin and process.stdout
    counter = 0

    def call(method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        nonlocal counter
        message: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notify:
            counter += 1
            message["id"] = counter
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        if notify:
            return None
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout")
        return json.loads(line)

    init = call(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "simworld-smoke", "version": "0.1.0"},
        },
    )
    assert init and init["result"]["serverInfo"]["name"] == "simworld"
    print("initialize:", init["result"]["protocolVersion"])
    call("notifications/initialized", notify=True)

    tools = call("tools/list")
    names = [tool["name"] for tool in tools["result"]["tools"]]
    print("tools:", ", ".join(names))
    assert "simworld_run_experiment" in names

    scenarios = call("tools/call", {"name": "simworld_list_scenarios", "arguments": {}})
    text = scenarios["result"]["content"][0]["text"]
    assert "Riverside Standard Run" in text and "Stadium Surge" in text
    print("list_scenarios: ok")

    run = call(
        "tools/call",
        {
            "name": "simworld_start_run",
            "arguments": {
                "scenario_id": "city-logistics/standard",
                "seed": 7,
                "agent_id": "city-baseline",
            },
        },
    )
    run_text = run["result"]["content"][0]["text"]
    assert run["result"]["isError"] is False
    assert "Score:" in run_text
    run_id = run_text.split("Run ", 1)[1].split(" ", 1)[0]
    print("start_run:", run_id, run_text.splitlines()[2])

    explain = call("tools/call", {"name": "simworld_explain_failure", "arguments": {"run_id": run_id}})
    assert explain["result"]["isError"] is False
    assert "Failure analysis" in explain["result"]["content"][0]["text"]
    print("explain_failure: ok")

    second = call(
        "tools/call",
        {
            "name": "simworld_start_run",
            "arguments": {"scenario_id": "city-logistics/standard", "seed": 7, "agent_id": "city-blind"},
        },
    )
    second_text = second["result"]["content"][0]["text"]
    second_id = second_text.split("Run ", 1)[1].split(" ", 1)[0]
    compare = call(
        "tools/call",
        {"name": "simworld_compare_runs", "arguments": {"run_ids": [run_id, second_id]}},
    )
    assert compare["result"]["isError"] is False
    print("compare_runs: ok")

    start = time.time()
    experiment = call(
        "tools/call",
        {
            "name": "simworld_run_experiment",
            "arguments": {
                "scenario_id": "city-logistics/standard",
                "seeds": [7, 11],
                "agent_ids": ["city-baseline", "city-greedy"],
            },
        },
    )
    assert experiment["result"]["isError"] is False
    text = experiment["result"]["content"][0]["text"]
    assert "Mean score" in text
    print(f"run_experiment: ok in {time.time() - start:.1f}s")

    process.stdin.close()
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    print("MCP smoke test passed")


if __name__ == "__main__":
    main()