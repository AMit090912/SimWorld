"""Objective evaluation.

Scores are computed only from recorded engine transitions and measured agent
latency. No metric is self-reported by an agent or a language model.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "completion_rate": {
        "label": "Delivery completion",
        "unit": "ratio",
        "direction": "higher",
        "description": "Delivered packages divided by packages in the scenario.",
        "weight": "50% of city score",
    },
    "on_time_rate": {
        "label": "On-time deliveries",
        "unit": "ratio",
        "direction": "higher",
        "description": "Packages delivered at or before their deadline divided by all packages.",
        "weight": "20% of city score",
    },
    "fuel_consumed_l": {
        "label": "Fuel consumed",
        "unit": "litres",
        "direction": "lower",
        "description": "Litres burned by actual vehicle movement; refuelling is recorded separately.",
        "weight": "drives the efficiency component",
    },
    "distance_km": {
        "label": "Distance driven",
        "unit": "km",
        "direction": "lower",
        "description": "Sum of traversed edge lengths.",
        "weight": "reported",
    },
    "invalid_actions": {
        "label": "Invalid actions",
        "unit": "count",
        "direction": "lower",
        "description": "Actions the engine rejected (blocked road, bad target, insufficient fuel, early phase switch).",
        "weight": "drives the compliance component",
    },
    "recovery_steps": {
        "label": "Disruption recovery",
        "unit": "steps",
        "direction": "lower",
        "description": "Steps between the first disruption and the next successful delivery. Null when no delivery followed.",
        "weight": "reported",
    },
    "agent_latency_ms": {
        "label": "Agent latency",
        "unit": "ms",
        "direction": "lower",
        "description": "Wall-clock time for the agent to answer each observation, measured by SimWorld.",
        "weight": "drives the reliability component",
    },
    "throughput_rate": {
        "label": "Throughput",
        "unit": "ratio",
        "direction": "higher",
        "description": "Vehicles discharged divided by vehicles that arrived.",
        "weight": "45% of traffic score",
    },
    "avg_wait_ticks": {
        "label": "Average wait",
        "unit": "ticks",
        "direction": "lower",
        "description": "Mean time from arrival to discharge for vehicles that cleared an intersection.",
        "weight": "drives the wait component",
    },
    "avg_queue_length": {
        "label": "Congestion",
        "unit": "vehicles",
        "direction": "lower",
        "description": "Mean queue length per intersection, sampled every tick.",
        "weight": "drives the congestion component",
    },
    "rule_violations": {
        "label": "Safety violations",
        "unit": "count",
        "direction": "lower",
        "description": "Attempted phase switches that broke the minimum-green constraint. The engine blocks them.",
        "weight": "drives the compliance component",
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _agent_stats(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = sorted(float(d.get("latency_ms") or 0.0) for d in decisions)
    errors = [d for d in decisions if d.get("error")]
    fallbacks = [d for d in decisions if d.get("fallback_used")]
    p95 = latencies[min(len(latencies) - 1, int(round(len(latencies) * 0.95)))] if latencies else 0.0
    total = max(1, len(decisions))
    return {
        "agent_calls": len(decisions),
        "agent_latency_ms": round(mean(latencies), 2) if latencies else 0.0,
        "agent_latency_p95_ms": round(p95, 2),
        "agent_errors": len(errors),
        "agent_fallbacks": len(fallbacks),
        "agent_error_rate": round(len(errors) / total, 4),
    }


def _recovery(events: list[dict[str, Any]], deliveries: list[dict[str, Any]]) -> dict[str, Any]:
    disruptions = [e for e in events if e.get("severity") in {"critical", "warning"}]
    if not disruptions:
        return {"recovery_steps": None, "post_disruption_deliveries": None, "disruption_count": 0}
    first = disruptions[0]["step"]
    after = [d for d in deliveries if d["step"] >= first]
    return {
        "recovery_steps": (after[0]["step"] - first) if after else None,
        "post_disruption_deliveries": len(after),
        "disruption_count": len(disruptions),
    }


def evaluate_run(
    kind: str,
    metrics: dict[str, Any],
    events: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    fuel_budget_l: float = 8.5,
) -> dict[str, Any]:
    agent = _agent_stats(decisions)
    merged = {**metrics, **agent}

    if kind == "city_logistics":
        recovery = _recovery(events, deliveries)
        merged.update(recovery)
        delivered = int(metrics.get("packages_delivered", 0))
        fuel = float(metrics.get("fuel_consumed_l", 0.0))
        invalid = int(metrics.get("invalid_actions", 0))
        completion = _clamp(float(metrics.get("completion_rate", 0.0)))
        on_time = _clamp(float(metrics.get("on_time_rate", 0.0)))
        efficiency = _clamp(1.0 - fuel / fuel_budget_l) if delivered > 0 else 0.0
        compliance = _clamp(1.0 - min(invalid, 10) / 10.0)
        reliability = _clamp(1.0 - float(agent["agent_error_rate"]))
        score = 100 * (
            0.50 * completion
            + 0.20 * on_time
            + 0.15 * efficiency
            + 0.10 * compliance
            + 0.05 * reliability
        )
        components = {
            "completion": round(completion, 4),
            "on_time": round(on_time, 4),
            "fuel_efficiency": round(efficiency, 4),
            "compliance": round(compliance, 4),
            "reliability": round(reliability, 4),
        }
    else:
        merged.update(
            {
                "recovery_steps": None,
                "post_disruption_deliveries": None,
                "disruption_count": len([e for e in events if e.get("severity") == "critical"]),
            }
        )
        throughput = _clamp(float(metrics.get("throughput_rate", 0.0)))
        wait = float(metrics.get("avg_wait_ticks", 0.0))
        queue = float(metrics.get("avg_queue_length", 0.0))
        violations = int(metrics.get("rule_violations", 0))
        wait_score = _clamp(1.0 - wait / 20.0)
        congestion = _clamp(1.0 - queue / 8.0)
        compliance = _clamp(1.0 - min(violations, 5) / 5.0)
        reliability = _clamp(1.0 - float(agent["agent_error_rate"]))
        score = 100 * (
            0.45 * throughput
            + 0.30 * wait_score
            + 0.15 * congestion
            + 0.05 * compliance
            + 0.05 * reliability
        )
        components = {
            "throughput": round(throughput, 4),
            "wait": round(wait_score, 4),
            "congestion": round(congestion, 4),
            "compliance": round(compliance, 4),
            "reliability": round(reliability, 4),
        }

    merged["score"] = round(score, 2)
    merged["score_components"] = components
    merged["failures"] = _failure_summary(kind, metrics, merged)
    return merged


def _failure_summary(kind: str, metrics: dict[str, Any], merged: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if kind == "city_logistics":
        missed = int(metrics.get("packages_total", 0)) - int(metrics.get("packages_delivered", 0))
        if missed > 0:
            failures.append(f"{missed} package(s) not delivered before the shift ended.")
        late = int(metrics.get("packages_late", 0))
        if late:
            failures.append(f"{late} package(s) delivered after their deadline.")
        if int(metrics.get("invalid_actions", 0)):
            reasons = metrics.get("invalid_by_reason", {})
            detail = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
            failures.append(f"{metrics['invalid_actions']} action(s) rejected by the engine ({detail}).")
        if float(metrics.get("fuel_remaining_l", 99)) < 0.5:
            failures.append("Van ended the run with under 0.5 L of fuel.")
    else:
        if int(metrics.get("rule_violations", 0)):
            failures.append(
                f"{metrics['rule_violations']} phase switch(es) blocked by the minimum-green rule."
            )
        rate = float(metrics.get("throughput_rate", 0.0))
        if rate < 0.8:
            failures.append(f"Only {rate:.0%} of arriving vehicles cleared an intersection.")
        if float(metrics.get("avg_wait_ticks", 0)) > 10:
            failures.append("Average wait exceeded 10 ticks.")
    if merged.get("agent_errors"):
        failures.append(f"{merged['agent_errors']} agent error(s); fallback policy was used.")
    if not failures:
        failures.append("No objective failures recorded.")
    return failures


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {"runs": 0, "metrics": {}, "scores": {}}
    numeric_keys: set[str] = set()
    for run in runs:
        for key, value in run.get("metrics", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_keys.add(key)
    summary: dict[str, Any] = {}
    for key in sorted(numeric_keys):
        values = [
            float(run["metrics"][key])
            for run in runs
            if isinstance(run.get("metrics", {}).get(key), (int, float))
            and not isinstance(run.get("metrics", {}).get(key), bool)
        ]
        if not values:
            continue
        summary[key] = {
            "mean": round(mean(values), 4),
            "std": round(pstdev(values), 4) if len(values) > 1 else 0.0,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
    scores = [float(r.get("metrics", {}).get("score", 0.0)) for r in runs]
    return {
        "runs": len(runs),
        "metrics": summary,
        "scores": {
            "mean": round(mean(scores), 2),
            "std": round(pstdev(scores), 2) if len(scores) > 1 else 0.0,
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
        },
    }


def metric_definitions() -> list[dict[str, Any]]:
    return [{"key": key, **value} for key, value in METRIC_DEFINITIONS.items()]