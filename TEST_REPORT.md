# SimWorld E2E Test Report

Date: 2026-10-27  
Repository: `C:\Users\khemc\OneDrive\Desktop\ALAN`

## Environment

- Windows, PowerShell 5.1
- Python 3.10, FastAPI/Uvicorn, SQLite
- Node 24, React 18, Vite 5
- Chrome via Playwright 1.64.1
- Ollama with `qwen2.5:1.5b-instruct` available for the live model check
- No secrets or API keys are included in this report. No paid model calls were made.

## Entry Points and Startup

- Backend entry point: `simworld.api.app:app`
- Production helper: `.\scripts\start.ps1`
- Development helper: `.\scripts\dev.ps1` (starts API and Vite in new terminals)
- Dev frontend: `npm run dev` in `frontend/`, proxying `/api` to port 8000
- Production frontend: `npm run build` in `frontend/`, then FastAPI serves `frontend/dist`

## Tests Added or Updated

- `backend/tests/test_determinism.py` — same-seed full-run reproducibility, seed differences, option metadata.
- `backend/tests/test_disruptions.py` — deadline change, fuel cut, traffic incident, traffic surge, live closure reroute, invalid disruption handling.
- `backend/tests/test_metrics_integration.py` — independent city metric reconciliation, terminal metadata, zero-package evaluation, traffic metrics and score.
- `backend/tests/test_api_validation.py` — malformed input, invalid IDs/agents, concurrency, duplicate start, reset/restart, pause/resume, and no stack-trace leakage.
- `backend/tests/test_api.py` — SPA path-traversal regression test.
- `backend/tests/conftest.py` — deterministic model test settings.
- `frontend/e2e/workflow.mjs` — browser workflow, screens, refresh, empty history, and failed-request recovery.
- `frontend/package.json` / `package-lock.json` — Playwright test dependency and `test:e2e` script.
- `frontend/src/index.css` — desktop readability scale; mobile layout unchanged.
- `frontend/src/components/maps/CityMap.tsx` — collapsible, non-overlapping side-rail map legend with minimize/expand control.
- `.gitignore` — E2E artifacts.

## Results

### Backend

```powershell
$env:PYTHONPATH="backend"; python -m pytest backend -p no:cacheprovider
```

Result: **109 passed, 0 failed, 0 skipped** (one third-party `PendingDeprecationWarning` from Starlette).

Overall counts: **109 backend tests passed**, **1 browser workflow passed**, **0 failed**, **0 skipped**. Blocked areas are listed under Remaining Issues (cloud Alan registration, Docker runtime, and real model availability when Ollama is not running).

Coverage includes:

- City and traffic engine rules
- Action schema validation
- Agent adapters, timeouts, malformed responses, SSRF blocking, fallback behavior
- Evaluation math and aggregation
- API lifecycle, replay, persistence, experiments, and error handling
- Replay reconstruction, including live disruptions
- Full-run determinism with the same seed and agent
- Different-seed divergence
- All implemented live disruption types
- Independent metric reconciliation
- Concurrent runs, repeated starts, pause/resume/reset/restart
- SPA path containment

### Frontend

```powershell
cd frontend
npm run typecheck
npm run build
```

Result: both passed.

### Browser E2E

Command used against a fresh database:

```powershell
cd backend
$env:SIMWORLD_ENV="production"
$env:SIMWORLD_DB_PATH="..\data\e2e-empty.db"
$env:SIMWORLD_STATIC_DIR="..\frontend\dist"
Remove-Item "..\data\e2e-empty.db*" -Force -ErrorAction SilentlyContinue
python -m uvicorn simworld.api.app:app --port 8002
```

```powershell
cd frontend
$env:BASE_URL="http://127.0.0.1:8002"
$env:E2E_EXPECT_EMPTY="1"
npm run test:e2e
```

Result: **1 browser workflow passed**.

Verified:

- Workspace, Scenarios, Agents, Runs, and Docs screens load
- Empty run history renders on a fresh database
- Launch button creates a real run through the browser
- Run reaches `finished`
- 7/7 packages delivered, 63 steps, score 80.26
- Replay and final evaluation render
- Page refresh preserves the completed run
- Zero console errors and zero failed requests on the normal path
- A failed `/api/scenarios` request shows the retry state and recovers after retry
- The map legend minimizes and restores via its own control, with the legend list hidden while collapsed
- The legend is a dedicated side rail beside the map; it no longer overlays map content

After adding the desktop readability scale and moving the legend into a non-overlapping map rail, the browser workflow was rerun successfully:
`45204b3eac98`, 63 steps, 7/7 delivered, score 80.26, 0 console errors, 0 failed requests.

### MCP and Alan

```powershell
$env:SIMWORLD_API_URL="http://127.0.0.1:8002"
python scripts/mcp_smoke.py
```

Result: passed.

- MCP handshake: `2024-11-05`
- Six tools listed
- Real run completed: score 80.3
- Failure explanation, run comparison, and 2×2 experiment passed (2.1 s)

Alan platform records were verified directly through the Alan API:

- Skill `simworld-evaluation`: enabled, version 1, no validation diagnostics
- Workflow `SimWorld weekly agent benchmark`: private, disabled, Monday 06:00 UTC, 30-minute timeout, one retry, local runtime `Amit`, zero runs
- Cloud MCP registration and scheduled workflow execution were **BLOCKED** by the absence of a public MCP endpoint/team registration and the intentionally disabled workflow.

### Open Model

Ollama was started locally and tested against its OpenAI-compatible API:

- `GET /v1/models` listed `qwen2.5:0.5b-instruct` and `qwen2.5:1.5b-instruct`
- `POST /v1/chat/completions` accepted the project request, including `response_format`
- A full model-driven run completed:
  - Run `8fa1c0d345b7`
  - 75 steps, 7/7 delivered, score 73.57
  - 10.065 L consumed, 0 invalid actions, 0 agent errors, 0 fallbacks
- A post-fix `/api/agents/test` call returned `ok: true`, `engine_accepted: true`, with a real pickup action.

Ollama was stopped after the audit. Model tests are **BLOCKED** when Ollama is not running; they are not mocked in the application.

## Failures Found and Fixed

### 1. Critical: SPA path traversal

Before the fix, a request such as:

```text
/..%2f..%2fREADME.md
```

could return repository files outside `frontend/dist`.

Fix: resolve the requested path and require it to remain under the static root in `backend/simworld/api/app.py`. Out-of-root paths now receive the SPA shell, not the target file.

Regression test: `backend/tests/test_api.py::test_spa_fallback_never_serves_files_outside_static_dir`.

### 2. External agent validation happened too late

`POST /api/runs` accepted an invalid external URL such as `file:///etc/passwd` and deferred failure until the first decision.

Fix: validate external endpoints when the agent is built in `backend/simworld/agents/factory.py`. Run creation now returns a clear 400 for invalid/blocked configuration.

The documented `/api/agents/test` contract is preserved: blocked/network failures still return HTTP 200 with `ok: false`, while invalid configuration returns 400.

### 3. Model status ignored injected settings

`/api/agents` and `/api/agents/llm/status` re-read environment variables instead of using the `RunService` settings. This could report a different endpoint than the one runs actually used.

Fix: `RunService._llm_config` is now the single source for the configured model endpoint in `backend/simworld/service.py`.

### 4. Tests depended on a developer’s local model

Starting Ollama caused `test_missing_model_credentials_are_reported_not_faked` to fail because the test settings pointed at the real local model endpoint.

Fix: test settings now use an intentionally unreachable endpoint in `backend/tests/conftest.py`. The test suite is deterministic with or without Ollama.

### 5. Desktop UI was too small to read comfortably

The design uses a dense 9–11px type scale. On large displays the labels, controls, map annotations, and navigation were difficult to read.

Fix: add a desktop-only readability scale in `frontend/src/index.css`: `1.2` at 1366px and wider, `1.12` at 1024–1365px, and no change on mobile. The layout remains unchanged, with no horizontal overflow at 1500px or 1783px. The browser workflow was rerun at the new scale and passed.

The map legend now has a minimize/expand button in `frontend/src/components/maps/CityMap.tsx`. The compact state becomes a narrow vertical rail with the compass and plus control. The expanded state occupies a reserved side rail inside the map card, so it does not cover the map sheet or map controls.

### Test-assumption corrections

These were not product defects:

- Wall-clock agent latency is nondeterministic by nature; determinism assertions compare state, actions, metrics, and score, not latency.
- Stored run options include scenario defaults plus the supplied overrides.
- The experiment API permits up to 10 seeds; the negative test now uses 11.
- A zero-package evaluation with zero remaining fuel correctly reports a low-fuel failure.

## Remaining Issues and Limits

- **No explicit stop endpoint**: pause, resume, reset, and restart are implemented and tested. A separate “stop and discard” operation is not implemented.
- **Experiment shutdown race**: an experiment thread can still be alive if the process closes immediately after creating an experiment. This was observed as a test-lifecycle warning when a valid experiment was abandoned; normal UI flows complete experiments. Graceful experiment cancellation is not implemented.
- **Corrupted database handling** was not tested. Invalid JSON, invalid IDs, unknown scenarios, and bad agent/disruption inputs were tested.
- **Vite favicon**: Vite development logs a 404 for `/favicon.ico`; production has no console error.
- **Vite IPv6 binding**: use `http://localhost:5173`; `127.0.0.1:5173` is not bound in this environment.
- **Docker runtime**: `docker compose config` passed, but the image was not built or run during this audit. That remains unverified.
- **Alan cloud**: cloud MCP registration and scheduled execution are not possible without a public endpoint and team registration. Local Skill/workflow records and the local MCP bridge were verified.
- **Frontend tests**: the repository originally had no frontend test framework; Playwright is now added for the main browser workflow. Compare/pause/closure click-through remains covered by API/MCP tests rather than a second browser script.
- **Desktop scaling**: at a 1001px-high viewport, the larger desktop UI scrolls vertically; the primary controls and map remain usable and there is no horizontal overflow. Mobile is unchanged.
- The working tree already contained uncommitted UI/theme changes before this audit. They were preserved; the changes listed above are test and backend fixes.

## Repeat Commands

```powershell
# Install
python -m pip install -r backend\requirements-dev.txt
cd frontend
npm install
npm run build
cd ..

# Backend suite
$env:PYTHONPATH="backend"
python -m pytest backend -p no:cacheprovider

# Frontend checks
cd frontend
npm run typecheck
npm run build

# Production application
cd ..
.\scripts\start.ps1
# Open http://127.0.0.1:8000
# If port 8000 is occupied: .\scripts\start.ps1 -Port 8002

# Browser E2E (API must be running; use a fresh DB for the empty-state check)
cd frontend
$env:BASE_URL="http://127.0.0.1:8000"
$env:E2E_EXPECT_EMPTY="1"   # omit if the database already has runs
npm run test:e2e
```

Manual development startup:

```powershell
# Terminal 1
cd backend
python -m uvicorn simworld.api.app:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
# Open http://localhost:5173
```

MCP smoke test:

```powershell
$env:SIMWORLD_API_URL="http://127.0.0.1:8000"
python scripts\mcp_smoke.py
```

Real model mode:

```powershell
ollama serve
ollama pull qwen2.5:1.5b-instruct
```

Do not expose API keys or local environment files in test output.
