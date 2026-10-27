"""HTTP agent adapter.

SimWorld POSTs an observation and reads back exactly one action. External
endpoints are untrusted: scheme/host checks, no redirects, hard timeouts, and a
response-size cap apply to every call.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from ..engine.actions import Action, ActionFormatError
from .base import AgentContext, AgentError, Decision

PROTOCOL = "simworld.agent.v1"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_REASONING_CHARS = 2000


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_loopback: bool) -> bool:
    if ip.is_loopback:
        return not allow_loopback
    if ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return False


def validate_endpoint(url: str, allow_loopback: bool) -> None:
    if not isinstance(url, str) or len(url) > 500:
        raise AgentError("invalid_endpoint", "Agent URL must be a string under 500 characters.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AgentError("invalid_endpoint", "Agent URL must use http or https.")
    if parsed.username or parsed.password:
        raise AgentError("invalid_endpoint", "Credentials in the agent URL are not allowed.")
    if not parsed.hostname:
        raise AgentError("invalid_endpoint", "Agent URL is missing a host.")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise AgentError("invalid_endpoint", "Agent URL has an invalid port.")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise AgentError("dns_failure", f"Could not resolve agent host '{host}'.") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise AgentError("dns_failure", f"Agent host '{host}' resolved to no addresses.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _is_blocked_ip(ip, allow_loopback):
            raise AgentError(
                "endpoint_blocked",
                f"Agent host resolves to a non-public address ({address}). "
                "Private, loopback, and link-local targets are blocked by default.",
            )


@dataclass
class ExternalAgent:
    url: str
    timeout_ms: int = 2500
    allow_loopback: bool = True
    auth_token: str | None = None
    id: str = "external"
    label: str = "External HTTP agent"
    kind: str = "external"

    def __post_init__(self) -> None:
        if not (200 <= self.timeout_ms <= 10000):
            raise AgentError("invalid_timeout", "Timeout must be between 200 and 10000 ms.")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        validate_endpoint(self.url, self.allow_loopback)
        payload = {
            "protocol": PROTOCOL,
            "run_id": context.run_id,
            "step": context.step,
            "deadline_ms": self.timeout_ms,
            "observation": observation,
            "legal_actions": legal_actions,
        }
        started = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self.timeout_ms / 1000.0,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(self.url, json=payload, headers=self._headers())
        except httpx.ConnectTimeout as exc:
            raise AgentError(
                "agent_unreachable", f"Could not connect to the agent within {self.timeout_ms} ms."
            ) from exc
        except httpx.TimeoutException as exc:
            raise AgentError(
                "agent_timeout", f"Agent did not respond within {self.timeout_ms} ms."
            ) from exc
        except httpx.HTTPError as exc:
            raise AgentError("agent_unreachable", f"Could not reach agent: {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        if response.status_code != 200:
            raise AgentError(
                "agent_http_error",
                f"Agent returned HTTP {response.status_code}.",
            )
        raw = response.content
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AgentError(
                "agent_response_too_large",
                f"Agent response exceeded {MAX_RESPONSE_BYTES // 1024} KiB.",
            )
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError("agent_bad_json", "Agent response was not valid JSON.") from exc
        if not isinstance(body, dict):
            raise AgentError("agent_bad_response", "Agent response must be a JSON object.")
        if "action" not in body:
            raise AgentError("agent_bad_response", "Agent response is missing the 'action' field.")
        try:
            action = Action.parse(body["action"])
        except ActionFormatError as exc:
            raise AgentError(
                "agent_bad_action", f"Agent action failed schema validation: {exc.message}"
            ) from exc
        reasoning = body.get("reasoning")
        if reasoning is not None and not isinstance(reasoning, str):
            raise AgentError("agent_bad_response", "Field 'reasoning' must be a string.")
        if reasoning and len(reasoning) > MAX_REASONING_CHARS:
            reasoning = reasoning[:MAX_REASONING_CHARS] + "…"
        return Decision(
            action=action.to_dict(),
            reasoning=reasoning,
            latency_ms=latency_ms,
            raw=raw[:4000].decode("utf-8", errors="replace"),
        )