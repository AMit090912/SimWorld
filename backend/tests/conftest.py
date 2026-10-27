from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from simworld.api.app import create_app
from simworld.config import Settings
from simworld.service import RunService
from simworld.store import Store


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=str(tmp_path / "simworld-test.db"),
        environment="development",
        allow_loopback_agents=True,
        max_agent_timeout_ms=10000,
        # Deliberately unreachable: tests must not depend on a local model server.
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="test-model",
        llm_api_key=None,
        llm_provider="openai_compatible",
        llm_timeout_s=5.0,
        cors_origins=(),
        static_dir=None,
    )


@pytest.fixture()
def service(settings) -> RunService:
    store = Store(settings.db_path)
    svc = RunService(store, settings)
    yield svc
    store.close()


@pytest.fixture()
def client(settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    app.state.store.close()

@pytest.fixture()
def tempfile_free_store(tmp_path):
    store = Store(str(tmp_path / "reload.db"))
    yield store
    store.close()
