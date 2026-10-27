"""FastAPI application for SimWorld."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..agents.base import AgentError
from ..agents.llm import probe_model, llm_config_from_env
from ..config import Settings, load_settings
from ..service import RunService
from ..store import Store
from .schemas import (
    AgentTestRequest,
    DisruptionRequest,
    ExperimentCreate,
    RunCreate,
    StartRequest,
)

MAX_BODY_BYTES = 256 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = Store(settings.db_path)
    service = RunService(store, settings)

    app = FastAPI(
        title="SimWorld API",
        version="0.1.0",
        description=(
            "Deterministic simulation and evaluation for AI agents. "
            "Connect an agent over HTTP, run reproducible experiments, and inspect "
            "what actually happened."
        ),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.store = store
    app.state.service = service
    app.state.started_at = time.time()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length")
            if length and int(length) > MAX_BODY_BYTES:
                return JSONResponse(
                    {"detail": f"Request body exceeds {MAX_BODY_BYTES // 1024} KiB."},
                    status_code=413,
                )
        return await call_next(request)

    rate_lock = threading.Lock()
    rate_hits: dict[str, deque[float]] = defaultdict(deque)

    def rate_limited(key: str, limit: int = 12, window_s: float = 60.0) -> bool:
        now = time.monotonic()
        with rate_lock:
            bucket = rate_hits[key]
            while bucket and now - bucket[0] > window_s:
                bucket.popleft()
            if len(bucket) >= limit:
                return True
            bucket.append(now)
            return False

    @app.exception_handler(AgentError)
    async def agent_error_handler(_: Request, exc: AgentError):
        return JSONResponse(
            {"detail": exc.message, "code": exc.code}, status_code=400
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(_: Request, exc: KeyError):
        return JSONResponse(
            {"detail": f"Not found: {exc.args[0] if exc.args else 'unknown'}"}, status_code=404
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # ----------------------------------------------------------------- health
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": "0.1.0",
            "environment": settings.environment,
            "uptime_s": round(time.time() - app.state.started_at, 1),
            "runs": store.count_runs(),
        }

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        return service.stats()

    # -------------------------------------------------------------- scenarios
    @app.get("/api/scenarios")
    def scenarios() -> dict[str, Any]:
        return {"scenarios": service.scenarios()}

    @app.get("/api/scenarios/{scenario_id:path}/preview")
    def scenario_preview(scenario_id: str, seed: int = 7) -> dict[str, Any]:
        return service.scenario_preview(scenario_id, seed)

    @app.get("/api/scenarios/{scenario_id:path}")
    def scenario_detail(scenario_id: str) -> dict[str, Any]:
        scenario = service.scenario(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario_id}'.")
        return scenario

    @app.get("/api/metrics")
    def metrics() -> dict[str, Any]:
        return {"metrics": service.metric_definitions()}

    # ------------------------------------------------------------------ agents
    @app.get("/api/agents")
    def agents() -> dict[str, Any]:
        return service.agent_catalogue()

    @app.get("/api/agents/llm/status")
    def llm_status() -> dict[str, Any]:
        return service.llm_status()

    @app.post("/api/agents/test")
    def agent_test(payload: AgentTestRequest, request: Request) -> dict[str, Any]:
        client = request.client.host if request.client else "unknown"
        if rate_limited(f"agent-test:{client}"):
            raise HTTPException(status_code=429, detail="Too many connection tests. Wait a minute.")
        return service.test_agent(payload.model_dump())

    # -------------------------------------------------------------------- runs
    @app.post("/api/runs")
    def create_run(payload: RunCreate) -> dict[str, Any]:
        return service.create_run(payload.model_dump(exclude_none=True))

    @app.get("/api/runs")
    def list_runs(limit: int = 40, offset: int = 0, scenario_id: str | None = None) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        runs = service.list_runs(limit=limit, offset=offset, scenario_id=scenario_id)
        return {"runs": runs, "total": store.count_runs()}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return service.get_run(run_id)

    @app.post("/api/runs/{run_id}/start")
    def start_run(run_id: str, payload: StartRequest | None = None) -> dict[str, Any]:
        return service.start(run_id, (payload or StartRequest()).delay_ms)

    @app.post("/api/runs/{run_id}/pause")
    def pause_run(run_id: str) -> dict[str, Any]:
        return service.pause(run_id)

    @app.post("/api/runs/{run_id}/step")
    def step_run(run_id: str) -> dict[str, Any]:
        return service.step(run_id)

    @app.post("/api/runs/{run_id}/reset")
    def reset_run(run_id: str) -> dict[str, Any]:
        return service.reset(run_id)

    @app.post("/api/runs/{run_id}/disrupt")
    def disrupt_run(run_id: str, payload: DisruptionRequest) -> dict[str, Any]:
        return service.inject_disruption(run_id, payload.model_dump(exclude_none=True))

    @app.get("/api/runs/{run_id}/replay")
    def replay_run(run_id: str) -> dict[str, Any]:
        return service.replay(run_id)

    # ------------------------------------------------------------- experiments
    @app.post("/api/experiments")
    def create_experiment(payload: ExperimentCreate) -> dict[str, Any]:
        return service.create_experiment(payload.model_dump(exclude_none=True))

    @app.get("/api/experiments")
    def list_experiments(limit: int = 30) -> dict[str, Any]:
        return {"experiments": service.list_experiments(max(1, min(limit, 100)))}

    @app.get("/api/experiments/{experiment_id}")
    def get_experiment(experiment_id: str) -> dict[str, Any]:
        experiment = service.get_experiment(experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found.")
        return experiment

    # ------------------------------------------------------------------- static
    static_dir = Path(settings.static_dir) if settings.static_dir else None
    if static_dir and (static_dir / "index.html").exists():
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found.")
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def root() -> dict[str, Any]:
            return {
                "service": "SimWorld API",
                "hint": "Frontend build not found. Run `npm run build` in frontend/.",
                "docs": "/api/docs",
            }

    @app.on_event("shutdown")
    def shutdown() -> None:
        store.close()

    return app


app = create_app()