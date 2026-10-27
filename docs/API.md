# API reference

Base: `http://127.0.0.1:8000`. Interactive docs: `/api/docs`. All request and response bodies are
JSON. Errors use `{ "detail": "...", "code": "optional_machine_code" }`.

## Scenarios

### `GET /api/scenarios`

Returns the catalogue, including objectives, constraints, variation axes, defaults, and metric keys.
Only scenarios that execute real rules are listed.

### `GET /api/scenarios/{scenario_id}`

`scenario_id` contains a slash, e.g. `city-logistics/standard`. Returns one scenario.

### `GET /api/scenarios/{scenario_id}/preview?seed=7`

Returns `{ scenario, snapshot }` for a fresh world. Preview worlds are never scored or stored.

### `GET /api/metrics`

Metric definitions with label, unit, direction, description, and score weight.

## Runs

### `POST /api/runs`

```json
{
  "scenario_id": "city-logistics/standard",
  "seed": 7,
  "options": { "disruption_timing": "early", "fuel_supply": "scarce" },
  "agent": { "type": "builtin", "id": "city-baseline" }
}
```

Agent variants:

```json
{ "type": "external", "url": "http://127.0.0.1:9100/agent", "timeout_ms": 2500 }
{ "type": "llm", "model": "qwen2.5:1.5b-instruct", "base_url": "http://127.0.0.1:11434/v1" }
```

Returns `{ run, state, evaluation, agent, last_step }`. `state` is a snapshot; `run.state` is not
included. Run options must be supported by the scenario or the API returns 400.

### `GET /api/runs?limit=40&offset=0&scenario_id=...`

Run history without full state. `total` is the total number of stored runs.

### `GET /api/runs/{id}`

Current `{ run, state, evaluation, agent, last_step }`. Poll this while a run is executing.

### `POST /api/runs/{id}/start`

```json
{ "delay_ms": 300 }
```

Starts a background autoplay thread. `delay_ms` is clamped to 0–2000. Returns the snapshot immediately.

### `POST /api/runs/{id}/pause`

Stops autoplay and marks the run `paused`. The world remains resumable.

### `POST /api/runs/{id}/step`

Advances exactly one tick through the agent → validation → transition → persistence pipeline.
Returns the snapshot plus `last_step`. Invalid actions are reported in `last_step` and do not mutate
the world beyond the clock.

### `POST /api/runs/{id}/reset`

Deletes recorded steps and restores the stored initial state. Returns status `ready`.

### `POST /api/runs/{id}/disrupt`

```json
{ "type": "road_closure" }
{ "type": "road_closure", "edges": ["1,1|2,1"] }
{ "type": "deadline_change", "delta_min": -10 }
{ "type": "fuel_cut" }
{ "type": "incident" }
{ "type": "surge", "count": 3 }
```

Only valid while the world is running. Returns the snapshot plus `injected`. A disruption that has no
effect (for example a closure on an already closed road) returns 400.

### `GET /api/runs/{id}/replay`

```json
{
  "run": { "...": "metadata, config, metrics" },
  "agent": { "...": "descriptor" },
  "initial_state": { "...": "authoritative to_dict world state" },
  "initial_snapshot": { "...": "display snapshot with metrics" },
  "steps": [
    {
      "step": 1,
      "time_min": 2,
      "action": { "type": "pickup", "package_ids": ["PKG-01"] },
      "decision": { "reasoning": "...", "valid": true, "code": "ok", "result": {} },
      "valid": true,
      "reason": "...",
      "latency_ms": 0.4,
      "state": { "...": "snapshot after the step" },
      "metrics": { "...": "engine metrics after the step" }
    }
  ],
  "evaluation": { "...": "final evaluation" },
  "step_count": 63
}
```

Replay consumers should treat `steps[].state` as the recorded evidence. `initial_state` exists for
action-sequence reconstruction and determinism tests.

## Agents

### `GET /api/agents`

Built-in agents plus supported modes. The LLM entry includes a live probe result.

### `GET /api/agents/llm/status`

Probes `/models` on the configured OpenAI-compatible endpoint. Reports `available`, `error`,
`model_listed`, and whether an API key is configured. It never returns the key.

### `POST /api/agents/test`

```json
{
  "scenario_id": "city-logistics/standard",
  "agent": { "type": "external", "url": "http://127.0.0.1:9100/agent", "timeout_ms": 2500 }
}
```

Sends one real observation from seed 7 and reports:

```json
{
  "ok": true,
  "latency_ms": 3.2,
  "action": { "type": "pickup", "package_ids": ["PKG-01"] },
  "action_was_offered": true,
  "engine_accepted": true,
  "engine_result": "Loaded 1 package(s).",
  "reasoning": "...",
  "protocol": "simworld.agent.v1"
}
```

Failures return HTTP 200 with `ok: false` and a machine-readable `code` (`agent_timeout`,
`agent_unreachable`, `endpoint_blocked`, `agent_bad_json`, ...). Invalid agent configuration (missing
URL, unknown type) returns 400.

## Experiments

### `POST /api/experiments`

```json
{
  "scenario_id": "city-logistics/standard",
  "seeds": [7, 11, 23],
  "agents": [
    { "type": "builtin", "id": "city-baseline" },
    { "type": "builtin", "id": "city-greedy" }
  ],
  "options": { "fuel_supply": "scarce" }
}
```

Up to 10 seeds, 4 agents, and 24 total runs. Runs execute in a background thread and are linked to the
experiment. Returns the experiment immediately with `status: "running"`.

### `GET /api/experiments/{id}`

Returns progress, `aggregate.overall`, `aggregate.by_agent` (mean/std/min/max per metric), and one row
per run. Aggregates are computed from stored run evaluations.

### `GET /api/experiments?limit=30`

Recent experiments, without per-run rows.

## External agent protocol

### Request (SimWorld → agent)

```json
{
  "protocol": "simworld.agent.v1",
  "run_id": "7f3a1c9d2e40",
  "step": 12,
  "deadline_ms": 2500,
  "observation": {
    "kind": "city_logistics",
    "vehicle": { "node": "3,2", "fuel_l": 4.8, "cargo": [] },
    "packages": [],
    "adjacency": {},
    "closed_edges": [],
    "stations": [],
    "legal_actions": []
  },
  "legal_actions": []
}
```

### Response (agent → SimWorld)

```json
{
  "action": { "type": "move", "target": "3,3" },
  "reasoning": "One short sentence, optional."
}
```

### Action types

| Type | Fields | Rules |
| --- | --- | --- |
| `move` | `target` | Adjacent node, road open, enough fuel |
| `wait` | none | Always valid |
| `pickup` | `package_id` or `package_ids` | At depot, packages available, capacity |
| `deliver` | `package_id` | Package in cargo, van at its destination |
| `refuel` | `amount` (≤10) | At a station with stock, tank not full |
| `set_phase` | `intersection`, `phase` (`NS`/`EW`) | Traffic only, minimum green satisfied |

Unknown types, unknown fields, wrong types, and duplicate ids are rejected at the schema boundary and
count as agent errors, not engine rejections.

## Limits and status codes

| Status | Meaning |
| --- | --- |
| 200 | Success (including `ok: false` connection diagnostics) |
| 400 | Invalid scenario/options/agent/disruption |
| 404 | Unknown run, scenario, or experiment |
| 413 | Request body over 256 KiB |
| 422 | Pydantic validation failure |
| 429 | Too many connection tests from one client |

Agent response cap: 64 KiB. Agent timeout: 200–10000 ms. Run step cap: 400. Experiment cap: 24 runs.