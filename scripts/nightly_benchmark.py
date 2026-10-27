"""Reproducible benchmark report across the shipped scenarios.

Usage:
    python scripts/nightly_benchmark.py [--api http://127.0.0.1:8000] [--seeds 7,11,23]

Calls the real SimWorld API, waits for each experiment, and writes
docs/benchmarks/latest.md. Nothing here fabricates a metric.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

SUITES = [
    {
        "scenario": "city-logistics/standard",
        "agents": ["city-baseline", "city-greedy", "city-blind"],
        "seeds": [7, 11, 23],
    },
    {
        "scenario": "city-logistics/disruption-storm",
        "agents": ["city-baseline", "city-greedy", "city-blind"],
        "seeds": [7, 11, 23],
    },
    {
        "scenario": "traffic-control/steady",
        "agents": ["traffic-adaptive", "traffic-fixed"],
        "seeds": [7, 11, 23],
    },
]


def request(api: str, path: str, method: str = "GET", body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{api.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"API error {exc.code} on {path}: {exc.read().decode()[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach SimWorld at {api}. Start the backend first.\n{exc}"
        ) from exc


def mean(block: dict[str, Any], key: str) -> float | None:
    entry = (block.get("metrics") or {}).get(key)
    return None if not entry else float(entry["mean"])


def fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def run_suite(api: str, suite: dict[str, Any], seeds: list[int]) -> dict[str, Any]:
    scenario = suite["scenario"]
    print(f"-> {scenario} ({len(suite['agents'])} agents x {len(seeds)} seeds)")
    experiment = request(
        api,
        "/api/experiments",
        "POST",
        {
            "scenario_id": scenario,
            "seeds": seeds,
            "agents": [{"type": "builtin", "id": agent} for agent in suite["agents"]],
        },
    )
    deadline = time.time() + 900
    while experiment["status"] == "running" and time.time() < deadline:
        time.sleep(1)
        experiment = request(api, f"/api/experiments/{experiment['id']}")
    if experiment["status"] != "finished":
        print(f"  ! experiment ended as {experiment['status']}: {experiment.get('error')}")
    return experiment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.getenv("SIMWORLD_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--seeds", default="7,11,23")
    parser.add_argument("--out", default="docs/benchmarks/latest.md")
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]

    health = request(args.api, "/api/health")
    print(f"SimWorld API {args.api} | version {health.get('version')} | runs {health.get('runs')}")

    experiments = [run_suite(args.api, suite, seeds) for suite in SUITES]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# SimWorld benchmark (latest run)",
        "",
        f"Generated {timestamp} from recorded runs. Seeds: {', '.join(str(seed) for seed in seeds)}.",
        "Every number below comes from the SimWorld API; none are self-reported by an agent.",
        "",
        "## Composite scores",
        "",
        "| Scenario | Agent | Mean score | Std | Runs |",
        "| --- | --- | --- | --- | --- |",
    ]
    for experiment in experiments:
        scenario = experiment["scenario_id"]
        for label, block in experiment["aggregate"]["by_agent"].items():
            lines.append(
                f"| {scenario} | {label} | {block['scores']['mean']:.1f} | "
                f"±{block['scores']['std']:.1f} | {block['runs']} |"
            )

    lines.extend(
        [
            "",
            "## City logistics components",
            "",
            "| Scenario | Agent | Completion | On time | Fuel (L) | Invalid | Latency (ms) |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for experiment in experiments:
        if experiment["kind"] != "city_logistics":
            continue
        scenario = experiment["scenario_id"]
        for label, block in experiment["aggregate"]["by_agent"].items():
            completion = mean(block, "completion_rate")
            on_time = mean(block, "on_time_rate")
            fuel = mean(block, "fuel_consumed_l")
            invalid = mean(block, "invalid_actions")
            latency = mean(block, "agent_latency_ms")
            lines.append(
                f"| {scenario} | {label} | "
                f"{'n/a' if completion is None else f'{completion:.0%}'} | "
                f"{'n/a' if on_time is None else f'{on_time:.0%}'} | "
                f"{fmt(fuel)} | {fmt(invalid, 1)} | {fmt(latency, 0)} |"
            )

    lines.extend(
        [
            "",
            "## Traffic control components",
            "",
            "| Scenario | Agent | Throughput | Avg wait (ticks) | Avg queue | Violations | Latency (ms) |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for experiment in experiments:
        if experiment["kind"] != "traffic_control":
            continue
        scenario = experiment["scenario_id"]
        for label, block in experiment["aggregate"]["by_agent"].items():
            throughput = mean(block, "throughput_rate")
            wait = mean(block, "avg_wait_ticks")
            queue = mean(block, "avg_queue_length")
            violations = mean(block, "rule_violations")
            latency = mean(block, "agent_latency_ms")
            lines.append(
                f"| {scenario} | {label} | "
                f"{'n/a' if throughput is None else f'{throughput:.0%}'} | "
                f"{fmt(wait, 1)} | {fmt(queue, 1)} | {fmt(violations, 1)} | {fmt(latency, 0)} |"
            )

    lines.extend(["", "## Failures worth reading", ""])
    seen = False
    for experiment in experiments:
        for run in experiment["aggregate"]["runs"]:
            failures = (run.get("metrics") or {}).get("failures") or []
            real = [failure for failure in failures if not failure.startswith("No objective")]
            if real:
                seen = True
                lines.append(
                    f"- **{run['id']}** · {experiment['scenario_id']} · seed {run['seed']} · "
                    f"{run['agent']} · score {run['score']}: {'; '.join(real)}"
                )
    if not seen:
        lines.append("- No objective failures recorded in this suite.")

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "Open any run in the SimWorld UI (`/runs/<id>`) to replay every recorded transition.",
            "Experiments used identical seeds for every agent in a scenario.",
            "",
        ]
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(f"wrote {args.out}")
    print("\n".join(lines[:18]))


if __name__ == "__main__":
    main()
