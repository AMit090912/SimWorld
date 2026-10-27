"""Pydantic request/response contracts for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AgentSpec(BaseModel):
    type: Literal["builtin", "external", "llm"] = "builtin"
    id: str | None = None
    url: str | None = None
    timeout_ms: int | None = Field(default=None, ge=200, le=10000)
    auth_env: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)
    provider: str | None = Field(default=None, max_length=40)
    temperature: float | None = Field(default=None, ge=0, le=2)
    label: str | None = Field(default=None, max_length=80)

    @field_validator("auth_env")
    @classmethod
    def env_name_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.replace("_", "").isalnum() or not value.upper() == value:
            raise ValueError("auth_env must be an environment variable name (A-Z, 0-9, _).")
        return value


class RunCreate(BaseModel):
    scenario_id: str = Field(min_length=3, max_length=120)
    seed: int = Field(default=7, ge=0, le=2**31 - 1)
    options: dict[str, str] = Field(default_factory=dict)
    agent: AgentSpec | None = None


class StartRequest(BaseModel):
    delay_ms: int = Field(default=300, ge=0, le=2000)


class DisruptionRequest(BaseModel):
    type: str = Field(default="road_closure", max_length=40)
    edges: list[str] | None = None
    delta_min: int | None = Field(default=None, ge=-60, le=60)
    duration_ticks: int | None = Field(default=None, ge=1, le=60)
    count: int | None = Field(default=None, ge=1, le=10)


class AgentTestRequest(BaseModel):
    agent: AgentSpec
    scenario_id: str = "city-logistics/standard"


class ExperimentCreate(BaseModel):
    scenario_id: str = Field(min_length=3, max_length=120)
    seeds: list[int] = Field(default_factory=lambda: [7, 11, 23], min_length=1, max_length=10)
    agents: list[AgentSpec] = Field(min_length=1, max_length=4)
    options: dict[str, str] = Field(default_factory=dict)

    @field_validator("seeds")
    @classmethod
    def seeds_in_range(cls, values: list[int]) -> list[int]:
        for value in values:
            if value < 0 or value > 2**31 - 1:
                raise ValueError("Seeds must be between 0 and 2147483647.")
        return values


class RunList(BaseModel):
    runs: list[dict[str, Any]]
    total: int


class SnapshotResponse(BaseModel):
    run: dict[str, Any]
    state: dict[str, Any]
    evaluation: dict[str, Any]
    agent: dict[str, Any]