# SimWorld MCP server

A dependency-free Model Context Protocol bridge that exposes SimWorld's evaluation workflow as tools.
It speaks JSON-RPC 2.0 over stdio and calls the SimWorld HTTP API, so it never contains simulation
rules of its own.

```bash
export SIMWORLD_API_URL=http://127.0.0.1:8000
python mcp_server/server.py
```

## Tools

| Tool | Arguments | Result |
| --- | --- | --- |
| `simworld_list_scenarios` | – | Environments, objectives, constraints, variation axes |
| `simworld_start_run` | `scenario_id`, `seed`, `agent_id`, `options` | Score, component metrics, failures, run id |
| `simworld_run_experiment` | `scenario_id`, `seeds`, `agent_ids`, `options` | Per-agent mean/std table and per-run evidence |
| `simworld_get_metrics` | `run_id` | Stored metrics for one run |
| `simworld_explain_failure` | `run_id` | Failures, invalid actions, late deliveries, event timeline |
| `simworld_compare_runs` | `run_ids` (2–4) | Side-by-side metric comparison |

## Verification

```bash
python scripts/mcp_smoke.py
```

The smoke test performs the MCP handshake, lists tools, starts a real run, explains its failure,
compares two runs, and executes a 2×2 experiment. It fails loudly if the API is unreachable.

## Notes

- Errors are returned as tool results with `isError: true` and a concrete message, so an agent can
  report the blocker instead of guessing.
- The bridge waits for runs to finish rather than returning a partial result.
- Alan registration guidance and the verified integration status are in
  [../docs/ALAN_INTEGRATION.md](../docs/ALAN_INTEGRATION.md).