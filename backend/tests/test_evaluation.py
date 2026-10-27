"""Evaluation math and aggregation."""

from __future__ import annotations

import pytest

from simworld.evaluation import aggregate, evaluate_run


def test_city_score_is_component_based_not_self_reported():
    metrics = {
        "packages_total": 5,
        "packages_delivered": 4,
        "packages_on_time": 2,
        "packages_late": 2,
        "completion_rate": 0.8,
        "on_time_rate": 0.4,
        "fuel_consumed_l": 4.25,
        "invalid_actions": 2,
        "fuel_remaining_l": 2.0,
        "invalid_by_reason": {"road_closed": 2},
    }
    events = [{"step": 10, "severity": "critical", "type": "road_closure"}]
    deliveries = [
        {"step": 4, "package_id": "P1", "late": False},
        {"step": 12, "package_id": "P2", "late": False},
        {"step": 15, "package_id": "P3", "late": True},
        {"step": 18, "package_id": "P4", "late": True},
    ]
    decisions = [
        {"latency_ms": 10.0, "error": None, "fallback_used": False},
        {"latency_ms": 20.0, "error": None, "fallback_used": False},
        {"latency_ms": 30.0, "error": "timeout", "fallback_used": True},
        {"latency_ms": 40.0, "error": None, "fallback_used": False},
    ]
    result = evaluate_run("city_logistics", metrics, events, deliveries, decisions)

    assert result["score_components"]["completion"] == pytest.approx(0.8)
    assert result["score_components"]["on_time"] == pytest.approx(0.4)
    assert result["score_components"]["fuel_efficiency"] == pytest.approx(0.5)
    assert result["score_components"]["compliance"] == pytest.approx(0.8)
    assert result["score_components"]["reliability"] == pytest.approx(0.75)
    expected = 100 * (0.5 * 0.8 + 0.2 * 0.4 + 0.15 * 0.5 + 0.1 * 0.8 + 0.05 * 0.75)
    assert result["score"] == pytest.approx(round(expected, 2))
    assert result["agent_errors"] == 1
    assert result["agent_latency_ms"] == pytest.approx(25.0)
    assert result["recovery_steps"] == 2
    assert result["post_disruption_deliveries"] == 3
    assert any("deadline" in failure for failure in result["failures"])


def test_no_deliveries_gets_zero_efficiency_and_failure_listed():
    metrics = {
        "packages_total": 3,
        "packages_delivered": 0,
        "packages_on_time": 0,
        "packages_late": 0,
        "completion_rate": 0.0,
        "on_time_rate": 0.0,
        "fuel_consumed_l": 0.0,
        "invalid_actions": 0,
        "invalid_by_reason": {},
        "fuel_remaining_l": 1.0,
    }
    result = evaluate_run("city_logistics", metrics, [], [], [])
    assert result["score_components"]["fuel_efficiency"] == 0.0
    assert result["score"] < 20
    assert "3 package(s) not delivered" in result["failures"][0]


def test_traffic_score_and_violations():
    metrics = {
        "throughput_rate": 0.9,
        "avg_wait_ticks": 5.0,
        "avg_queue_length": 2.0,
        "rule_violations": 1,
        "invalid_actions": 1,
    }
    result = evaluate_run("traffic_control", metrics, [], [], [])
    assert result["score_components"]["throughput"] == pytest.approx(0.9)
    assert result["score_components"]["wait"] == pytest.approx(0.75)
    assert result["score_components"]["congestion"] == pytest.approx(0.75)
    assert result["score_components"]["compliance"] == pytest.approx(0.8)
    assert result["score"] > 0


def test_aggregate_mean_std_and_range():
    runs = [
        {"metrics": {"score": 70.0, "fuel_consumed_l": 8.0}},
        {"metrics": {"score": 80.0, "fuel_consumed_l": 10.0}},
        {"metrics": {"score": 90.0, "fuel_consumed_l": 12.0}},
    ]
    summary = aggregate(runs)
    assert summary["runs"] == 3
    assert summary["scores"]["mean"] == pytest.approx(80.0)
    assert summary["scores"]["min"] == 70.0
    assert summary["scores"]["max"] == 90.0
    assert summary["metrics"]["fuel_consumed_l"]["mean"] == pytest.approx(10.0)
    assert summary["metrics"]["fuel_consumed_l"]["std"] > 0