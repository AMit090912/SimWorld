import {
  ArrowRight,
  BookOpen,
  Boxes,
  Braces,
  CheckCircle2,
  Cpu,
  Database,
  GitBranch,
  KeyRound,
  Network,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { MetricDefinition } from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import { CopyButton, PageHeader, Spinner } from "../components/ui";

const QUICKSTART = `# 1. backend
cd backend
python -m pip install -r requirements-dev.txt
python -m uvicorn simworld.api.app:app --reload --port 8000

# 2. frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173

# production: build once, then FastAPI serves the SPA
cd frontend && npm run build
cd ../backend && python -m uvicorn simworld.api.app:app --port 8000`;

const AGENT_EXAMPLE = `# examples/external_agent.py — a working external agent
python examples/external_agent.py --port 9100

# then point SimWorld at http://127.0.0.1:9100/agent
# or test it from the Agents screen`;

const CURL = `curl -s http://127.0.0.1:8000/api/scenarios | head

curl -s -X POST http://127.0.0.1:8000/api/runs \\
  -H 'Content-Type: application/json' \\
  -d '{
    "scenario_id": "city-logistics/standard",
    "seed": 7,
    "agent": {"type": "builtin", "id": "city-baseline"}
  }'`;

const TESTS = `cd backend
python -m pytest -q
# engine rules, agent adapters, evaluation math, replay, API`;

const FLOW = `observation ──► agent ──► candidate action
      ▲                              │
      │                       schema validation
      │                              │
      │                       engine rules
      │                              │
      └──── new world state ◄── apply + events`;

const PROTOCOL_REQUEST = `{
  "protocol": "simworld.agent.v1",
  "run_id": "a1b2c3d4e5f6",
  "step": 14,
  "deadline_ms": 2500,
  "observation": { "...": "environment-specific state" },
  "legal_actions": [
    { "type": "move", "target": "3,2" },
    { "type": "pickup", "package_ids": ["PKG-01"] },
    { "type": "wait" }
  ]
}`;

const PROTOCOL_ACTION = `{ "type": "move", "target": "3,2" }
{ "type": "pickup", "package_ids": ["PKG-01", "PKG-02"] }
{ "type": "deliver", "package_id": "PKG-01" }
{ "type": "refuel", "amount": 5 }
{ "type": "wait" }
{ "type": "set_phase", "intersection": "1,1", "phase": "EW" }`;

const ENV = `SIMWORLD_ENV=development
SIMWORLD_DB_PATH=./data/simworld.db

# external agents: allow loopback during local development only
SIMWORLD_AGENT_ALLOW_LOOPBACK=true
SIMWORLD_MAX_AGENT_TIMEOUT_MS=10000

# OpenAI-compatible model (Ollama, vLLM, OpenRouter, OpenAI, ...)
SIMWORLD_LLM_BASE_URL=http://127.0.0.1:11434/v1
SIMWORLD_LLM_MODEL=qwen2.5:1.5b-instruct
SIMWORLD_LLM_API_KEY_ENV=OPENAI_API_KEY`;

const ARCHITECTURE = [
  { title: "React workspace", detail: "Map, controls, replay, compare", icon: Boxes },
  { title: "FastAPI service", detail: "Lifecycle, persistence, experiments", icon: Network },
  { title: "Deterministic engine", detail: "State · rules · events · scores", icon: Cpu },
  { title: "SQLite evidence", detail: "Runs, steps, actions, hashes", icon: Database },
];

export default function Docs() {
  const { data: metricData, loading } = useApiData(() => api.metrics(), []);

  return (
    <div>
      <PageHeader
        eyebrow="Documentation"
        title="SimWorld in ten minutes"
        description="A deterministic simulation and evaluation harness for agents. This page documents the run model, the external-agent contract, metric definitions, security boundaries, and the honest limitations."
      />

      <div className="grid gap-5 lg:grid-cols-[190px_minmax(0,1fr)]">
        <aside className="hidden lg:block">
          <div className="sticky top-20 space-y-1 text-[11px]">
            {[
              ["overview", "Overview"],
              ["start", "Quickstart"],
              ["loop", "Simulation loop"],
              ["protocol", "Agent protocol"],
              ["metrics", "Metrics"],
              ["repro", "Reproducibility"],
              ["security", "Security"],
              ["alan", "Alan integration"],
              ["limits", "Limitations"],
            ].map(([id, label]) => (
              <a key={id} href={`#${id}`} className="block rounded px-2 py-1.5 text-fog transition hover:bg-white/[0.03] hover:text-slate-200">
                {label}
              </a>
            ))}
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          <section id="overview" className="panel p-4">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-mint" />
              <h2 className="text-sm font-semibold text-white">What this is</h2>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-fog">
              SimWorld is a real simulation runtime for agents. The engine owns the world; the agent only proposes
              actions. Every tick is recorded with its resulting state, so scores and replays are evidence rather than
              narration. Two environments ship today: <strong className="text-slate-300">city logistics</strong> and{" "}
              <strong className="text-slate-300">traffic signal control</strong>.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {ARCHITECTURE.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="rounded border border-line/60 bg-ink-900/50 p-2.5">
                    <Icon className="h-4 w-4 text-mint" />
                    <div className="mt-1.5 text-[11px] font-medium text-slate-200">{item.title}</div>
                    <div className="text-[9px] leading-relaxed text-slate-500">{item.detail}</div>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Link to="/" className="btn-primary !py-1.5 !text-[10px]">Open workspace <ArrowRight className="h-3 w-3" /></Link>
              <Link to="/agents" className="btn-ghost !py-1.5 !text-[10px]">Connect an agent</Link>
              <Link to="/scenarios" className="btn-ghost !py-1.5 !text-[10px]">Browse scenarios</Link>
            </div>
          </section>

          <section id="start" className="panel p-4">
            <SectionTitle icon={<Terminal className="h-4 w-4" />} title="Run it locally" action={<CopyButton text={QUICKSTART} />} />
            <CodeBlock code={QUICKSTART} />
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-fog">
              <span className="chip">Python 3.10+</span>
              <span className="chip">Node 20+</span>
              <span className="chip">SQLite</span>
              <span className="chip">no cloud credentials required for built-ins</span>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              The backend creates its SQLite file automatically. In production, build the frontend first; FastAPI serves
              <span className="font-mono text-slate-400"> frontend/dist</span> and the SPA routes from the same origin.
            </p>
          </section>

          <section id="loop" className="panel p-4">
            <SectionTitle icon={<GitBranch className="h-4 w-4" />} title="The simulation loop" />
            <pre className="mt-2 overflow-x-auto rounded border border-line/60 bg-ink-950/70 p-3 font-mono text-[9px] leading-relaxed text-mint/90">{FLOW}</pre>
            <div className="mt-3 grid gap-2 text-[10px] leading-relaxed text-fog sm:grid-cols-3">
              <div className="rounded border border-line/50 p-2">
                <div className="mb-1 font-semibold text-slate-300">1 · Observe</div>
                The agent receives a scenario-specific observation plus the actions the engine will accept right now.
              </div>
              <div className="rounded border border-line/50 p-2">
                <div className="mb-1 font-semibold text-slate-300">2 · Validate</div>
                Shape is checked first, then world rules: adjacency, road status, fuel, cargo, capacity, signal timing.
              </div>
              <div className="mb-0 rounded border border-line/50 p-2">
                <div className="mb-1 font-semibold text-slate-300">3 · Record</div>
                The tick, action, result, latency, resulting state, and hash are persisted before the next observation.
              </div>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              Invalid actions still consume a tick. That is deliberate: a planner that repeatedly proposes illegal moves
              loses time, and the metric shows it.
            </p>
          </section>

          <section id="protocol" className="panel p-4">
            <SectionTitle icon={<Braces className="h-4 w-4" />} title="External agent protocol" action={<span className="chip">simworld.agent.v1</span>} />
            <div className="mt-2 grid gap-3 lg:grid-cols-2">
              <div>
                <div className="label mb-1.5">SimWorld → agent</div>
                <CodeBlock code={PROTOCOL_REQUEST} compact />
              </div>
              <div>
                <div className="label mb-1.5">Action vocabulary</div>
                <CodeBlock code={PROTOCOL_ACTION} compact />
              </div>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-fog">
              Respond with <span className="font-mono text-slate-300">{`{"action": {...}, "reasoning": "..."}`}</span>. Reasoning is
              stored and shown in the replay; it never affects the score. Unknown action types or fields are rejected at the
              schema boundary.
            </p>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <div>
                <div className="label mb-1.5">Sample agent</div>
                <CodeBlock code={AGENT_EXAMPLE} compact />
              </div>
              <div>
                <div className="label mb-1.5">Drive it over HTTP</div>
                <CodeBlock code={CURL} compact />
              </div>
            </div>
            <div className="mt-3 rounded border border-line/60 bg-ink-900/40 p-2.5 text-[10px] leading-relaxed text-fog">
              <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-300"><ShieldCheck className="h-3 w-3 text-mint" /> Failure policy</div>
              Timeout, non-JSON, a missing action, or an oversized response counts as an agent error. SimWorld applies one
              deterministic fallback action, logs the error, and aborts the run after three consecutive failures. Malformed
              actions never mutate the world.
            </div>
          </section>

          <section id="metrics" className="panel p-4">
            <SectionTitle icon={<Cpu className="h-4 w-4" />} title="Metrics and scoring" action={<span className="text-[9px] text-slate-600">definitions served by /api/metrics</span>} />
            {loading ? <Spinner label="Loading metric definitions" /> : null}
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              {(metricData?.metrics ?? []).map((metric: MetricDefinition) => (
                <div key={metric.key} className="rounded border border-line/50 bg-ink-900/40 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-slate-200">{metric.label}</span>
                    <span className="chip !text-[9px]">{metric.unit}</span>
                  </div>
                  <p className="mt-1 text-[9px] leading-relaxed text-fog">{metric.description}</p>
                  <div className="mt-1 flex items-center gap-2 text-[8px] uppercase tracking-[0.1em] text-slate-600">
                    <span>{metric.direction} is better</span>
                    <span>{metric.weight}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              The composite score never hides failures: the UI always shows component metrics and the failure list next to
              it. Scores are computed from recorded transitions only. An agent's own claim is never scored.
            </p>
          </section>

          <section id="repro" className="panel p-4">
            <SectionTitle icon={<CheckCircle2 className="h-4 w-4" />} title="Reproducibility" />
            <div className="mt-2 grid gap-2 text-[10px] leading-relaxed text-fog md:grid-cols-2">
              <div className="rounded border border-line/50 p-2.5">
                <div className="mb-1 font-semibold text-slate-300">Seeded initial conditions</div>
                Scenario layout, package-to-destination assignment, deadlines, station stock, and the event schedule are
                generated once from the seed and stored in the run configuration.
              </div>
              <div className="rounded border border-line/50 p-2.5">
                <div className="mb-1 font-semibold text-slate-300">Pure transitions</div>
                The engine performs no random draws while stepping. Given the same config and action sequence, the state
                hash is identical — covered by engine and API tests.
              </div>
              <div className="rounded border border-line/50 p-2.5">
                <div className="mb-1 font-semibold text-slate-300">Exact replay</div>
                Every step stores its action, agent decision, result, and resulting state. Replay reads those recorded
                transitions rather than re-running a separate animation.
              </div>
              <div className="rounded border border-line/50 p-2.5">
                <div className="mb-1 font-semibold text-slate-300">Same-seed comparisons</div>
                Experiments pair every seed with every selected agent. Comparing different seeds is allowed but labelled,
                because it is not an equivalent-condition comparison.
              </div>
            </div>
            <div className="mt-2">
              <div className="label mb-1.5">Test suite</div>
              <CodeBlock code={TESTS} compact />
            </div>
          </section>

          <section id="security" className="panel p-4">
            <SectionTitle icon={<ShieldCheck className="h-4 w-4" />} title="Security boundaries" />
            <div className="mt-2 grid gap-2 text-[10px] leading-relaxed text-fog md:grid-cols-2">
              {[
                ["Untrusted agents", "No direct database or world access. Only observations out, one validated action in."],
                ["SSRF screening", "http(s) only, no credentials in URLs, no redirects, loopback disabled outside dev, private/link-local/metadata IPs blocked."],
                ["Limits", "Hard request timeout ≤ 10 s, 64 KiB agent response cap, 256 KiB API body cap."],
                ["No code execution", "Agent output is parsed as data. SimWorld never shells out to an agent-provided command."],
                ["Secrets", "Credentials come from environment variables and are never stored in runs or returned by the API."],
                ["State integrity", "Invalid or failed actions cannot mutate the world; the fallback policy is recorded per step."],
              ].map(([title, detail]) => (
                <div key={title} className="rounded border border-line/50 p-2.5">
                  <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-300">
                    <KeyRound className="h-3 w-3 text-mint" /> {title}
                  </div>
                  {detail}
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
              Simulated success is not evidence that an agent is safe in the real world. SimWorld measures behaviour inside
              a specific, deliberately simplified model.
            </p>
          </section>

          <section id="alan" className="panel p-4">
            <SectionTitle icon={<Workflow className="h-4 w-4" />} title="Alan integration" />
            <p className="mt-2 text-[11px] leading-relaxed text-fog">
              SimWorld ships an <strong className="text-slate-300">MCP server</strong> that exposes the evaluation
              workflow as tools an Alan agent can call: list scenarios, launch a run, run a multi-seed experiment, fetch
              metrics, and explain a failure from stored evidence. The same operations are available over the HTTP API.
            </p>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div className="rounded border border-line/50 bg-ink-900/40 p-2.5 text-[10px] leading-relaxed text-fog">
                <div className="mb-1 font-semibold text-slate-300">MCP tools</div>
                <ul className="space-y-0.5 font-mono text-[9px] text-slate-400">
                  <li>simworld_list_scenarios</li>
                  <li>simworld_start_run</li>
                  <li>simworld_run_experiment</li>
                  <li>simworld_get_metrics</li>
                  <li>simworld_explain_failure</li>
                </ul>
              </div>
              <div className="rounded border border-line/50 bg-ink-900/40 p-2.5 text-[10px] leading-relaxed text-fog">
                <div className="mb-1 font-semibold text-slate-300">What stays honest</div>
                Model output is only a proposed action. The engine validates and records it. The integration is verified at
                the protocol level in this repository; connecting it to a cloud Alan team requires a publicly reachable
                MCP URL. See <span className="font-mono text-slate-400">docs/ALAN_INTEGRATION.md</span>.
              </div>
            </div>
            <div className="mt-2">
              <div className="label mb-1.5">Environment</div>
              <CodeBlock code={ENV} compact />
            </div>
          </section>

          <section id="limits" className="panel p-4">
            <SectionTitle icon={<AlertTriangleIcon />} title="Known limitations" />
            <ul className="mt-2 space-y-1.5 text-[10px] leading-relaxed text-fog">
              {[
                "Logistics is single-vehicle. The scenario abstraction supports multiple entities, but cooperative multi-agent logistics is not implemented.",
                "External agents run on the same host by default in development; loopback allowlisting must be disabled for untrusted public deployments.",
                "SQLite is intentional for a single-process deployment. Multi-worker deployments need a shared database and a run queue.",
                "Replay stores full per-step state snapshots, which favours exactness over storage size. Long runs are bounded to 400 steps.",
                "LLM agents are only as good as the configured endpoint. If it is unreachable, fallbacks are recorded and counted — never hidden.",
                "Scores are environment-specific and not comparable across different scenarios.",
              ].map((limitation) => (
                <li key={limitation} className="flex items-start gap-1.5">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber" />
                  {limitation}
                </li>
              ))}
            </ul>
          </section>

          <div className="flex items-center justify-between rounded-lg border border-line/70 bg-ink-900/40 px-4 py-3 text-[10px] text-fog">
            <span>MIT licensed · open source · built for reproducible agent evaluation</span>
            <Link to="/" className="inline-flex items-center gap-1 text-mint hover:underline">
              Workspace <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="text-mint">{icon}</span>
        <h2 className="text-sm font-semibold text-white">{title}</h2>
      </div>
      {action}
    </div>
  );
}

function CodeBlock({ code, compact = false }: { code: string; compact?: boolean }) {
  return (
    <div className="relative">
      <pre className={`overflow-x-auto rounded border border-line/60 bg-ink-950/70 p-2.5 font-mono ${compact ? "text-[9px]" : "text-[10px]"} leading-relaxed text-slate-400`}>
        {code}
      </pre>
      <div className="absolute right-1.5 top-1.5 opacity-70">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function AlertTriangleIcon() {
  return <span className="text-amber">⚠</span>;
}