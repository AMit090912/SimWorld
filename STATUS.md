# Project status

Updated: 2026-10-26

## Completed

- Deterministic city-logistics engine: grid roads, closures, fuel, capacity, deadlines, refuelling,
  scheduled and live disruptions, terminal states, state hashes.
- Deterministic traffic-control engine: nine signals, queues, minimum-green enforcement, incidents,
  throughput and waiting-time metrics.
- Six scenarios with seeded initial conditions and validated variation axes.
- Five deterministic built-in agents and a failure baseline.
- External HTTP agent adapter with schema validation, timeouts, SSRF screening, response caps, latency
  measurement, connection testing, and safe fallback.
- OpenAI-compatible LLM agent with a compact decision view, tolerant action normalisation, strict
  engine validation, and honest fallback reporting. Verified with Ollama.
- FastAPI service: run lifecycle, autoplay, pause, reset, live disruption injection, replay,
  experiments, comparison, error handling, request limits.
- SQLite evidence store: runs, per-step snapshots, decisions, metrics, experiments.
- Objective evaluation with component metrics, failure summaries, recovery, reliability, aggregation.
- Polished React/TypeScript UI: workspace, scenario browser, agent lab, run history, replay, comparison,
  experiment launcher, documentation.
- External-agent example that completes a real run (included in tests).
- MCP server with six tools and a protocol smoke test.
- Alan team Skill `simworld-evaluation` (validated, enabled) and weekly benchmark workflow (draft,
  disabled to avoid unsolicited sessions).
- Documentation: README, architecture, API, metrics, Alan integration, deployment, demo.
- Dockerfile, Compose file, dev/start scripts. Docker image built and verified (SPA + API + a real run).

## Test status

`python -m pytest backend -q` → **86 passed**.

Coverage includes engine transitions, fuel, deadlines, closures, scheduled events, fog, determinism,
traffic minimum green and incidents, external agent validation/timeouts/SSRF/oversized responses, the
example agent over HTTP, LLM schema tolerance and fallback, metric math, replay reconstruction, run
lifecycle, experiments, MCP tools, and HTTP API behaviours.

## Integration status

| Integration | Status | Evidence |
| --- | --- | --- |
| Built-in agents | Verified | Tests and live UI runs |
| External HTTP agent | Verified | Example server + engine-complete run test |
| Ollama model agent | Verified | `qwen2.5:1.5b-instruct`, real actions, no fallback, 2.5–7.5 s/decision |
| MCP server | Verified locally | `scripts/mcp_smoke.py` real runs and experiment |
| Alan Skill | Created + validated | Alan API create_skill validation |
| Alan workflow | Created as draft | Alan API create_workflow, disabled |
| Docker image | Verified locally | Built image served the SPA/API and completed a run (score 81.17) |
| Public deployment | Not performed | No hosting credential or public URL |
| GitHub publication | Not performed | No GitHub credential or `gh` CLI in this environment |
| Cloud Alan MCP registration | Not performed | Requires public URL and team MCP configuration |

## Known issues

- `notifications/initialized` is ignored as intended; no server-initiated notifications are emitted.
- Local model runs are slow on CPU (seconds per decision) by nature, not a code defect. The supervisor design limits model calls to goal changes; router ticks are near-instant.
- The UI scenario preview fetches per card; with many scenarios this would need caching.
- Run deletion/archival is not exposed in the UI.
- The autoplay thread is in-process; do not run multiple Uvicorn workers against one SQLite file.

## Next steps

1. Deploy the Docker image to a public host and verify `/`, `/api/docs`, and a run over HTTPS.
2. Register the public MCP endpoint in the Alan team and execute the weekly workflow once.
3. Publish the repository, then add CI (pytest + `npm run build` + Docker build).
4. Add multi-vehicle logistics and a third environment (factory scheduling) behind the same interface.
5. Replace SQLite with PostgreSQL and move run execution to a queue for horizontal scaling.

## Evidence

- Screenshots: `docs/screenshots/`
- Benchmark report: `docs/benchmarks/latest.md`
- Test suite: `backend/tests/`
- MCP verification: `scripts/mcp_smoke.py`
- Demo flow: `docs/DEMO.md`