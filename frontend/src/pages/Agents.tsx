import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Cloud,
  Cpu,
  Globe,
  Loader2,
  PlayCircle,
  ServerCog,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import type { AgentTestResult } from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import { CopyButton, ErrorBanner, Field, PageHeader, Panel, Spinner } from "../components/ui";

const REQUEST_SAMPLE = `POST /agent
Content-Type: application/json

{
  "protocol": "simworld.agent.v1",
  "run_id": "7f3a1c9d2e40",
  "step": 12,
  "deadline_ms": 2500,
  "observation": {
    "kind": "city_logistics",
    "vehicle": { "node": "3,2", "fuel_l": 4.8, "cargo": ["PKG-01"] },
    "packages": [ { "id": "PKG-01", "dest": "6,1", "deadline_min": 64 } ],
    "closed_edges": ["2,3|3,3"],
    "legal_actions": [ { "type": "move", "target": "3,3" } ]
  },
  "legal_actions": [ { "type": "move", "target": "3,3" } ]
}`;

const RESPONSE_SAMPLE = `HTTP/1.1 200 OK
Content-Type: application/json

{
  "action": { "type": "move", "target": "3,3" },
  "reasoning": "Closure forces a northern detour."
}`;

function BuiltinCard({ agent }: { agent: import("../lib/types").BuiltinAgent }) {
  return (
    <div className="panel-flat p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-pine/20 bg-pine/[0.07]">
            <Cpu className="h-3.5 w-3.5 text-pine" />
          </div>
          <div>
            <div className="text-xs font-semibold text-ink-800">{agent.label}</div>
            <div className="font-mono text-[9px] text-ink-400">{agent.id}</div>
          </div>
        </div>
        <span className="chip !text-[9px]">{agent.environments.includes("city_logistics") ? "city" : "traffic"}</span>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-ink-500">{agent.description}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {agent.traits.map((trait) => (
          <span key={trait} className="rounded border border-line/70 bg-paper/50 px-1.5 py-0.5 text-[9px] text-ink-500">
            {trait}
          </span>
        ))}
      </div>
    </div>
  );
}

function ResultView({ result }: { result: AgentTestResult }) {
  if (!result.ok) {
    return (
      <div className="space-y-2 rounded-md border border-brick/30 bg-brick/[0.05] p-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-brick">
          <XCircle className="h-3.5 w-3.5" /> Connection test failed
        </div>
        <div className="font-mono text-[9px] text-brick/80">{result.code}</div>
        <p className="text-[10px] leading-relaxed text-ink-600">{result.error}</p>
        <div className="font-mono text-[9px] text-ink-400">{result.latency_ms.toFixed(0)} ms</div>
      </div>
    );
  }
  return (
    <div className="space-y-2 rounded-md border border-pine/25 bg-pine/[0.04] p-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-pine">
          <CheckCircle2 className="h-3.5 w-3.5" /> Endpoint responded with a valid action
        </div>
        <span className="font-mono text-[9px] text-ink-500">{result.latency_ms.toFixed(0)} ms</span>
      </div>
      <div className="rounded border border-line/60 bg-paper/70 px-2 py-1.5 font-mono text-[10px] text-ink-700">
        {JSON.stringify(result.action)}
      </div>
      <div className="flex flex-wrap gap-1">
        <span className={result.engine_accepted ? "chip-mint" : "chip-coral"}>
          {result.engine_accepted ? "engine accepted" : "engine rejected"}
        </span>
        <span className={result.action_was_offered ? "chip" : "chip-amber"}>
          {result.action_was_offered ? "was offered" : "not in offered list"}
        </span>
        {result.fallback_used ? <span className="chip-amber">fallback used</span> : null}
      </div>
      {result.reasoning ? <p className="text-[10px] leading-relaxed text-ink-500">{result.reasoning}</p> : null}
      {result.engine_result ? <p className="text-[9px] text-ink-500">{result.engine_result}</p> : null}
      {result.error ? (
        <div className="flex items-start gap-1.5 text-[9px] text-ochre">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {result.error}
        </div>
      ) : null}
    </div>
  );
}

export default function Agents() {
  const { data: catalogue, error, loading, reload } = useApiData(() => api.agents(), []);
  const { data: llm, loading: llmLoading } = useApiData(() => api.llmStatus(), []);
  const [scenarioId, setScenarioId] = useState("city-logistics/standard");
  const [url, setUrl] = useState("http://127.0.0.1:9100/agent");
  const [timeoutMs, setTimeoutMs] = useState(2500);
  const [busy, setBusy] = useState<"external" | "llm" | null>(null);
  const [externalResult, setExternalResult] = useState<AgentTestResult | null>(null);
  const [llmResult, setLlmResult] = useState<AgentTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  async function runTest(kind: "external" | "llm") {
    setBusy(kind);
    setTestError(null);
    try {
      const result = await api.testAgent(
        kind === "external"
          ? { type: "external", url: url.trim(), timeout_ms: timeoutMs }
          : { type: "llm" },
        scenarioId,
      );
      if (kind === "external") setExternalResult(result);
      else setLlmResult(result);
    } catch (err) {
      setTestError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Agent integration"
        title="Bring your agent. The engine stays the referee."
        description="SimWorld sends an observation, receives one candidate action, and validates it against the world's rules. External endpoints are untrusted: timeouts, SSRF screening, and response limits are always on."
        actions={
          <a href="#protocol" className="btn-ghost">
            HTTP contract
          </a>
        }
      />

      {error ? <ErrorBanner message={error} onRetry={reload} /> : null}
      {testError ? <ErrorBanner message={testError} onRetry={() => setTestError(null)} /> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_390px]">
        <div className="space-y-4">
          <Panel title="Built-in strategies" action={<span className="text-[9px] text-ink-400">deterministic · no credentials</span>}>
            {loading ? <Spinner label="Loading agents" /> : null}
            <div className="grid gap-2 sm:grid-cols-2">
              {catalogue?.builtin.map((agent) => <BuiltinCard key={agent.id} agent={agent} />)}
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-ink-500">
              Built-ins can complete their environments without a model. They are useful baselines and fallbacks,
              not proof that an external agent will behave the same way.
            </p>
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-1.5">
                <Globe className="h-3 w-3 text-pine" /> External HTTP agent
              </span>
            }
            action={<span className="chip !text-[9px]">simworld.agent.v1</span>}
          >
            <div className="grid gap-3 sm:grid-cols-[1fr_150px]">
              <Field label="Endpoint URL" hint="POST only. Redirects are not followed; private and link-local hosts are blocked outside explicit dev allowlisting.">
                <input className="input font-mono !text-[10px]" value={url} onChange={(event) => setUrl(event.target.value)} />
              </Field>
              <Field label="Timeout (ms)">
                <input
                  type="number"
                  min={200}
                  max={10000}
                  step={100}
                  className="input font-mono"
                  value={timeoutMs}
                  onChange={(event) => setTimeoutMs(Math.max(200, Number(event.target.value) || 200))}
                />
              </Field>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select className="select !w-auto !py-1.5 !text-[10px]" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
                <option value="city-logistics/standard">City · Riverside Standard</option>
                <option value="traffic-control/steady">Traffic · Steady Commuter Flow</option>
              </select>
              <button className="btn-primary" onClick={() => runTest("external")} disabled={busy !== null}>
                {busy === "external" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
                Test connection
              </button>
              <span className="text-[9px] text-ink-400">sends one real observation from seed 7</span>
            </div>
            {externalResult ? (
              <div className="mt-3">
                <ResultView result={externalResult} />
              </div>
            ) : null}
            <div className="mt-3 rounded border border-line/60 bg-paper/50 p-2.5 text-[10px] leading-relaxed text-ink-500">
              Start the sample agent locally:
              <code className="mt-1 block font-mono text-[10px] text-pine">python examples/external_agent.py --port 9100</code>
              It uses the same observation/action schema as the panel on the right.
            </div>
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-1.5">
                <Sparkles className="h-3 w-3 text-ochre" /> Model agent
              </span>
            }
            action={
              llm?.probe.available ? <span className="chip-mint">endpoint reachable</span> : <span className="chip-amber">not reachable</span>
            }
          >
            {llmLoading ? (
              <Spinner label="Probing model endpoint" />
            ) : (
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-line/60 bg-paper/50 p-2">
                    <div className="label mb-1">Model</div>
                    <div className="font-mono text-[11px] text-ink-700">{llm?.model}</div>
                  </div>
                  <div className="rounded border border-line/60 bg-paper/50 p-2">
                    <div className="label mb-1">Base URL</div>
                    <div className="truncate font-mono text-[10px] text-ink-600">{llm?.base_url}</div>
                  </div>
                </div>
                <div className="space-y-1 text-[10px] text-ink-500">
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck className="h-3 w-3 text-ink-500" />
                    API key configured: <span className={llm?.api_key_configured ? "text-pine" : "text-ochre"}>{llm?.api_key_configured ? "yes" : "no"}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ServerCog className="h-3 w-3 text-ink-500" />
                    Probe: <span className={llm?.probe.available ? "text-pine" : "text-ochre"}>{llm?.probe.available ? "available" : llm?.probe.error}</span>
                  </div>
                  {llm?.probe.model_listed === false ? (
                    <div className="text-ochre">The model name is not in the endpoint's /models list.</div>
                  ) : null}
                </div>
                {!llm?.probe.available ? (
                  <div className="flex items-start gap-2 rounded border border-ochre/25 bg-ochre/[0.05] p-2 text-[10px] leading-relaxed text-ochre/90">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    No model is answering. Runs configured with a model will record a fallback and mark it in the metrics —
                    they will not pretend the model decided.
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <button className="btn-ghost" onClick={() => runTest("llm")} disabled={busy !== null}>
                    {busy === "llm" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
                    Test model decision
                  </button>
                  <span className="text-[9px] text-ink-400">OpenAI-compatible · config via env</span>
                </div>
                {llmResult ? <ResultView result={llmResult} /> : null}
                <div className="rounded border border-line/60 bg-paper/50 p-2.5">
                  <div className="label mb-1.5">Server environment</div>
                  <div className="space-y-1 font-mono text-[9px] text-ink-500">
                    <div>SIMWORLD_LLM_BASE_URL</div>
                    <div>SIMWORLD_LLM_MODEL</div>
                    <div>SIMWORLD_LLM_API_KEY_ENV</div>
                  </div>
                </div>
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-4" id="protocol">
          <Panel
            title="Request contract"
            action={<CopyButton text={REQUEST_SAMPLE} />}
            bodyClassName="p-0"
          >
            <pre className="max-h-[360px] overflow-auto p-3 font-mono text-[9px] leading-relaxed text-ink-600">{REQUEST_SAMPLE}</pre>
          </Panel>
          <Panel title="Expected response" action={<CopyButton text={RESPONSE_SAMPLE} />} bodyClassName="p-0">
            <pre className="overflow-auto p-3 font-mono text-[9px] leading-relaxed text-ink-600">{RESPONSE_SAMPLE}</pre>
          </Panel>
          <Panel title="Failure policy">
            <div className="space-y-2 text-[10px] leading-relaxed text-ink-500">
              <div className="flex items-start gap-1.5">
                <Cloud className="mt-0.5 h-3.5 w-3.5 shrink-0 text-steel" />
                Timeout, crash, or malformed output → one safe deterministic fallback action is applied and the error is recorded.
              </div>
              <div className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ochre" />
                Three consecutive agent failures terminate the run as <span className="font-mono text-ochre">agent_unavailable</span>.
              </div>
              <div className="flex items-start gap-1.5">
                <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-pine" />
                Structurally valid but illegal actions reach the engine, are rejected, and count against the agent.
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}