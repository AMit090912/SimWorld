# Example external agent

`external_agent.py` is a complete, dependency-free implementation of the SimWorld agent contract. It
is the reference for anyone writing their own agent.

```bash
python examples/external_agent.py --port 9100
```

Then either:

- open **Agents → External HTTP agent** in the UI, enter `http://127.0.0.1:9100/agent`, and press
  **Test connection**; or
- select the **HTTP** agent mode in the workspace and launch a run; or
- create one over the API:

```bash
curl -s -X POST http://127.0.0.1:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"city-logistics/standard","seed":7,
       "agent":{"type":"external","url":"http://127.0.0.1:9100/agent","timeout_ms":2500}}'
```

## What it does

- **City logistics** — delivers a package when it is standing on its destination, refuels when the tank
  drops below 30%, loads a batch at the depot prioritising the earliest deadlines, and otherwise moves
  one hop toward the most urgent package. When fuel is low it diverts to the nearest station with stock.
- **Traffic control** — switches the intersection with the largest opposing queue pressure, only when a
  switch is offered (so the minimum-green rule is respected).

It uses the same `observation` and `legal_actions` fields as any other agent, and it is exercised by the
test suite (`backend/tests/test_example_agent.py`) against a full engine run.

## Contract summary

Request:

```json
{
  "protocol": "simworld.agent.v1",
  "run_id": "...",
  "step": 12,
  "observation": { "...": "environment state" },
  "legal_actions": [ { "type": "move", "target": "3,3" } ]
}
```

Response:

```json
{ "action": { "type": "move", "target": "3,3" }, "reasoning": "short explanation" }
```

Return exactly one action from `legal_actions`. If you return an action that is well-formed but not
legal, the engine rejects it and counts it — returning a legal action is always the better strategy.
