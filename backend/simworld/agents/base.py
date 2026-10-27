"""Provider-independent agent interface.

An agent sees only an observation and a legal-action list. It returns a
candidate action; the engine is the sole authority on whether that action is
legal and what it changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AgentContext:
    run_id: str
    step: int
    timeout_ms: int = 2500
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    action: dict[str, Any] | None
    reasoning: str | None = None
    latency_ms: float = 0.0
    fallback_used: bool = False
    error: str | None = None
    raw: str | None = None


class AgentError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Agent(Protocol):
    id: str
    label: str
    kind: str

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision: ...


def action_key(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    parts = [str(action.get("type"))]
    for key in ("target", "package_id", "package_ids", "intersection", "phase", "amount"):
        if key in action and action[key] is not None:
            value = action[key]
            if isinstance(value, list):
                value = ",".join(str(v) for v in value)
            parts.append(f"{key}={value}")
    return "|".join(parts)