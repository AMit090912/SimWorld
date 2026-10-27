"""SQLite persistence for runs, recorded steps, and experiments."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    scenario_version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    seed INTEGER NOT NULL,
    options_json TEXT NOT NULL,
    agent_json TEXT NOT NULL,
    status TEXT NOT NULL,
    terminal_reason TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    score REAL,
    metrics_json TEXT,
    config_json TEXT NOT NULL,
    initial_state_json TEXT NOT NULL,
    state_json TEXT NOT NULL,
    error TEXT,
    duration_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);

CREATE TABLE IF NOT EXISTS run_steps (
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    time_min INTEGER NOT NULL,
    action_json TEXT,
    decision_json TEXT,
    valid INTEGER NOT NULL,
    reason TEXT,
    latency_ms REAL,
    state_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY (run_id, step),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    aggregate_json TEXT,
    error TEXT,
    total_runs INTEGER NOT NULL DEFAULT 0,
    completed_runs INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_experiments_created ON experiments(created_at DESC);

CREATE TABLE IF NOT EXISTS experiment_runs (
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (experiment_id, run_id),
    FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def _loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class Store:
    def __init__(self, path: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --------------------------------------------------------------------- runs
    def create_run(
        self,
        *,
        scenario_id: str,
        scenario_version: int,
        kind: str,
        seed: int,
        options: dict[str, Any],
        agent: dict[str, Any],
        config: dict[str, Any],
        initial_state: dict[str, Any],
        status: str = "ready",
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._conn.execute(
                """INSERT INTO runs (id, created_at, scenario_id, scenario_version, kind, seed,
                   options_json, agent_json, status, steps, config_json, initial_state_json, state_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    now_iso(),
                    scenario_id,
                    scenario_version,
                    kind,
                    seed,
                    _dumps(options),
                    _dumps(agent),
                    status,
                    0,
                    _dumps(config),
                    _dumps(initial_state),
                    _dumps(initial_state),
                ),
            )
            self._conn.commit()
        return run_id

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        mapping = {
            "status": "status",
            "terminal_reason": "terminal_reason",
            "steps": "steps",
            "score": "score",
            "metrics": "metrics_json",
            "state": "state_json",
            "error": "error",
            "duration_ms": "duration_ms",
            "agent": "agent_json",
        }
        columns, params = [], []
        for key, value in fields.items():
            column = mapping.get(key)
            if column is None:
                raise KeyError(f"Unknown run field '{key}'.")
            columns.append(f"{column}=?")
            params.append(_dumps(value) if key in {"metrics", "state", "agent"} else value)
        params.append(run_id)
        with self._lock:
            self._conn.execute(f"UPDATE runs SET {', '.join(columns)} WHERE id=?", params)
            self._conn.commit()

    def add_step(
        self,
        *,
        run_id: str,
        step: int,
        time_min: int,
        action: dict[str, Any] | None,
        decision: dict[str, Any] | None,
        valid: bool,
        reason: str,
        latency_ms: float,
        state: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO run_steps
                   (run_id, step, time_min, action_json, decision_json, valid, reason, latency_ms,
                    state_json, metrics_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    step,
                    time_min,
                    _dumps(action) if action is not None else None,
                    _dumps(decision) if decision is not None else None,
                    1 if valid else 0,
                    reason,
                    latency_ms,
                    _dumps(state),
                    _dumps(metrics),
                ),
            )
            self._conn.commit()

    def clear_steps(self, run_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM run_steps WHERE run_id=?", (run_id,))
            self._conn.commit()

    def _run_row(self, row: sqlite3.Row, include_state: bool = True) -> dict[str, Any]:
        result = {
            "id": row["id"],
            "created_at": row["created_at"],
            "scenario_id": row["scenario_id"],
            "scenario_version": row["scenario_version"],
            "kind": row["kind"],
            "seed": row["seed"],
            "options": _loads(row["options_json"], {}),
            "agent": _loads(row["agent_json"], {}),
            "status": row["status"],
            "terminal_reason": row["terminal_reason"],
            "steps": row["steps"],
            "score": row["score"],
            "metrics": _loads(row["metrics_json"]),
            "config": _loads(row["config_json"]),
            "error": row["error"],
            "duration_ms": row["duration_ms"],
        }
        if include_state:
            result["state"] = _loads(row["state_json"])
            result["initial_state"] = _loads(row["initial_state_json"])
        return result

    def get_run(self, run_id: str, include_state: bool = True) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._run_row(row, include_state) if row else None

    def list_runs(
        self, limit: int = 50, offset: int = 0, scenario_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM runs"
        params: list[Any] = []
        if scenario_id:
            query += " WHERE scenario_id=?"
            params.append(scenario_id)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._run_row(row, include_state=False) for row in rows]

    def count_runs(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()
        return int(row["n"])

    def get_steps(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY step", (run_id,)
            ).fetchall()
        return [
            {
                "step": row["step"],
                "time_min": row["time_min"],
                "action": _loads(row["action_json"]),
                "decision": _loads(row["decision_json"]),
                "valid": bool(row["valid"]),
                "reason": row["reason"],
                "latency_ms": row["latency_ms"],
                "state": _loads(row["state_json"]),
                "metrics": _loads(row["metrics_json"]),
            }
            for row in rows
        ]

    def last_step(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY step DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "step": row["step"],
            "time_min": row["time_min"],
            "action": _loads(row["action_json"]),
            "decision": _loads(row["decision_json"]),
            "valid": bool(row["valid"]),
            "reason": row["reason"],
            "latency_ms": row["latency_ms"],
            "metrics": _loads(row["metrics_json"]),
        }

    # -------------------------------------------------------------- experiments
    def create_experiment(
        self,
        *,
        scenario_id: str,
        kind: str,
        config: dict[str, Any],
        total_runs: int,
    ) -> str:
        experiment_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._conn.execute(
                """INSERT INTO experiments
                   (id, created_at, scenario_id, kind, config_json, status, total_runs, completed_runs)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    experiment_id,
                    now_iso(),
                    scenario_id,
                    kind,
                    _dumps(config),
                    "running",
                    total_runs,
                    0,
                ),
            )
            self._conn.commit()
        return experiment_id

    def update_experiment(self, experiment_id: str, **fields: Any) -> None:
        mapping = {
            "status": "status",
            "aggregate": "aggregate_json",
            "error": "error",
            "completed_runs": "completed_runs",
            "total_runs": "total_runs",
        }
        columns, params = [], []
        for key, value in fields.items():
            column = mapping.get(key)
            if column is None:
                raise KeyError(f"Unknown experiment field '{key}'.")
            columns.append(f"{column}=?")
            params.append(_dumps(value) if key == "aggregate" else value)
        params.append(experiment_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE experiments SET {', '.join(columns)} WHERE id=?", params
            )
            self._conn.commit()

    def link_experiment_run(self, experiment_id: str, run_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO experiment_runs (experiment_id, run_id) VALUES (?,?)",
                (experiment_id, run_id),
            )
            self._conn.commit()

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM experiments WHERE id=?", (experiment_id,)
            ).fetchone()
            if row is None:
                return None
            run_rows = self._conn.execute(
                """SELECT r.* FROM runs r
                   JOIN experiment_runs er ON er.run_id = r.id
                   WHERE er.experiment_id=?
                   ORDER BY r.created_at, r.rowid""",
                (experiment_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "scenario_id": row["scenario_id"],
            "kind": row["kind"],
            "config": _loads(row["config_json"], {}),
            "status": row["status"],
            "aggregate": _loads(row["aggregate_json"]),
            "error": row["error"],
            "total_runs": row["total_runs"],
            "completed_runs": row["completed_runs"],
            "runs": [self._run_row(r, include_state=False) for r in run_rows],
        }

    def list_experiments(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "scenario_id": row["scenario_id"],
                "kind": row["kind"],
                "config": _loads(row["config_json"], {}),
                "status": row["status"],
                "aggregate": _loads(row["aggregate_json"]),
                "error": row["error"],
                "total_runs": row["total_runs"],
                "completed_runs": row["completed_runs"],
            }
            for row in rows
        ]