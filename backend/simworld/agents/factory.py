"""Build agents from validated API specifications."""

from __future__ import annotations

import os
from typing import Any

from ..config import Settings
from .base import Agent, AgentError
from .builtins import AGENT_METADATA, default_builtin_for, make_builtin
from .external import ExternalAgent
from .llm import LLMAgent

MAX_TIMEOUT_MS = 10000
MIN_TIMEOUT_MS = 200


def build_agent(spec: dict[str, Any], environment: str, settings: Settings) -> Agent:
    agent_type = (spec or {}).get("type")
    if agent_type == "builtin":
        agent_id = spec.get("id") or default_builtin_for(environment)
        try:
            agent = make_builtin(agent_id)
        except KeyError as exc:
            raise AgentError("unknown_agent", str(exc)) from exc
        if environment not in getattr(agent, "environments", [environment]):
            raise AgentError(
                "incompatible_agent",
                f"Built-in agent '{agent_id}' does not support the {environment} environment.",
            )
        return agent

    if agent_type == "external":
        url = spec.get("url")
        if not isinstance(url, str) or not url.strip():
            raise AgentError("invalid_agent", "External agent requires a URL.")
        timeout_ms = int(spec.get("timeout_ms") or 2500)
        if not MIN_TIMEOUT_MS <= timeout_ms <= min(MAX_TIMEOUT_MS, settings.max_agent_timeout_ms):
            raise AgentError(
                "invalid_timeout",
                f"Timeout must be between {MIN_TIMEOUT_MS} and "
                f"{min(MAX_TIMEOUT_MS, settings.max_agent_timeout_ms)} ms.",
            )
        token_env = spec.get("auth_env")
        token = os.getenv(token_env) if isinstance(token_env, str) and token_env else None
        return ExternalAgent(
            url=url.strip(),
            timeout_ms=timeout_ms,
            allow_loopback=settings.allow_loopback_agents,
            auth_token=token,
            label=spec.get("label") or "External HTTP agent",
        )

    if agent_type == "llm":
        model = str(spec.get("model") or settings.llm_model)
        base_url = str(spec.get("base_url") or settings.llm_base_url)
        api_key = settings.llm_api_key
        key_env = spec.get("api_key_env")
        if isinstance(key_env, str) and key_env:
            api_key = os.getenv(key_env) or api_key
        if spec.get("api_key"):
            api_key = str(spec["api_key"])
        return LLMAgent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            provider=str(spec.get("provider") or settings.llm_provider),
            temperature=float(spec.get("temperature") or 0.0),
            timeout_s=float(spec.get("timeout_s") or settings.llm_timeout_s),
            label=spec.get("label"),
            environment=environment,
        )

    raise AgentError("unknown_agent", "Agent type must be 'builtin', 'external', or 'llm'.")


def agent_descriptor(spec: dict[str, Any], agent: Agent, environment: str) -> dict[str, Any]:
    safe = {k: v for k, v in (spec or {}).items() if k not in {"api_key", "token", "auth_token"}}
    return {
        "type": spec.get("type", "builtin"),
        "id": getattr(agent, "id", spec.get("id")),
        "label": getattr(agent, "label", spec.get("label")),
        "config": safe,
        "environment": environment,
    }


def catalogue(settings: Settings) -> dict[str, Any]:
    return {
        "builtin": AGENT_METADATA,
        "modes": [
            {
                "type": "external",
                "label": "External HTTP agent",
                "description": (
                    "SimWorld POSTs an observation to your endpoint and validates the action it "
                    "returns. Request timeout, SSRF checks, and size limits apply."
                ),
                "protocol": "simworld.agent.v1",
                "loopback_allowed": settings.allow_loopback_agents,
            },
            {
                "type": "llm",
                "label": "OpenAI-compatible model",
                "description": (
                    "Model selects a permitted action; the engine still validates every move. "
                    "Runs fall back to a deterministic strategy when the model is unreachable."
                ),
                "configured": bool(settings.llm_api_key) or settings.llm_base_url.startswith("http://127.0.0.1")
                or settings.llm_base_url.startswith("http://localhost"),
                "model": settings.llm_model,
                "base_url": settings.llm_base_url,
                "provider": settings.llm_provider,
            },
        ],
    }