"""OpenAI-compatible LLM agent.

Used for model-driven decisions and explanations. The engine still validates
every proposed action; if the model is unavailable or returns unusable output,
the run falls back to a deterministic strategy and records that honestly.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from typing import Any

import httpx

from ..engine.actions import Action, ActionFormatError
from .base import AgentContext, AgentError, Decision
from .builtins import default_builtin_for, make_builtin

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen2.5:1.5b-instruct"

SYSTEM_PROMPT = """You control one agent inside SimWorld, a deterministic simulator.

Choose exactly ONE action from the supplied legal_actions. Never invent ids or fields.

Delivery policy:
1. If a package in cargo can be delivered here, deliver the one with the earliest deadline.
2. If fuel is below 25% and a refuel action is offered, refuel.
3. If at the depot with free capacity and packages are waiting, load a batch (2-3 packages) prioritising the earliest deadlines and nearby drops.
4. Otherwise move one hop toward the most urgent undelivered package. Use each package's next_hop field.
5. Wait only when no progress is possible.

Traffic policy:
- Switch the intersection where the opposing queue is largest and a switch is offered.
- Respect the minimum green constraint; never try a switch that is not in legal_actions.

Reply with only JSON. Example:
{"action": {"type": "move", "target": "3,2"}, "reasoning": "Earliest deadline is two hops east."}
No markdown, no code fences, no extra keys."""


class LLMAgent:
    kind = "llm"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        provider: str = "openai_compatible",
        temperature: float = 0.0,
        timeout_s: float = 20.0,
        label: str | None = None,
        environment: str = "city_logistics",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider = provider
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.id = f"llm-{model}"
        self.label = label or f"LLM · {model}"
        self.environment = environment
        self._fallback = make_builtin(default_builtin_for(environment))
        self.last_error: str | None = None
        self._plan: dict[str, Any] | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _next_hop(
        adjacency: dict[str, list[str]], start: str, goal: str, closed: set[str]
    ) -> str | None:
        if start == goal:
            return start
        seen = {start}
        queue: deque[list[str]] = deque([[start]])
        while queue:
            path = queue.popleft()
            node = path[-1]
            for neighbour in adjacency.get(node, []):
                if neighbour in seen:
                    continue
                key = "|".join(sorted((node, neighbour), key=lambda n: tuple(int(v) for v in n.split(","))))
                if key in closed:
                    continue
                if neighbour == goal:
                    return neighbour
                seen.add(neighbour)
                queue.append(path + [neighbour])
        return None

    @staticmethod
    def _path(
        adjacency: dict[str, list[str]], start: str, goal: str, closed: set[str]
    ) -> list[str] | None:
        if start == goal:
            return [start]
        seen = {start}
        queue: deque[list[str]] = deque([[start]])
        while queue:
            path = queue.popleft()
            node = path[-1]
            for neighbour in adjacency.get(node, []):
                if neighbour in seen:
                    continue
                key = "|".join(sorted((node, neighbour), key=lambda n: tuple(int(v) for v in n.split(","))))
                if key in closed:
                    continue
                if neighbour == goal:
                    return path + [neighbour]
                seen.add(neighbour)
                queue.append(path + [neighbour])
        return None

    def _compact_view(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Small, decision-relevant view. Keeps prompts short enough for local models."""
        kind = observation.get("kind")
        if kind == "city_logistics":
            vehicle = observation["vehicle"]
            adjacency = observation["adjacency"]
            closed = set(observation.get("closed_edges", []))
            node = vehicle["node"]
            packages = []
            for pkg in observation["packages"]:
                if pkg["status"] == "delivered":
                    continue
                if pkg["status"] != "in_transit" and node != observation["depot"]:
                    continue
                item = {
                    "id": pkg["id"],
                    "dest": pkg["dest"],
                    "deadline_min": pkg["deadline_min"],
                    "status": pkg["status"],
                    "next_hop": self._next_hop(adjacency, node, pkg["dest"], closed),
                }
                packages.append(item)
            moves = [a for a in legal_actions if a.get("type") == "move"]
            delivers = [a for a in legal_actions if a.get("type") == "deliver"]
            refuels = [a for a in legal_actions if a.get("type") == "refuel"]
            waits = [a for a in legal_actions if a.get("type") == "wait"]
            singles = [
                a for a in legal_actions
                if a.get("type") == "pickup" and len(a.get("package_ids", [])) == 1
            ]
            batches = [
                a for a in legal_actions
                if a.get("type") == "pickup" and len(a.get("package_ids", [])) > 1
            ]
            if delivers:
                # Do not offer movement that abandons a reachable drop.
                curated = delivers + waits
            elif vehicle["node"] == observation["depot"] and singles:
                # At the depot, loading is the only productive decision.
                curated = singles[:6] + batches[:2] + waits
            else:
                curated = moves + refuels + waits
                if singles:
                    curated += singles[:3]
            view = {
                "step": observation["step"],
                "time_min": observation["time_min"],
                "objective": observation["objective"],
                "van": {
                    "node": node,
                    "fuel_l": vehicle["fuel_l"],
                    "cargo": [c["id"] for c in vehicle["cargo"]],
                    "capacity": vehicle["capacity"],
                },
                "depot": observation["depot"],
                "next_hop_to_depot": self._next_hop(adjacency, node, observation["depot"], closed),
                "packages": packages,
                "stations": observation["stations"],
                "closed_edges": sorted(closed)[:6],
            }
            return view, curated

        if kind == "traffic_control":
            view = {
                "step": observation["step"],
                "objective": observation["objective"],
                "min_green_ticks": observation["min_green_ticks"],
                "intersections": [
                    {
                        "id": item["id"],
                        "phase": item["phase"],
                        "queues": item["queues"],
                        "green_for": item["green_for_ticks"],
                        "oldest_wait": item["oldest_wait_ticks"],
                    }
                    for item in observation["intersections"]
                ],
            }
            return view, legal_actions

        compact = {
            key: value
            for key, value in observation.items()
            if key not in {"legal_actions", "recent_events", "adjacency"}
        }
        return compact, legal_actions

    @staticmethod
    def _coerce_action(parsed: dict[str, Any]) -> dict[str, Any]:
        raw = parsed.get("action")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if text.startswith("{") and text.endswith("}"):
                nested = json.loads(text)
                if isinstance(nested, dict):
                    return nested
            sibling = {
                key: value
                for key, value in parsed.items()
                if key not in {"action", "reasoning", "explanation", "thought"}
            }
            sibling["type"] = text
            return sibling
        if isinstance(parsed.get("type"), str):
            return {
                key: value
                for key, value in parsed.items()
                if key not in {"reasoning", "explanation", "thought"}
            }
        raise ValueError("Model did not return an action object.")

    def _payload(
        self,
        observation: dict[str, Any],
        legal_actions: list[dict[str, Any]],
        actions_override: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        view, curated = self._compact_view(observation, legal_actions)
        user = {
            "task": "Choose exactly one action from legal_actions. Reply with JSON only.",
            "observation": view,
            "legal_actions": actions_override if actions_override is not None else curated,
        }
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "stream": False,
            "max_tokens": 140,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
            ],
        }
        if self.provider in {"openai", "openai_compatible", "openrouter"}:
            body["response_format"] = {"type": "json_object"}
        if self.provider == "ollama":
            body["response_format"] = {"type": "json_object"}
        return body

    def _call(self, body: dict[str, Any]) -> str:
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout_s, trust_env=False) as client:
                response = client.post(url, json=body, headers=self._headers())
                if response.status_code == 400 and "response_format" in body:
                    body = {k: v for k, v in body.items() if k != "response_format"}
                    response = client.post(url, json=body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise AgentError("llm_timeout", f"Model did not answer within {self.timeout_s:.0f}s.") from exc
        except httpx.HTTPError as exc:
            raise AgentError("llm_unreachable", f"Could not reach model endpoint: {exc}") from exc
        if response.status_code == 401:
            raise AgentError("llm_unauthorized", "Model endpoint rejected the API key.")
        if response.status_code >= 400:
            detail = response.text[:200].replace(self.api_key or "\0", "[redacted]")
            raise AgentError("llm_http_error", f"Model endpoint returned HTTP {response.status_code}: {detail}")
        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AgentError("llm_bad_response", "Model response did not match the chat-completions schema.") from exc

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found")
        return json.loads(text[start : end + 1])

    def decide(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        if observation.get("kind") == "city_logistics":
            return self._decide_city(observation, legal_actions, context)
        return self._decide_direct(observation, legal_actions, context)

    def _decide_city(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        """Model chooses goals; a deterministic router emits validated moves.

        Asking a small local model for raw hops produced spatial nonsense, so the
        model selects the package or batch and the router handles navigation. The
        model still decides strategy, and the engine still validates every move.
        """
        vehicle = observation["vehicle"]
        node = vehicle["node"]
        packages = {pkg["id"]: pkg for pkg in observation["packages"]}
        adjacency = observation["adjacency"]
        closed = set(observation.get("closed_edges", []))
        stations = {s["node"]: float(s["stock_l"]) for s in observation["stations"]}
        step = observation["step"]
        fuel = float(vehicle["fuel_l"])
        capacity = float(vehicle["fuel_capacity_l"])
        consumption = float(vehicle["consumption_l_per_km"])
        edge_km = float(observation["edge_km"])

        def route_to(dest: str) -> list[str] | None:
            return self._path(adjacency, node, dest, closed)

        delivers = [a for a in legal_actions if a.get("type") == "deliver"]
        if delivers:
            self._plan = None
            delivers.sort(key=lambda a: packages[a["package_id"]]["deadline_min"])
            chosen = packages[delivers[0]["package_id"]]
            return Decision(
                action=delivers[0],
                reasoning=f"At {chosen['dest_label']}; delivering {chosen['id']} due at t+{chosen['deadline_min']} min.",
            )

        last = observation.get("last_result") or {}
        if last.get("code") == "insufficient_fuel" and fuel < 0.2:
            self._plan = None
            return Decision(
                action={"type": "wait"},
                reasoning="Stranded: fuel is exhausted and no adjacent move is possible.",
            )

        if fuel < capacity * 0.5:
            if node in stations and stations[node] > 0.01:
                return Decision(
                    action={"type": "refuel", "amount": 5.0},
                    reasoning="Fuel guard: halftank or less while at a station.",
                )
            options = []
            for station, stock in stations.items():
                if stock <= 0.01:
                    continue
                path = route_to(station)
                if path is None or len(path) < 2:
                    continue
                cost = (len(path) - 1) * edge_km * consumption
                if fuel >= cost + 0.4:
                    options.append((len(path), station, path))
            if options:
                options.sort()
                _, station, path = options[0]
                self._plan = {
                    "dest": station,
                    "until": step + len(path) + 4,
                    "package": "fuel stop",
                }
                return Decision(
                    action={"type": "move", "target": path[1]},
                    reasoning=f"Fuel guard: proactively refuelling at {station} before continuing.",
                )

        plan = self._plan
        if plan:
            if step <= int(plan["until"]):
                path = route_to(str(plan["dest"]))
                if path and len(path) > 1:
                    return Decision(
                        action={"type": "move", "target": path[1]},
                        reasoning=(
                            f"Following the model-selected target {plan['package']} "
                            f"toward {plan['dest']}."
                        ),
                    )
            self._plan = None

        # Fuel guard: divert before the tank cannot reach a station.
        if fuel < 1.7:
            candidates = []
            for station, stock in stations.items():
                if stock <= 0.01:
                    continue
                path = route_to(station)
                if path is None:
                    continue
                cost = max(0, len(path) - 1) * edge_km * consumption
                if fuel >= cost + 0.15:
                    candidates.append((len(path), station, path))
            if candidates:
                candidates.sort()
                _, station, path = candidates[0]
                if len(path) > 1:
                    self._plan = {
                        "dest": station,
                        "until": step + len(path) + 4,
                        "package": "fuel stop",
                    }
                    return Decision(
                        action={"type": "move", "target": path[1]},
                        reasoning=f"Fuel guard: diverting to station {station} before the tank runs dry.",
                    )

        pickups = [a for a in legal_actions if a.get("type") == "pickup"]
        if node == observation["depot"] and pickups and len(vehicle["cargo"]) < int(vehicle["capacity"]):
            singles = [a for a in pickups if len(a.get("package_ids", [])) == 1]
            batches = [a for a in pickups if len(a.get("package_ids", [])) > 1]
            curated = singles[:6] + batches[:2] + [a for a in legal_actions if a.get("type") == "wait"]
            decision = self._ask(observation, legal_actions, curated)
            if decision and decision.action and decision.action.get("type") == "pickup":
                return decision
            fallback = batches[0] if batches else singles[0]
            return Decision(
                action=fallback,
                reasoning="Model output unusable for the loading decision; deterministic fallback batch selected.",
                fallback_used=True,
                error=decision.error if decision else "model unavailable",
            )

        cargo_ids = {entry["id"] for entry in vehicle["cargo"]}
        if not cargo_ids and node != observation["depot"]:
            depot_route = route_to(observation["depot"])
            if depot_route and len(depot_route) > 1:
                self._plan = {
                    "dest": observation["depot"],
                    "until": step + len(depot_route) + 4,
                    "package": "depot",
                }
                return Decision(
                    action={"type": "move", "target": depot_route[1]},
                    reasoning="Van is empty; returning to the depot for the next batch.",
                )

        candidates: dict[str, dict[str, Any]] = {}
        for pkg in packages.values():
            if pkg["status"] == "delivered" or pkg["id"] not in cargo_ids:
                continue
            path = route_to(pkg["dest"])
            if not path or len(path) < 2:
                continue
            hop = path[1]
            current = candidates.get(hop)
            if current is None or pkg["deadline_min"] < current["deadline_min"]:
                candidates[hop] = pkg
        if not candidates:
            return Decision(action={"type": "wait"}, reasoning="No reachable drop remains.")

        moves = [{"type": "move", "target": hop} for hop in sorted(candidates)]
        curated = moves + [a for a in legal_actions if a.get("type") in {"refuel", "wait"}]
        decision = self._ask(observation, legal_actions, curated)
        if decision and decision.action and decision.action.get("type") == "move":
            target = decision.action.get("target")
            pkg = candidates.get(target)
            if pkg:
                path = route_to(pkg["dest"])
                self._plan = {
                    "dest": pkg["dest"],
                    "until": step + (len(path) if path else 10) + 6,
                    "package": pkg["id"],
                }
                decision.reasoning = (
                    f"Model target {pkg['id']} ? {pkg['dest_label']}. {decision.reasoning or ''}".strip()
                )
                return decision
        if decision and decision.action and decision.action.get("type") in {"refuel", "wait"}:
            return decision
        return Decision(
            action={"type": "wait"},
            reasoning="Model did not select a reachable target; deterministic fallback is holding.",
            fallback_used=True,
            error=decision.error if decision else "model unavailable",
        )

    def _ask(
        self,
        observation: dict[str, Any],
        legal_actions: list[dict[str, Any]],
        actions_override: list[dict[str, Any]],
    ) -> Decision | None:
        started = time.perf_counter()
        try:
            content = self._call(self._payload(observation, legal_actions, actions_override))
            parsed = self._extract_json(content)
            raw_action = self._coerce_action(parsed)
            action = Action.parse(raw_action)
            reasoning = parsed.get("reasoning") or parsed.get("explanation")
            if reasoning is not None and not isinstance(reasoning, str):
                reasoning = None
            if reasoning and len(reasoning) > 400:
                reasoning = reasoning[:400] + "?"
            return Decision(
                action=action.to_dict(),
                reasoning=reasoning or "Model-selected action.",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except (AgentError, ActionFormatError, ValueError, json.JSONDecodeError) as exc:
            self.last_error = getattr(exc, "message", str(exc))
            return Decision(
                action=None,
                reasoning=f"Model output unusable ({self.last_error}).",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                fallback_used=True,
                error=self.last_error,
            )

    def _decide_direct(
        self, observation: dict[str, Any], legal_actions: list[dict[str, Any]], context: AgentContext
    ) -> Decision:
        started = time.perf_counter()
        try:
            content = self._call(self._payload(observation, legal_actions))
            parsed = self._extract_json(content)
            raw_action = self._coerce_action(parsed)
            action = Action.parse(raw_action)
            reasoning = parsed.get("reasoning") or parsed.get("explanation")
            if reasoning is not None and not isinstance(reasoning, str):
                reasoning = None
            if reasoning and len(reasoning) > 400:
                reasoning = reasoning[:400] + "…"
            return Decision(
                action=action.to_dict(),
                reasoning=reasoning or "Model-selected action.",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except (AgentError, ActionFormatError, ValueError, json.JSONDecodeError) as exc:
            message = getattr(exc, "message", str(exc))
            self.last_error = message
            fallback = self._fallback.decide(observation, legal_actions, context)
            return Decision(
                action=fallback.action,
                reasoning=(
                    f"Model output unusable ({message}). Deterministic fallback "
                    f"'{self._fallback.label}' chose {fallback.action}."
                ),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                fallback_used=True,
                error=message,
            )


def llm_config_from_env() -> dict[str, Any]:
    key_env = os.getenv("SIMWORLD_LLM_API_KEY_ENV", "OPENAI_API_KEY")
    return {
        "base_url": os.getenv("SIMWORLD_LLM_BASE_URL", DEFAULT_BASE_URL),
        "model": os.getenv("SIMWORLD_LLM_MODEL", DEFAULT_MODEL),
        "api_key": os.getenv(key_env) or os.getenv("SIMWORLD_LLM_API_KEY"),
        "provider": os.getenv("SIMWORLD_LLM_PROVIDER", "openai_compatible"),
        "timeout_s": float(os.getenv("SIMWORLD_LLM_TIMEOUT_S", "20")),
    }


def probe_model(base_url: str, model: str, api_key: str | None, timeout_s: float = 4.0) -> dict[str, Any]:
    """Check whether the configured OpenAI-compatible model is reachable."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=timeout_s, trust_env=False) as client:
            response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return {"available": False, "error": f"unreachable: {exc}", "model": model, "base_url": base_url}
    if response.status_code == 401:
        return {"available": False, "error": "unauthorized", "model": model, "base_url": base_url}
    if response.status_code >= 400:
        return {
            "available": False,
            "error": f"HTTP {response.status_code}",
            "model": model,
            "base_url": base_url,
        }
    try:
        data = response.json()
        ids = [m.get("id") for m in data.get("data", [])]
    except ValueError:
        ids = []
    found = model in ids if ids else None
    return {
        "available": True,
        "model": model,
        "base_url": base_url,
        "models": ids[:40],
        "model_listed": found,
    }