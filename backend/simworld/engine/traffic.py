"""Adaptive traffic-signal control environment.

Nine signalised intersections with stochastic arrivals, fixed green timing
rules, and incidents. The agent chooses signal phases; the engine discharges
queues and measures waiting time, throughput, and safety-rule violations.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .actions import Action, ApplyResult

APPROACHES = ("N", "S", "E", "W")
GREEN_APPROACHES = {"NS": ("N", "S"), "EW": ("E", "W")}


class TrafficWorld:
    kind = "traffic_control"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.scenario_id: str = config["scenario_id"]
        self.seed = int(config["seed"])
        self.grid = int(config.get("grid", 3))
        self.horizon_steps = int(config.get("horizon_steps", 120))
        self.step_minutes = int(config.get("step_minutes", 1))
        self.min_green = int(config.get("min_green", 3))
        self.discharge_per_tick = int(config.get("discharge_per_tick", 2))
        self.arrival_tick_list: list[dict[str, Any]] = config.get("arrivals", [])

        nodes = [f"{x},{y}" for x in range(self.grid) for y in range(self.grid)]
        self.signals: dict[str, dict[str, Any]] = {
            node: {"phase": "NS", "last_switch": 0} for node in nodes
        }
        self.queues: dict[str, dict[str, list[int]]] = {
            node: {approach: [] for approach in APPROACHES} for node in nodes
        }
        self.arrivals_by_tick: dict[int, list[dict[str, Any]]] = {}
        for arrival in self.arrival_tick_list:
            self.arrivals_by_tick.setdefault(int(arrival["tick"]), []).append(arrival)

        self.step = 0
        self.time_min = 0
        self.status = "running"
        self.terminal_reason: str | None = None
        self.events: list[dict[str, Any]] = []
        self.event_plan: list[dict[str, Any]] = sorted(
            (dict(e) for e in config.get("event_plan", [])), key=lambda e: int(e["at_step"])
        )
        self.next_event_index = 0
        self.live_events: list[dict[str, Any]] = []
        self.active_incidents: list[dict[str, Any]] = []
        self.stats: dict[str, Any] = {
            "arrivals_total": 0,
            "discharged": 0,
            "wait_total": 0,
            "max_wait": 0,
            "invalid_actions": 0,
            "invalid_by_reason": {},
            "rule_violations": 0,
            "phase_changes": 0,
            "queue_samples": 0,
            "queue_total": 0,
        }
        self._event_seq = 0

    # -------------------------------------------------------------- observation
    def _queue_counts(self) -> dict[str, dict[str, int]]:
        return {
            node: {approach: len(q) for approach, q in approaches.items()}
            for node, approaches in self.queues.items()
        }

    def _waiting(self, node: str) -> list[int]:
        return [t for q in self.queues[node].values() for t in q]

    def legal_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for node in sorted(self.signals):
            signal = self.signals[node]
            if self.step - signal["last_switch"] < self.min_green:
                continue
            next_phase = "EW" if signal["phase"] == "NS" else "NS"
            actions.append({"type": "set_phase", "intersection": node, "phase": next_phase})
        actions.append({"type": "wait"})
        return actions

    def observation(self) -> dict[str, Any]:
        nodes = []
        for node in sorted(self.signals):
            signal = self.signals[node]
            queues = self._queue_counts()[node]
            waiting = self._waiting(node)
            nodes.append(
                {
                    "id": node,
                    "phase": signal["phase"],
                    "green_for_ticks": self.step - signal["last_switch"],
                    "queues": queues,
                    "waiting": len(waiting),
                    "oldest_wait_ticks": (self.step - min(waiting)) if waiting else 0,
                    "incidents": [
                        i for i in self.active_incidents if i["intersection"] == node
                    ],
                }
            )
        return {
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "step": self.step,
            "time_min": self.time_min,
            "horizon_steps": self.horizon_steps,
            "objective": self.config.get(
                "objective",
                "Minimise vehicle waiting time and maximise throughput while respecting minimum green times.",
            ),
            "min_green_ticks": self.min_green,
            "intersections": nodes,
            "recent_events": self.events[-4:],
            "metrics": self.metrics(),
            "legal_actions": self.legal_actions(),
        }

    # ------------------------------------------------------------------- rules
    def apply(self, action: Action) -> ApplyResult:
        if self.status != "running":
            return ApplyResult.rejected("run_not_running", f"Run is {self.status}.")

        switched: set[str] = set()
        if action.type == "set_phase":
            result = self._apply_phase(action.intersection or "", action.phase or "")
            if result.ok:
                switched.add(action.intersection or "")
        elif action.type == "wait":
            result = ApplyResult.success("Signals held.")
        else:
            result = ApplyResult.rejected(
                "wrong_environment",
                f"Action '{action.type}' is not supported in the traffic control environment.",
            )

        if not result.ok:
            self.stats["invalid_actions"] += 1
            by_reason = self.stats["invalid_by_reason"]
            by_reason[result.code] = by_reason.get(result.code, 0) + 1

        self._advance(switched)
        return result

    def _apply_phase(self, intersection: str, phase: str) -> ApplyResult:
        signal = self.signals.get(intersection)
        if signal is None:
            return ApplyResult.rejected(
                "intersection_not_found", f"Unknown intersection '{intersection}'."
            )
        if phase == signal["phase"]:
            return ApplyResult.success(f"{intersection} already running {phase}.")
        elapsed = self.step - signal["last_switch"]
        if elapsed < self.min_green:
            self.stats["rule_violations"] += 1
            return ApplyResult.rejected(
                "phase_too_soon",
                f"{intersection} has been green for {elapsed} tick(s); minimum green is "
                f"{self.min_green}. Safety constraint blocked the switch.",
            )
        signal["phase"] = phase
        signal["last_switch"] = self.step
        self.stats["phase_changes"] += 1
        return ApplyResult.success(f"{intersection} switched to {phase}.", phase=phase)

    def _advance(self, switched: set[str]) -> None:
        self.step += 1
        self.time_min += self.step_minutes
        while (
            self.next_event_index < len(self.event_plan)
            and int(self.event_plan[self.next_event_index]["at_step"]) <= self.step
        ):
            event = self.event_plan[self.next_event_index]
            self.next_event_index += 1
            self._apply_event(event, source="plan")

        self.active_incidents = [
            i for i in self.active_incidents if int(i["until_step"]) > self.step
        ]

        for arrival in self.arrivals_by_tick.get(self.step, []):
            node = arrival["intersection"]
            if node not in self.queues:
                continue
            for approach in arrival["approaches"]:
                if approach not in self.queues[node]:
                    continue
                for _ in range(int(arrival.get("count", 1))):
                    self.queues[node][approach].append(self.step)
                    self.stats["arrivals_total"] += 1

        for node in sorted(self.signals):
            if node in switched:
                continue
            phase = self.signals[node]["phase"]
            budget = self.discharge_per_tick
            blocked = {
                i["approach"] for i in self.active_incidents if i["intersection"] == node
            }
            while budget > 0:
                candidates = [
                    approach
                    for approach in GREEN_APPROACHES[phase]
                    if self.queues[node][approach] and approach not in blocked
                ]
                if not candidates:
                    break
                approach = min(candidates, key=lambda a: self.queues[node][a][0])
                arrived = self.queues[node][approach].pop(0)
                wait = self.step - arrived
                self.stats["discharged"] += 1
                self.stats["wait_total"] += wait
                self.stats["max_wait"] = max(self.stats["max_wait"], wait)
                budget -= 1

        total_queue = sum(len(q) for node in self.queues for q in self.queues[node].values())
        self.stats["queue_samples"] += 1
        self.stats["queue_total"] += total_queue

        if self.step >= self.horizon_steps:
            self.status = "finished"
            self.terminal_reason = "horizon_reached"

    def _apply_event(self, event: dict[str, Any], source: str) -> None:
        event_type = event.get("type")
        payload: dict[str, Any] = {}
        if event_type == "incident":
            node = event.get("intersection")
            approach = event.get("approach")
            if node not in self.signals or approach not in APPROACHES:
                return
            duration = int(event.get("duration_ticks", 10))
            incident = {
                "intersection": node,
                "approach": approach,
                "until_step": self.step + duration,
            }
            self.active_incidents.append(incident)
            payload = incident
        elif event_type == "surge":
            node = event.get("intersection")
            if node not in self.signals:
                return
            count = int(event.get("count", 3))
            for approach in event.get("approaches", ["N", "S", "E", "W"]):
                for _ in range(count):
                    self.queues[node][approach].append(self.step)
                    self.stats["arrivals_total"] += 1
            payload = {"intersection": node, "count": count}
        else:
            return

        self._event_seq += 1
        record = {
            "seq": self._event_seq,
            "step": self.step,
            "time_min": self.time_min,
            "type": event_type,
            "severity": event.get("severity", "warning"),
            "message": event.get("message", ""),
            "payload": payload,
            "source": source,
        }
        self.events.append(record)
        if source == "live":
            # Live injections happen between ticks. Record the step so replay can
            # reconstruct them in order with the recorded actions.
            self.live_events.append({**event, "at_step": self.step})

    def inject(self, event: dict[str, Any]) -> dict[str, Any] | None:
        before = len(self.events)
        self._apply_event({**event, "source": "live"}, source="live")
        if len(self.events) == before:
            return None
        return self.events[-1]

    # -------------------------------------------------------------- termination
    def terminal(self) -> tuple[bool, str | None]:
        return self.status != "running", self.terminal_reason

    def fail(self, reason: str) -> None:
        self.status = "failed"
        self.terminal_reason = reason

    # ----------------------------------------------------------------- metrics
    def metrics(self) -> dict[str, Any]:
        discharged = self.stats["discharged"]
        arrivals = self.stats["arrivals_total"]
        queue_avg = (
            self.stats["queue_total"] / (self.stats["queue_samples"] * max(1, len(self.signals)))
            if self.stats["queue_samples"]
            else 0.0
        )
        return {
            "vehicles_arrived": arrivals,
            "vehicles_discharged": discharged,
            "throughput_rate": round(discharged / arrivals, 4) if arrivals else 0.0,
            "avg_wait_ticks": round(self.stats["wait_total"] / discharged, 2) if discharged else 0.0,
            "max_wait_ticks": self.stats["max_wait"],
            "avg_queue_length": round(queue_avg, 2),
            "rule_violations": self.stats["rule_violations"],
            "invalid_actions": self.stats["invalid_actions"],
            "invalid_by_reason": dict(self.stats["invalid_by_reason"]),
            "phase_changes": self.stats["phase_changes"],
            "steps": self.step,
            "sim_minutes": self.time_min,
            "disruptions": len(self.events),
        }

    # ---------------------------------------------------------------- snapshot
    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "scenario_version": self.config.get("scenario_version"),
            "seed": self.seed,
            "step": self.step,
            "time_min": self.time_min,
            "horizon_steps": self.horizon_steps,
            "step_minutes": self.step_minutes,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "grid": self.grid,
            "min_green": self.min_green,
            "options": self.config.get("options", {}),
            "intersections": [
                {
                    "id": node,
                    "phase": signal["phase"],
                    "last_switch": signal["last_switch"],
                    "queues": {a: len(q) for a, q in self.queues[node].items()},
                    "oldest_wait_ticks": (
                        self.step - min(self._waiting(node)) if self._waiting(node) else 0
                    ),
                }
                for node, signal in sorted(self.signals.items())
            ],
            "incidents": list(self.active_incidents),
            "events": list(self.events),
            "metrics": self.metrics(),
            "state_hash": self.state_hash(),
        }

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "config": self.config,
            "signals": self.signals,
            "queues": self.queues,
            "step": self.step,
            "time_min": self.time_min,
            "status": self.status,
            "terminal_reason": self.terminal_reason,
            "events": self.events,
            "event_plan": self.event_plan,
            "next_event_index": self.next_event_index,
            "live_events": self.live_events,
            "active_incidents": self.active_incidents,
            "stats": self.stats,
            "event_seq": self._event_seq,
            "state_hash": self.state_hash(),
        }

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "TrafficWorld":
        world = cls(state["config"])
        world.signals = state["signals"]
        world.queues = state["queues"]
        world.step = state["step"]
        world.time_min = state["time_min"]
        world.status = state["status"]
        world.terminal_reason = state["terminal_reason"]
        world.events = state["events"]
        world.event_plan = state["event_plan"]
        world.next_event_index = state["next_event_index"]
        world.live_events = state.get("live_events", [])
        world.active_incidents = state.get("active_incidents", [])
        world.stats = state["stats"]
        world._event_seq = state.get("event_seq", len(world.events))
        return world

    def state_hash(self) -> str:
        payload = json.dumps(
            {
                "signals": self.signals,
                "queues": {n: {a: len(q) for a, q in qs.items()} for n, qs in self.queues.items()},
                "step": self.step,
                "status": self.status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]