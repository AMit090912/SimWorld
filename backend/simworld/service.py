"""Run orchestration: lifecycle, agent calls, persistence, replay, experiments.

The service is the only layer that combines the engine, agent adapters, and
storage. It never lets an agent touch world state directly.
"""

from __future__ import annotations

import copy
import json
import random
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from .agents.base import AgentContext, AgentError, Decision
from .agents.builtins import AGENT_METADATA, default_builtin_for, make_builtin
from .agents.factory import agent_descriptor, build_agent
from .agents.llm import llm_config_from_env, probe_model
from .config import Settings
from .engine.actions import Action, ActionFormatError
from .engine.city import CityWorld
from .engine.scenarios import (
    SCENARIO_BY_ID,
    build_config,
    build_world,
    list_scenarios,
    scenario_public,
    world_from_state,
)
from .evaluation import aggregate, evaluate_run, metric_definitions
from .store import Store

MAX_STEPS_PER_RUN = 400
MAX_AUTOPLAY_DELAY_MS = 2000
MAX_EXPERIMENT_RUNS = 24


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


@dataclass
class RunSession:
    run_id: str
    world: Any
    agent: Any
    agent_desc: dict[str, Any]
    run_meta: dict[str, Any]
    decisions: list[dict[str, Any]] = field(default_factory=list)
    deliveries: list[dict[str, Any]] = field(default_factory=list)
    last_result: dict[str, Any] | None = None
    consecutive_errors: int = 0
    started_monotonic: float | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class RunService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self._sessions: dict[str, RunSession] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._registry_lock = threading.RLock()
        self._experiments: dict[str, threading.Thread] = {}

    # ----------------------------------------------------------------- catalog
    def scenarios(self) -> list[dict[str, Any]]:
        return list_scenarios()

    def scenario(self, scenario_id: str) -> dict[str, Any] | None:
        scenario = SCENARIO_BY_ID.get(scenario_id)
        return scenario_public(scenario) if scenario else None

    def scenario_preview(self, scenario_id: str, seed: int = 7) -> dict[str, Any]:
        scenario = self.scenario(scenario_id)
        if scenario is None:
            raise KeyError(scenario_id)
        world = build_world(scenario_id, seed, None)
        return {"scenario": scenario, "snapshot": world.snapshot()}

    def metric_definitions(self) -> list[dict[str, Any]]:
        return metric_definitions()

    def agent_catalogue(self) -> dict[str, Any]:
        llm = llm_config_from_env()
        probe = probe_model(
            llm["base_url"], llm["model"], llm["api_key"], timeout_s=3.0
        )
        return {
            "builtin": AGENT_METADATA,
            "modes": [
                {
                    "type": "external",
                    "label": "External HTTP agent",
                    "protocol": "simworld.agent.v1",
                    "loopback_allowed": self.settings.allow_loopback_agents,
                },
                {
                    "type": "llm",
                    "label": "OpenAI-compatible model",
                    "model": llm["model"],
                    "base_url": llm["base_url"],
                    "provider": llm["provider"],
                    "api_key_configured": bool(llm["api_key"]),
                    "probe": probe,
                },
            ],
        }

    def llm_status(self) -> dict[str, Any]:
        config = llm_config_from_env()
        result = probe_model(
            config["base_url"], config["model"], config["api_key"], timeout_s=4.0
        )
        configured = bool(config["api_key"]) or any(
            host in config["base_url"] for host in ("127.0.0.1", "localhost")
        )
        return {
            "provider": config["provider"],
            "model": config["model"],
            "base_url": config["base_url"],
            "api_key_configured": bool(config["api_key"]),
            "configured": configured,
            "probe": result,
        }

    # ------------------------------------------------------------------- runs
    def _lock(self, run_id: str) -> threading.RLock:
        with self._registry_lock:
            return self._locks.setdefault(run_id, threading.RLock())

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenario_id = str(payload.get("scenario_id") or "")
        scenario = SCENARIO_BY_ID.get(scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario '{scenario_id}'.")
        seed = payload.get("seed", 7)
        if not isinstance(seed, int) or isinstance(seed, bool) or not (0 <= seed <= 2**31 - 1):
            raise ValueError("Seed must be an integer between 0 and 2147483647.")
        options = payload.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError("Options must be an object.")
        config = build_config(scenario_id, seed, options)
        world = build_world(scenario_id, seed, options)

        agent_spec = payload.get("agent") or {
            "type": "builtin",
            "id": default_builtin_for(config["kind"]),
        }
        if not isinstance(agent_spec, dict):
            raise ValueError("Agent must be an object.")
        agent = build_agent(agent_spec, config["kind"], self.settings)
        descriptor = agent_descriptor(agent_spec, agent, config["kind"])

        run_id = self.store.create_run(
            scenario_id=scenario_id,
            scenario_version=int(config.get("scenario_version", 1)),
            kind=config["kind"],
            seed=seed,
            options=config.get("options", {}),
            agent=descriptor,
            config=config,
            initial_state=world.to_dict(),
        )
        meta = self.store.get_run(run_id, include_state=False) or {}
        session = RunSession(
            run_id=run_id,
            world=world,
            agent=agent,
            agent_desc=descriptor,
            run_meta=meta,
        )
        with self._registry_lock:
            self._sessions[run_id] = session
        return self.get_run(run_id)

    def _load_session(self, run_id: str) -> RunSession:
        with self._registry_lock:
            existing = self._sessions.get(run_id)
        if existing is not None:
            return existing
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        world = world_from_state(run["state"])
        descriptor = run["agent"]
        config = descriptor.get("config", {})
        spec = {
            "type": descriptor.get("type", "builtin"),
            "id": descriptor.get("id"),
            "url": config.get("url"),
            "timeout_ms": config.get("timeout_ms"),
            "auth_env": config.get("auth_env"),
            "label": config.get("label"),
            "model": config.get("model"),
            "base_url": config.get("base_url"),
            "provider": config.get("provider"),
            "temperature": config.get("temperature"),
        }
        agent = build_agent(spec, run["kind"], self.settings)
        steps = self.store.get_steps(run_id)
        decisions = [
            s["decision"]
            for s in steps
            if s.get("decision")
        ]
        deliveries = [
            {
                "step": s["step"],
                "package_id": (s.get("action") or {}).get("package_id"),
                "late": bool((s.get("decision") or {}).get("result", {}).get("late")),
            }
            for s in steps
            if (s.get("action") or {}).get("type") == "deliver"
            and s.get("valid")
            and (s.get("decision") or {}).get("result")
        ]
        session = RunSession(
            run_id=run_id,
            world=world,
            agent=agent,
            agent_desc=descriptor,
            run_meta=run,
            decisions=decisions,
            deliveries=deliveries,
        )
        last = steps[-1] if steps else None
        if last:
            session.last_result = {
                "step": last["step"],
                "ok": last["valid"],
                "message": last["reason"],
            }
        with self._registry_lock:
            self._sessions[run_id] = session
        return session

    def _fuel_budget(self, config: dict[str, Any]) -> float:
        vehicle = config.get("vehicle", {})
        capacity = float(vehicle.get("fuel_capacity_l", 12.0))
        return round(capacity * 0.75, 2)

    def _snapshot_payload(self, session: RunSession) -> dict[str, Any]:
        evaluation = self._evaluate(session)
        run = self.store.get_run(session.run_id, include_state=False) or session.run_meta
        last = self.store.last_step(session.run_id)
        last_step = None
        if last:
            decision = last.get("decision") or {}
            last_step = {
                "step": last["step"],
                "ok": last["valid"],
                "code": decision.get("code", "ok"),
                "reason": last["reason"],
                "latency_ms": last["latency_ms"],
                "agent_error": decision.get("error"),
                "fallback_used": decision.get("fallback_used", False),
                "reasoning": decision.get("reasoning"),
                "action": last["action"],
            }
        return {
            "run": run,
            "state": session.world.snapshot(),
            "evaluation": evaluation,
            "agent": session.agent_desc,
            "last_step": last_step,
        }

    def _evaluate(self, session: RunSession) -> dict[str, Any]:
        return evaluate_run(
            session.world.kind,
            session.world.metrics(),
            session.world.events,
            session.deliveries,
            session.decisions,
            fuel_budget_l=self._fuel_budget(session.world.config),
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        # Serialize snapshot reads with step writes so a poll can never observe a
        # terminal world with stale run metadata.
        with self._lock(run_id):
            session = self._load_session(run_id)
            return self._snapshot_payload(session)

    def list_runs(self, limit: int = 50, offset: int = 0, scenario_id: str | None = None):
        return self.store.list_runs(limit=limit, offset=offset, scenario_id=scenario_id)

    def _persist(self, session: RunSession, status: str | None = None) -> None:
        world = session.world
        updates: dict[str, Any] = {
            "steps": world.step,
            "state": world.to_dict(),
            "terminal_reason": world.terminal_reason,
        }
        if status:
            updates["status"] = status
            session.run_meta["status"] = status
        evaluation = None
        if world.status in {"finished", "failed"}:
            evaluation = self._evaluate(session)
            updates["metrics"] = evaluation
            updates["score"] = evaluation["score"]
            if world.status == "failed":
                updates["status"] = "failed"
                session.run_meta["status"] = "failed"
            else:
                updates["status"] = world.status
                session.run_meta["status"] = world.status
            if session.started_monotonic is not None:
                updates["duration_ms"] = round(
                    (time.monotonic() - session.started_monotonic) * 1000, 2
                )
        self.store.update_run(session.run_id, **updates)
        if evaluation is not None:
            session.run_meta["metrics"] = evaluation
            session.run_meta["score"] = evaluation["score"]
        session.run_meta["steps"] = world.step

    def step(self, run_id: str, *, auto: bool = False) -> dict[str, Any]:
        with self._lock(run_id):
            session = self._load_session(run_id)
            if session.world.status != "running":
                self._persist(session, status=session.world.status)
                return self._snapshot_payload(session)

            if session.run_meta.get("status") == "ready" and not auto:
                session.run_meta["status"] = "running"
                self.store.update_run(run_id, status="running")
            if session.started_monotonic is None:
                session.started_monotonic = time.monotonic()

            observation = session.world.observation()
            observation["run_id"] = run_id
            observation["last_result"] = session.last_result
            legal = observation.get("legal_actions", [])
            context = AgentContext(run_id=run_id, step=session.world.step)

            started = time.perf_counter()
            agent_error: str | None = None
            fallback_used = False
            try:
                decision = session.agent.decide(observation, legal, context)
            except AgentError as exc:
                agent_error = f"{exc.code}: {exc.message}"
                decision = self._safe_fallback(session, observation, legal, exc.message)
                fallback_used = True
            except Exception as exc:  # noqa: BLE001 - third-party agents must not crash a run
                agent_error = f"agent_exception: {exc}"
                decision = self._safe_fallback(session, observation, legal, str(exc))
                fallback_used = True
            measured_latency = round((time.perf_counter() - started) * 1000, 2)

            if agent_error:
                session.consecutive_errors += 1
            else:
                session.consecutive_errors = 0

            action_payload: dict[str, Any] | None = decision.action
            parse_error: str | None = None
            if action_payload is None:
                parse_error = "agent returned no action"
                action_payload = {"type": "wait"}
            try:
                action = Action.parse(action_payload)
            except ActionFormatError as exc:
                parse_error = exc.message
                action = Action.parse({"type": "wait"})

            result = session.world.apply(action)
            world = session.world
            step_record = {
                "step": world.step,
                "time_min": world.time_min,
                "action": action.to_dict(),
                "decision": {
                    "reasoning": decision.reasoning,
                    "latency_ms": measured_latency,
                    "agent_latency_ms": decision.latency_ms,
                    "fallback_used": fallback_used or decision.fallback_used,
                    "error": agent_error or decision.error or parse_error,
                    "raw": decision.raw,
                    "result": result.details,
                    "ok": result.ok,
                    "code": result.code,
                },
                "valid": result.ok,
                "reason": result.message,
                "latency_ms": measured_latency,
                # Snapshots are the recorded transition evidence used by replay.
                # The authoritative world state lives on the run row.
                "state": world.snapshot(),
                "metrics": world.metrics(),
            }
            self.store.add_step(
                run_id=run_id,
                step=step_record["step"],
                time_min=step_record["time_min"],
                action=step_record["action"],
                decision=step_record["decision"],
                valid=result.ok,
                reason=result.message,
                latency_ms=measured_latency,
                state=step_record["state"],
                metrics=step_record["metrics"],
            )
            session.decisions.append(
                {
                    "step": world.step,
                    "latency_ms": measured_latency,
                    "error": step_record["decision"]["error"],
                    "fallback_used": step_record["decision"]["fallback_used"],
                }
            )
            if result.ok and action.type == "deliver":
                session.deliveries.append(
                    {
                        "step": world.step,
                        "package_id": action.package_id,
                        "late": bool(result.details.get("late")),
                    }
                )
            session.last_result = {
                "step": world.step,
                "action": action.to_dict(),
                "ok": result.ok,
                "code": result.code,
                "message": result.message,
            }

            if session.consecutive_errors >= 3 and world.status == "running":
                world.fail("agent_unavailable")

            terminal, reason = world.terminal()
            status = "running"
            if terminal or world.status == "failed":
                status = "failed" if world.status == "failed" else "finished"
                if world.status == "running":
                    world.status = "finished"
                if session.run_meta.get("status") not in {"failed"}:
                    session.run_meta["status"] = status
                world.terminal_reason = reason or world.terminal_reason
            self._persist(session, status=status)
            payload = self._snapshot_payload(session)
            payload["last_step"] = {
                **payload.get("last_step", {}),
                "ok": result.ok,
                "code": result.code,
                "reason": result.message,
                "latency_ms": measured_latency,
                "agent_error": agent_error,
                "action": action.to_dict(),
            }
            return payload

    def _safe_fallback(
        self,
        session: RunSession,
        observation: dict[str, Any],
        legal: list[dict[str, Any]],
        message: str,
    ) -> Decision:
        try:
            builtin_id = default_builtin_for(session.world.kind)
            fallback = make_builtin(builtin_id)
            decision = fallback.decide(observation, legal, AgentContext(session.run_id, 0))
            return Decision(
                action=decision.action,
                reasoning=f"Agent unavailable ({message}); safe fallback used.",
                fallback_used=True,
                error=message,
            )
        except Exception:  # noqa: BLE001
            return Decision(
                action={"type": "wait"},
                reasoning=f"Agent unavailable ({message}); waiting.",
                fallback_used=True,
                error=message,
            )

    def start(self, run_id: str, delay_ms: int = 250) -> dict[str, Any]:
        delay_ms = max(0, min(MAX_AUTOPLAY_DELAY_MS, int(delay_ms)))
        with self._lock(run_id):
            session = self._load_session(run_id)
            if session.world.status in {"finished", "failed"}:
                return self._snapshot_payload(session)
            if session.thread and session.thread.is_alive():
                return self._snapshot_payload(session)
            session.stop_event.clear()
            session.run_meta["status"] = "running"
            self.store.update_run(run_id, status="running")
            if session.started_monotonic is None:
                session.started_monotonic = time.monotonic()

            def loop() -> None:
                try:
                    while not session.stop_event.is_set():
                        with self._lock(run_id):
                            if session.stop_event.is_set() or session.world.status != "running":
                                break
                            self.step(run_id, auto=True)
                        if delay_ms:
                            if session.stop_event.wait(delay_ms / 1000.0):
                                break
                        else:
                            time.sleep(0)
                except Exception as exc:  # noqa: BLE001
                    traceback.print_exc()
                    with self._lock(run_id):
                        session.world.fail("internal_error")
                        self.store.update_run(
                            run_id, status="failed", error=f"{exc}", terminal_reason="internal_error"
                        )
                finally:
                    with self._lock(run_id):
                        if session.world.status == "running":
                            self.store.update_run(run_id, status="paused")

            thread = threading.Thread(target=loop, name=f"simworld-run-{run_id}", daemon=True)
            session.thread = thread
            thread.start()
            return self._snapshot_payload(session)

    def pause(self, run_id: str) -> dict[str, Any]:
        with self._lock(run_id):
            session = self._load_session(run_id)
            session.stop_event.set()
            thread = session.thread
            if session.world.status == "running":
                session.run_meta["status"] = "paused"
                self.store.update_run(run_id, status="paused")
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock(run_id):
            return self._snapshot_payload(session)

    def reset(self, run_id: str) -> dict[str, Any]:
        with self._lock(run_id):
            session = self._load_session(run_id)
            session.stop_event.set()
            thread = session.thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock(run_id):
            run = self.store.get_run(run_id)
            if run is None:
                raise KeyError(run_id)
            world = world_from_state(copy.deepcopy(run["initial_state"]))
            session.world = world
            session.decisions = []
            session.deliveries = []
            session.last_result = None
            session.consecutive_errors = 0
            session.started_monotonic = None
            session.stop_event = threading.Event()
            session.thread = None
            self.store.clear_steps(run_id)
            self.store.update_run(
                run_id,
                status="ready",
                steps=0,
                state=world.to_dict(),
                terminal_reason=None,
                score=None,
                metrics=None,
                error=None,
                duration_ms=None,
            )
            session.run_meta["status"] = "ready"
            return self._snapshot_payload(session)

    def inject_disruption(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock(run_id):
            session = self._load_session(run_id)
            world = session.world
            if world.status != "running":
                raise ValueError("Disruptions can only be injected into a running simulation.")
            event_type = payload.get("type") or "road_closure"
            event = self._build_disruption(session, event_type, payload)
            if event is None:
                raise ValueError("This disruption type is not supported by the current environment.")
            record = world.inject(event)
            if record is None:
                raise ValueError("The disruption had no effect on the current world state.")
            self._persist(session, status="running")
            data = self._snapshot_payload(session)
            data["injected"] = record
            return data

    def _build_disruption(
        self, session: RunSession, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        world = session.world
        rng = random.Random(f"{session.run_id}:{world.step}:{len(world.events)}:{event_type}")

        if isinstance(world, CityWorld):
            if event_type == "road_closure":
                requested = payload.get("edges")
                if isinstance(requested, list) and requested:
                    edges = [str(e) for e in requested if str(e) in world.edges]
                    if not edges:
                        raise ValueError("None of the requested edges exist on the map.")
                    return {
                        "type": "road_closure",
                        "edges": edges,
                        "severity": "critical",
                        "message": "Operator injected a road closure.",
                    }
                from .engine.city import parse_node

                vx, vy = parse_node(world.vehicle["node"])
                candidates = []
                for eid, edge in world.edges.items():
                    if not edge["open"]:
                        continue
                    ax, ay = parse_node(edge["a"])
                    bx, by = parse_node(edge["b"])
                    dist = min(abs(ax - vx) + abs(ay - vy), abs(bx - vx) + abs(by - vy))
                    if 1 <= dist <= 4:
                        candidates.append((dist, eid))
                if not candidates:
                    return None
                candidates.sort()
                shortest = candidates[0][0]
                near = [eid for dist, eid in candidates if dist == shortest]
                chosen = rng.choice(near)
                return {
                    "type": "road_closure",
                    "edges": [chosen],
                    "severity": "critical",
                    "message": f"Live road closure injected on {chosen}.",
                }
            if event_type == "deadline_change":
                pending = [p for p in world.packages.values() if p["status"] != "delivered"]
                if not pending:
                    return None
                pkg = rng.choice(pending)
                return {
                    "type": "deadline_change",
                    "package_id": pkg["id"],
                    "delta_min": int(payload.get("delta_min") or -10),
                    "severity": "warning",
                    "message": f"Live deadline change for {pkg['id']}.",
                }
            if event_type == "fuel_cut":
                stations = [node for node in world.stations if node != world.depot]
                if not stations:
                    return None
                node = rng.choice(sorted(stations))
                return {
                    "type": "station_stock",
                    "node": node,
                    "stock_l": 0.0,
                    "severity": "critical",
                    "message": f"Live fuel shortage: station {node} runs dry.",
                }
            return None

        # Traffic control
        if event_type in {"road_closure", "incident"}:
            nodes = sorted(world.signals)
            busy = max(
                nodes,
                key=lambda n: sum(len(q) for q in world.queues[n].values()),
            )
            approach = rng.choice(["N", "S", "E", "W"])
            return {
                "type": "incident",
                "intersection": busy,
                "approach": approach,
                "duration_ticks": int(payload.get("duration_ticks") or 12),
                "severity": "critical",
                "message": f"Live lane incident at {busy} ({approach} approach).",
            }
        if event_type == "surge":
            nodes = sorted(world.signals)
            node = rng.choice(nodes)
            return {
                "type": "surge",
                "intersection": node,
                "approaches": ["N", "S", "E", "W"],
                "count": int(payload.get("count") or 3),
                "severity": "warning",
                "message": f"Live traffic surge at {node}.",
            }
        return None

    def replay(self, run_id: str) -> dict[str, Any]:
        with self._lock(run_id):
            run = self.store.get_run(run_id)
            if run is None:
                raise KeyError(run_id)
            steps = self.store.get_steps(run_id)
            evaluation = None
            if run.get("metrics"):
                evaluation = run["metrics"]
            else:
                session = self._load_session(run_id)
                evaluation = self._evaluate(session)
        initial_world = world_from_state(copy.deepcopy(run["initial_state"]))
        return {
            "run": {k: v for k, v in run.items() if k not in {"state", "initial_state"}},
            "agent": run["agent"],
            "initial_state": run["initial_state"],
            "initial_snapshot": initial_world.snapshot(),
            "steps": steps,
            "evaluation": evaluation,
            "step_count": len(steps),
        }

    # ------------------------------------------------------------- experiments
    def create_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenario_id = str(payload.get("scenario_id") or "")
        scenario = SCENARIO_BY_ID.get(scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario '{scenario_id}'.")
        seeds = payload.get("seeds") or [7, 11, 23]
        if not isinstance(seeds, list) or not seeds:
            raise ValueError("seeds must be a non-empty array.")
        if len(seeds) > 10:
            raise ValueError("At most 10 seeds per experiment.")
        for seed in seeds:
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                raise ValueError("Every seed must be a non-negative integer.")
        agents = payload.get("agents") or [
            {"type": "builtin", "id": default_builtin_for(scenario["kind"])}
        ]
        if not isinstance(agents, list) or not agents:
            raise ValueError("agents must be a non-empty array.")
        if len(seeds) * len(agents) > MAX_EXPERIMENT_RUNS:
            raise ValueError(
                f"Experiment would create {len(seeds) * len(agents)} runs; limit is {MAX_EXPERIMENT_RUNS}."
            )
        options = payload.get("options") or {}
        if not isinstance(options, dict):
            raise ValueError("options must be an object.")
        # Validate everything before persisting anything.
        build_config(scenario_id, int(seeds[0]), options)
        for spec in agents:
            build_agent(spec, scenario["kind"], self.settings)

        total = len(seeds) * len(agents)
        experiment_id = self.store.create_experiment(
            scenario_id=scenario_id,
            kind=scenario["kind"],
            config={"seeds": seeds, "agents": agents, "options": options},
            total_runs=total,
        )

        def runner() -> None:
            run_ids: list[str] = []
            try:
                for seed in seeds:
                    for spec in agents:
                        run = self.create_run(
                            {
                                "scenario_id": scenario_id,
                                "seed": int(seed),
                                "options": options,
                                "agent": spec,
                            }
                        )
                        run_id = run["run"]["id"]
                        run_ids.append(run_id)
                        self.store.link_experiment_run(experiment_id, run_id)
                        run["run"]["status"] = "running"
                        self.store.update_run(run_id, status="running")
                        self._run_to_completion(run_id)
                        self.store.update_experiment(
                            experiment_id,
                            completed_runs=len(run_ids),
                        )
                runs = [self.store.get_run(rid) for rid in run_ids]
                runs = [r for r in runs if r]
                overall = aggregate(runs)
                by_agent: dict[str, Any] = {}
                for spec in agents:
                    descriptor = build_agent(spec, scenario["kind"], self.settings)
                    agent_id = getattr(descriptor, "id", spec.get("id", "agent"))
                    subset = [
                        r
                        for r in runs
                        if r["agent"].get("id") == agent_id
                    ]
                    by_agent[getattr(descriptor, "label", agent_id)] = aggregate(subset)
                self.store.update_experiment(
                    experiment_id,
                    status="finished",
                    aggregate={
                        "overall": overall,
                        "by_agent": by_agent,
                        "runs": [
                            {
                                "id": r["id"],
                                "seed": r["seed"],
                                "agent": r["agent"].get("label"),
                                "status": r["status"],
                                "score": r["score"],
                                "metrics": r["metrics"],
                                "terminal_reason": r["terminal_reason"],
                            }
                            for r in runs
                        ],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.store.update_experiment(
                    experiment_id, status="failed", error=f"{exc}"
                )

        thread = threading.Thread(
            target=runner, name=f"simworld-experiment-{experiment_id}", daemon=True
        )
        self._experiments[experiment_id] = thread
        thread.start()
        return self.store.get_experiment(experiment_id) or {}

    def _run_to_completion(self, run_id: str, max_steps: int = MAX_STEPS_PER_RUN) -> None:
        session = self._load_session(run_id)
        session.started_monotonic = session.started_monotonic or time.monotonic()
        for _ in range(max_steps):
            with self._lock(run_id):
                if session.world.status != "running":
                    break
                self.step(run_id, auto=True)
            if session.world.status != "running":
                break
        with self._lock(run_id):
            if session.world.status == "running":
                session.world.fail("step_limit")
                self._persist(session, status="failed")

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        return self.store.get_experiment(experiment_id)

    def list_experiments(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.store.list_experiments(limit=limit)

    # ------------------------------------------------------------------- misc
    def test_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenario_id = payload.get("scenario_id") or "city-logistics/standard"
        scenario = SCENARIO_BY_ID.get(scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario '{scenario_id}'.")
        spec = payload.get("agent") or {}
        agent = build_agent(spec, scenario["kind"], self.settings)
        world = build_world(scenario_id, 7, None)
        observation = world.observation()
        legal = observation["legal_actions"]
        started = time.perf_counter()
        try:
            decision = agent.decide(
                observation, legal, AgentContext(run_id="connection-test", step=0)
            )
        except AgentError as exc:
            return {
                "ok": False,
                "code": exc.code,
                "error": exc.message,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "protocol": "simworld.agent.v1",
            }
        latency = round((time.perf_counter() - started) * 1000, 2)
        action = decision.action
        try:
            parsed = Action.parse(action)
            valid_action = True
            parsed_action = parsed.to_dict()
        except ActionFormatError as exc:
            valid_action = False
            parsed_action = action
            return {
                "ok": False,
                "code": "invalid_action",
                "error": exc.message,
                "latency_ms": latency,
                "protocol": "simworld.agent.v1",
            }
        legal_keys = {json.dumps(a, sort_keys=True) for a in legal}
        is_legal = json.dumps(parsed_action, sort_keys=True) in legal_keys
        probe_world = build_world(scenario_id, 7, None)
        result = probe_world.apply(Action.parse(parsed_action))
        return {
            "ok": True,
            "latency_ms": latency,
            "agent_latency_ms": decision.latency_ms,
            "action": parsed_action,
            "action_was_offered": is_legal,
            "engine_accepted": result.ok,
            "engine_result": result.message,
            "reasoning": decision.reasoning,
            "fallback_used": decision.fallback_used,
            "error": decision.error,
            "protocol": "simworld.agent.v1",
        }

    def stats(self) -> dict[str, Any]:
        return {
            "runs": self.store.count_runs(),
            "experiments": len(self.store.list_experiments(limit=200)),
            "scenarios": len(SCENARIO_BY_ID),
        }