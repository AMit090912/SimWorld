# Deployment

## Local production run (verified)

```bash
cd frontend && npm install && npm run build
cd ../backend
python -m uvicorn simworld.api.app:app --host 0.0.0.0 --port 8000
```

FastAPI serves `frontend/dist` and the SPA routes from the same origin, so no CORS configuration and
no separate web server are needed. Verified locally at `http://127.0.0.1:8000` with the API at
`/api/*`, the OpenAPI UI at `/api/docs`.

## Docker (verified)

```bash
docker build -t simworld .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" simworld
```

or

```bash
docker compose up --build
```

The image builds the UI in a Node stage, installs the Python dependencies, runs as a non-root user, and
exposes a health check against `/api/health`. Verified locally: the container served the SPA, reported
`environment: production`, and completed a traffic run with score 81.17 and throughput 0.9717.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SIMWORLD_ENV` | `development` | `production` disables loopback agent targets |
| `SIMWORLD_DB_PATH` | `backend/data/simworld.db` | SQLite file location |
| `SIMWORLD_STATIC_DIR` | `frontend/dist` | Built UI to serve; ignored when missing |
| `SIMWORLD_CORS_ORIGINS` | `http://localhost:5173,...` | Allowed origins for a separate dev UI |
| `SIMWORLD_AGENT_ALLOW_LOOPBACK` | `true` in dev, `false` in prod | Allow `127.0.0.1` agent endpoints |
| `SIMWORLD_MAX_AGENT_TIMEOUT_MS` | `10000` | Upper bound for agent timeouts |
| `SIMWORLD_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible model endpoint |
| `SIMWORLD_LLM_MODEL` | `qwen2.5:1.5b-instruct` | Model id |
| `SIMWORLD_LLM_PROVIDER` | `openai_compatible` | Adapter dialect |
| `SIMWORLD_LLM_TIMEOUT_S` | `20` | Model request timeout |
| `SIMWORLD_LLM_API_KEY_ENV` | `OPENAI_API_KEY` | Name of the variable holding the key |
| `SIMWORLD_API_URL` | `http://127.0.0.1:8000` | Used by the MCP bridge |
| `MCP_RUN_TIMEOUT_S` | `900` | How long an MCP tool waits for a run |

See `.env.example`. The backend reads the process environment; it does not load `.env` itself.

## Production checklist

- [ ] `SIMWORLD_ENV=production`
- [ ] `SIMWORLD_AGENT_ALLOW_LOOPBACK=false` (public agents must not reach your internal network)
- [ ] `SIMWORLD_DB_PATH` on a persistent volume
- [ ] Reverse proxy with TLS; the UI and API share the origin, so no CORS changes are needed
- [ ] API key provided through the environment only, never a file in the image
- [ ] Health check on `/api/health`

## Scaling notes

The current design runs simulations in-process threads and stores evidence in SQLite. That is a good
fit for a single process. To scale out:

1. Move storage to PostgreSQL (the `store.py` surface is small and JSON-oriented).
2. Move run execution to a queue with worker processes.
3. Keep the engine stateless per run: a run is fully described by its config, seed, and recorded steps,
   so it can resume on another worker.

The API already returns `409`-free semantics for concurrency, and each run has its own re-entrant
lock, but the autoplay thread lives in the process that created the run.

## Not performed in this environment

No public hosting was performed: this environment has no hosting credential, no public domain, and no
GitHub credential. The local production run and the Docker build were verified instead. To publish:

1. Push the repository to a public GitHub repository.
2. Deploy the image to any container host and set the environment variables above.
3. Point the MCP bridge at the public API and register it in the Alan team (see
   [ALAN_INTEGRATION.md](ALAN_INTEGRATION.md)).