"""Environment-driven settings. No secrets are ever written to the database."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "simworld.db"


@dataclass(frozen=True)
class Settings:
    db_path: str
    environment: str
    allow_loopback_agents: bool
    max_agent_timeout_ms: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    llm_provider: str
    llm_timeout_s: float
    cors_origins: tuple[str, ...]
    static_dir: str | None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


def load_settings() -> Settings:
    environment = os.getenv("SIMWORLD_ENV", "development").lower()
    db_path = os.getenv("SIMWORLD_DB_PATH", str(DEFAULT_DB))
    allow_loopback = os.getenv("SIMWORLD_AGENT_ALLOW_LOOPBACK")
    if allow_loopback is None:
        allow_loopback_flag = environment != "production"
    else:
        allow_loopback_flag = allow_loopback.strip().lower() in {"1", "true", "yes", "on"}

    key_env = os.getenv("SIMWORLD_LLM_API_KEY_ENV", "OPENAI_API_KEY")
    origins = os.getenv(
        "SIMWORLD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    static_dir = os.getenv("SIMWORLD_STATIC_DIR", str(BASE_DIR.parent / "frontend" / "dist"))

    return Settings(
        db_path=db_path,
        environment=environment,
        allow_loopback_agents=allow_loopback_flag,
        max_agent_timeout_ms=int(os.getenv("SIMWORLD_MAX_AGENT_TIMEOUT_MS", "10000")),
        llm_base_url=os.getenv("SIMWORLD_LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
        llm_model=os.getenv("SIMWORLD_LLM_MODEL", "qwen2.5:1.5b-instruct"),
        llm_api_key=os.getenv(key_env) or os.getenv("SIMWORLD_LLM_API_KEY"),
        llm_provider=os.getenv("SIMWORLD_LLM_PROVIDER", "openai_compatible"),
        llm_timeout_s=float(os.getenv("SIMWORLD_LLM_TIMEOUT_S", "20")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        static_dir=static_dir if os.path.isdir(static_dir) else None,
    )