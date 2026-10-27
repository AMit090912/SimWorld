import {
  ArrowRight,
  Bot,
  Boxes,
  ChevronRight,
  Cpu,
  ExternalLink as ExternalIcon,
  Fuel,
  Gauge,
  Globe,
  Play,
  RefreshCw,
  Sparkles,
  Target,
  Timer,
  Wifi,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { clock, duration, num } from "../lib/format";
import type {
  AgentSpec,
  BuiltinAgent,
  CityState,
  LastStep,
  LLMStatus,
  RunPayload,
  Scenario,
  SimState,
  TrafficState,
} from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import { EmptyState, ErrorBanner, Field, Panel, Spinner, Toast } from "../components/ui";
import {
  EventFeed,
  MetricsPanel,
  PackageList,
  RunControls,
  SimulationMap,
  StatusPill,
} from "../components/sim";

type AgentMode = "builtin" | "external" | "llm";

function agentSpec(mode: AgentMode, builtinId: string, url: string, model: string): AgentSpec {
  if (mode === "external") return { type: "external", url: url.trim(), timeout_ms: 2500 };
  if (mode === "llm") return { type: "llm", model: model.trim() || undefined, temperature: 0 };
  return { type: "builtin", id: builtinId };
}

export default function Workspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: scenarioData, error: scenarioError } = useApiData(() => api.scenarios(), []);
  const { data: agentData } = useApiData(() => api.agents(), []);
  const { data: llmStatus } = useApiData<LLMStatus>(() => api.llmStatus(), []);

  const scenarios = scenarioData?.scenarios ?? [];
  const builtins = agentData?.builtin ?? [];
  const initialId = searchParams.get("scenario") || "city-logistics/standard";
  const [scenarioId, setScenarioId] = useState(initialId);
  const scenario: Scenario | undefined = scenarios.find((item) => item.id === scenarioId) || scenarios[0];

  const [seed, setSeed] = useState(7);
  const [options, setOptions] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<AgentMode>("builtin");
  const [builtinId, setBuiltinId] = useState("city-baseline");
  const [externalUrl, setExternalUrl] = useState("http://127.0.0.1:9100/agent");
  const [llmModel, setLlmModel] = useState("");
  const [startImmediately, setStartImmediately] = useState(true);

  const [payload, setPayload] = useState<RunPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "mint" | "coral" | "amber" } | null>(null);
  const [speed, setSpeed] = useState(300);
  const [trail, setTrail] = useState<string[]>([]);
  const trailRun = useRef<string | null>(null);

  const kind = scenario?.kind ?? "city_logistics";
  const compatible = useMemo(
    () => builtins.filter((agent) => agent.environments.includes(kind)),
    [builtins, kind],
  );
  const preview = useApiData(
    () => (scenario ? api.preview(scenario.id, seed) : Promise.reject(new Error("No scenario"))),
    [scenario?.id, seed],
  );

  useEffect(() => {
    if (!scenario) return;
    setOptions({ ...scenario.default_options });
    if (!compatible.some((agent) => agent.id === builtinId)) {
      setBuiltinId(compatible[0]?.id ?? "city-baseline");
    }
    if (scenario.id !== searchParams.get("scenario")) {
      setSearchParams({ scenario: scenario.id }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.id, compatible.length]);

  useEffect(() => {
    if (payload && payload.run.id !== trailRun.current) {
      trailRun.current = payload.run.id;
      setTrail(payload.state.kind === "city_logistics" ? [payload.state.vehicle.node] : []);
    }
  }, [payload?.run.id]);

  useEffect(() => {
    const state = payload?.state;
    if (!state || state.kind !== "city_logistics") return;
    setTrail((previous) => {
      if (previous[previous.length - 1] === state.vehicle.node) return previous;
      return [...previous, state.vehicle.node].slice(-90);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload?.state.step, payload?.run.id]);

  useEffect(() => {
    if (!payload || payload.run.status !== "running") return;
    const runId = payload.run.id;
    const handle = window.setInterval(() => {
      api
        .getRun(runId)
        .then((next) => setPayload(next))
        .catch((err: Error) => setError(err.message));
    }, 420);
    return () => window.clearInterval(handle);
  }, [payload?.run.id, payload?.run.status]);

  useEffect(() => {
    if (!toast) return;
    const handle = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(handle);
  }, [toast]);

  const selectedBuiltin: BuiltinAgent | undefined = compatible.find((agent) => agent.id === builtinId);
  const spec = agentSpec(mode, builtinId, externalUrl, llmModel);
  const liveState = payload?.state ?? preview.data?.snapshot ?? null;
  const evaluation = payload?.evaluation ?? null;

  async function launch() {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createRun({
        scenario_id: scenario.id,
        seed,
        options,
        agent: spec,
      });
      setPayload(created);
      setTrail(created.state.kind === "city_logistics" ? [created.state.vehicle.node] : []);
      if (startImmediately) {
        const started = await api.startRun(created.run.id, speed);
        setPayload(started);
      }
      setToast({ message: `Run ${created.run.id} created.`, tone: "mint" });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function control(action: "start" | "pause" | "step" | "reset") {
    if (!payload) return;
    setBusy(true);
    setError(null);
    try {
      const runId = payload.run.id;
      const next =
        action === "start"
          ? await api.startRun(runId, speed)
          : action === "pause"
            ? await api.pauseRun(runId)
            : action === "step"
              ? await api.stepRun(runId)
              : await api.resetRun(runId);
      setPayload(next);
      if (action === "reset") {
        setTrail(next.state.kind === "city_logistics" ? [next.state.vehicle.node] : []);
        setToast({ message: "Run reset to its initial state.", tone: "amber" });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function disrupt(type: string) {
    if (!payload) return;
    setBusy(true);
    try {
      const next = await api.disrupt(payload.run.id, { type });
      setPayload(next);
      setToast({
        message: next.injected?.message || "Disruption injected.",
        tone: "amber",
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (scenarioError) {
    return <ErrorBanner message={scenarioError} />;
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[286px_minmax(0,1fr)_336px]">
        <div className="order-2 min-w-0 space-y-3 xl:order-1">
          <Panel title="Scenario">
            {!scenarioData ? (
              <Spinner label="Loading scenarios" />
            ) : (
              <div className="space-y-3">
                <Field label="Environment">
                  <select
                    className="select"
                    value={scenario?.id}
                    onChange={(event) => {
                      setScenarioId(event.target.value);
                      setPayload(null);
                      setTrail([]);
                    }}
                  >
                    {scenarios.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </Field>
                {scenario ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <span className="chip-sky">{scenario.kind === "city_logistics" ? "City logistics" : "Traffic control"}</span>
                      <span className="chip-amber">{scenario.difficulty}</span>
                    </div>
                    <p className="text-[11px] leading-relaxed text-fog">{scenario.tagline}</p>
                    <div className="flex flex-wrap gap-1">
                      <span className="chip">
                        <Timer className="h-2.5 w-2.5" /> {scenario.horizon_steps} ticks
                      </span>
                      <span className="chip">
                        <Target className="h-2.5 w-2.5" /> {scenario.objectives.length} objectives
                      </span>
                    </div>
                  </div>
                ) : null}

                <div className="divider" />
                <Field label="Seed" hint="Same scenario, seed, agent and actions reproduce the same run.">
                  <div className="flex gap-1.5">
                    <input
                      type="number"
                      min={0}
                      className="input font-mono"
                      value={seed}
                      onChange={(event) => setSeed(Math.max(0, Number(event.target.value) || 0))}
                    />
                    <button
                      className="btn-ghost px-2"
                      onClick={() => setSeed(Math.floor(Math.random() * 1_000_000))}
                      title="New random seed"
                      aria-label="New random seed"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </Field>

                {scenario ? (
                  <details className="group rounded-md border border-line/60 bg-ink-900/40 px-2.5 py-2">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
                      <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-fog">
                        Variations
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="chip !text-[9px]">{scenario.variations.length}</span>
                        <ChevronRight className="h-3 w-3 text-slate-500 transition group-open:rotate-90" />
                      </span>
                    </summary>
                    <div className="mt-2.5 space-y-2.5">
                      {scenario.variations.map((variation) => (
                        <Field key={variation.key} label={variation.label}>
                          <select
                            className="select"
                            value={options[variation.key] ?? variation.default}
                            onChange={(event) => setOptions((current) => ({ ...current, [variation.key]: event.target.value }))}
                          >
                            {variation.options.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </Field>
                      ))}
                    </div>
                  </details>
                ) : null}
              </div>
            )}
          </Panel>

          <Panel title="Agent">
            <div className="mb-2.5 grid grid-cols-3 gap-1 rounded-md border border-line bg-ink-950/60 p-0.5">
              {(
                [
                  { id: "builtin", label: "Built-in", icon: Cpu },
                  { id: "external", label: "HTTP", icon: Globe },
                  { id: "llm", label: "Model", icon: Sparkles },
                ] as const
              ).map((item) => {
                const Icon = item.icon;
                const active = mode === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setMode(item.id)}
                    className={`flex items-center justify-center gap-1 rounded px-1 py-1.5 text-[10px] font-medium transition ${
                      active ? "bg-ink-750 text-white shadow" : "text-fog hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-3 w-3" />
                    {item.label}
                  </button>
                );
              })}
            </div>

            {mode === "builtin" ? (
              <div className="space-y-2">
                <select className="select" value={builtinId} onChange={(event) => setBuiltinId(event.target.value)}>
                  {compatible.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.label}
                    </option>
                  ))}
                </select>
                {selectedBuiltin ? (
                  <div className="rounded-md border border-line/60 bg-ink-900/50 p-2">
                    <p className="text-[10px] leading-relaxed text-fog">{selectedBuiltin.description}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {selectedBuiltin.traits.map((trait) => (
                        <span key={trait} className="chip !text-[9px]">
                          {trait}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            {mode === "external" ? (
              <div className="space-y-2.5">
                <Field label="Endpoint URL" hint="POST receives an observation, returns one action. Loopback is allowed in development.">
                  <input
                    className="input font-mono !text-[10px]"
                    value={externalUrl}
                    onChange={(event) => setExternalUrl(event.target.value)}
                    placeholder="http://127.0.0.1:9100/agent"
                  />
                </Field>
                <div className="flex items-center gap-1.5 text-[9px] text-fog">
                  <Wifi className="h-3 w-3 text-mint" /> timeout 2.5s · SSRF screened · schema validated
                </div>
                <Link to="/agents" className="flex items-center gap-1 text-[10px] text-mint hover:underline">
                  Open connection test <ChevronRight className="h-3 w-3" />
                </Link>
              </div>
            ) : null}

            {mode === "llm" ? (
              <div className="space-y-2.5">
                <Field label="Model" hint="Any OpenAI-compatible endpoint. The engine still validates every action.">
                  <input
                    className="input font-mono !text-[10px]"
                    value={llmModel}
                    onChange={(event) => setLlmModel(event.target.value)}
                    placeholder={llmStatus?.model || "qwen2.5:1.5b-instruct"}
                  />
                </Field>
                <div className="rounded-md border border-line/60 bg-ink-900/50 p-2 text-[9px] leading-relaxed text-fog">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono">{llmStatus?.base_url || "not configured"}</span>
                    {llmStatus?.probe.available ? (
                      <span className="chip-mint shrink-0 !text-[9px]">reachable</span>
                    ) : (
                      <span className="chip-amber shrink-0 !text-[9px]">offline</span>
                    )}
                  </div>
                  {!llmStatus?.probe.available ? (
                    <p className="mt-1 text-amber/80">
                      No model detected. Runs will record fallbacks instead of pretending a model decided.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}

            <button className="btn-primary mt-3 w-full" onClick={launch} disabled={busy || !scenario}>
              {busy ? <Spinner label="" /> : <Play className="h-3.5 w-3.5" />}
              {payload ? "Launch another run" : "Launch run"}
            </button>
            <label className="mt-2 flex items-center gap-1.5 text-[10px] text-fog">
              <input
                type="checkbox"
                checked={startImmediately}
                onChange={(event) => setStartImmediately(event.target.checked)}
                className="accent-mint"
              />
              start immediately
            </label>
          </Panel>

          {payload ? (
            <Panel title="Run controls">
              <RunControls
                status={payload.run.status}
                step={payload.state.step}
                horizon={payload.state.horizon_steps}
                speed={speed}
                onSpeed={setSpeed}
                onStart={() => control("start")}
                onPause={() => control("pause")}
                onStep={() => control("step")}
                onReset={() => control("reset")}
                onDisrupt={disrupt}
                busy={busy}
                kind={payload.state.kind}
              />
            </Panel>
          ) : null}
        </div>

        <div className="order-1 min-w-0 space-y-3 xl:order-2">
          <Panel
            bodyClassName="p-2.5"
            title={
              <span className="flex items-center gap-2">
                {liveState ? (liveState.kind === "city_logistics" ? "Riverside road network" : "Signal grid") : "Map preview"}
                {payload ? <StatusPill status={payload.run.status} /> : <span className="chip">preview</span>}
              </span>
            }
            action={
              payload ? (
                <Link to={`/runs/${payload.run.id}`} className="flex items-center gap-1 text-[10px] text-mint hover:underline">
                  replay <ExternalIcon className="h-3 w-3" />
                </Link>
              ) : (
                <span className="text-[10px] text-slate-600">seed {seed}</span>
              )
            }
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-0.5">
              <div className="flex flex-wrap items-center gap-2 text-[10px] text-fog">
                <span className="font-mono text-slate-300">
                  {payload ? `run ${payload.run.id}` : scenario?.name}
                </span>
                {liveState ? (
                  <>
                    <span className="text-slate-600">·</span>
                    <span className="font-mono">
                      t{liveState.step} / {liveState.horizon_steps}
                    </span>
                    <span className="text-slate-600">·</span>
                    <span className="font-mono">{clock(liveState.time_min)}</span>
                  </>
                ) : null}
              </div>
              <div className="flex items-center gap-1.5">
                {liveState?.kind === "city_logistics" ? (
                  <>
                    <span className="chip">
                      <Fuel className="h-2.5 w-2.5 text-sky" /> {num(liveState.vehicle.fuel_l, 2)} L
                    </span>
                    <span className="chip">
                      <Boxes className="h-2.5 w-2.5 text-amber" /> {liveState.vehicle.cargo.length}/{liveState.vehicle.capacity}
                    </span>
                  </>
                ) : null}
                {liveState?.kind === "traffic_control" ? (
                  <span className="chip">
                    <Gauge className="h-2.5 w-2.5 text-amber" /> min green {liveState.min_green}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="relative h-[clamp(340px,50vh,580px)] overflow-hidden rounded-lg border border-line/60">
              {liveState ? (
                <SimulationMap state={liveState} trail={trail} />
              ) : (
                <div className="flex h-full items-center justify-center bg-[#070d13]">
                  {preview.loading ? <Spinner label="Loading map" /> : <span className="text-xs text-slate-600">No map</span>}
                </div>
              )}
              {!payload && liveState ? (
                <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-[#070d13] via-[#070d13]/70 to-transparent px-3 pb-2.5 pt-8">
                  <div className="text-[10px] leading-relaxed text-fog">
                    Preview with default variations. Launch a run to record transitions.
                  </div>
                  <span className="chip">not recorded</span>
                </div>
              ) : null}
            </div>
          </Panel>

          <div className="grid gap-3 md:grid-cols-2">
            <Panel
              title={
                payload?.last_step
                  ? `Last decision · step ${payload.last_step.step ?? payload.state.step}`
                  : "Agent decision"
              }
              action={
                payload?.last_step ? (
                  <span className={`chip ${payload.last_step.ok ? "chip-mint" : "chip-coral"} !text-[9px]`}>
                    {payload.last_step.ok ? "engine accepted" : payload.last_step.code}
                  </span>
                ) : null
              }
            >
              {payload?.last_step ? (
                <DecisionCard step={payload.last_step} agentLabel={payload.agent.label} />
              ) : (
                <div className="space-y-2 text-[10px] leading-relaxed text-fog">
                  <div className="flex items-center gap-1.5 text-slate-300">
                    <Bot className="h-3.5 w-3.5 text-mint" />
                    {payload ? payload.agent.label : selectedBuiltin?.label || "No run yet"}
                  </div>
                  <p>
                    {payload
                      ? "Start or step the run to see the observation → action loop recorded here."
                      : "The agent only sees observations and permitted actions. Every action is validated by the engine before it changes the world."}
                  </p>
                  {!payload && spec.type === "external" ? (
                    <p className="font-mono text-[9px] text-slate-600">POST {externalUrl}</p>
                  ) : null}
                </div>
              )}
            </Panel>

            <Panel title={payload ? "Packages" : "Objectives"}>
              {payload?.state.kind === "city_logistics" ? (
                <PackageList packages={(payload.state as CityState).packages} />
              ) : payload?.state.kind === "traffic_control" ? (
                <TrafficList state={payload.state as TrafficState} />
              ) : scenario ? (
                <div className="space-y-2">
                  {scenario.objectives.map((objective) => (
                    <div key={objective} className="flex items-start gap-1.5 text-[10px] leading-relaxed text-slate-300">
                      <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-mint" />
                      {objective}
                    </div>
                  ))}
                  <div className="divider" />
                  {scenario.constraints.map((constraint) => (
                    <div key={constraint} className="flex items-start gap-1.5 text-[9px] leading-relaxed text-fog">
                      <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber" />
                      {constraint}
                    </div>
                  ))}
                </div>
              ) : null}
            </Panel>
          </div>
        </div>

        <div className="order-3 min-w-0 space-y-3">
          <Panel title="Evaluation" action={<span className="text-[9px] text-slate-600">from recorded state</span>}>
            {payload && evaluation ? (
              <MetricsPanel state={payload.state} evaluation={evaluation} />
            ) : (
              <PreviewMetrics state={preview.data?.snapshot ?? null} scenario={scenario} />
            )}
          </Panel>

          <Panel title="Event feed" action={<span className="chip !text-[9px]">{payload?.state.events.length ?? 0} events</span>} bodyClassName="p-2.5">
            <EventFeed events={payload?.state.events ?? []} />
          </Panel>

          {payload && payload.run.status !== "running" ? (
            <Panel title="Run summary">
              <div className="space-y-1.5 text-[10px]">
                <Row label="Terminal state" value={payload.state.terminal_reason?.replace(/_/g, " ") || "—"} />
                <Row label="Duration" value={duration(payload.run.duration_ms)} />
                <Row label="Steps" value={num(payload.state.step, 0)} />
                <Row label="State hash" value={payload.state.state_hash} mono />
                <Row label="Agent" value={payload.agent.label} />
                <Link to={`/runs/${payload.run.id}`} className="btn-ghost mt-2 w-full !py-1.5 !text-[10px]">
                  Open replay <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </Panel>
          ) : null}
        </div>
      </div>

      {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} /> : null}
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-fog">{label}</span>
      <span className={`truncate text-right text-slate-300 ${mono ? "font-mono text-[9px]" : ""}`}>{value}</span>
    </div>
  );
}

function DecisionCard({ step, agentLabel }: { step: LastStep; agentLabel: string }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 text-[10px]">
        <span className="flex items-center gap-1.5 text-slate-300">
          <Bot className="h-3.5 w-3.5 text-mint" /> {agentLabel}
        </span>
        <span className="font-mono text-slate-500">{num(step.latency_ms, 0)} ms</span>
      </div>
      <div className="rounded border border-line/60 bg-ink-950/60 px-2 py-1.5 font-mono text-[10px] text-mint">
        {JSON.stringify(step.action)}
      </div>
      <p className="text-[10px] leading-relaxed text-fog">
        {step.reasoning || step.reason || "No explanation recorded."}
      </p>
      {step.agent_error ? (
        <div className="rounded border border-coral/30 bg-coral/[0.06] px-2 py-1 text-[9px] text-coral">
          {step.agent_error} {step.fallback_used ? "· deterministic fallback applied" : ""}
        </div>
      ) : null}
      {!step.ok ? (
        <div className="rounded border border-amber/30 bg-amber/[0.06] px-2 py-1 text-[9px] text-amber">
          Engine rejected this action: {step.code}. The tick was still consumed.
        </div>
      ) : null}
    </div>
  );
}

function TrafficList({ state }: { state: TrafficState }) {
  return (
    <div className="max-h-[230px] space-y-1 overflow-y-auto pr-0.5">
      {state.intersections.map((intersection) => {
        const total = Object.values(intersection.queues).reduce((sum, value) => sum + value, 0);
        return (
          <div key={intersection.id} className="flex items-center gap-2 rounded border border-line/40 bg-ink-900/40 px-2 py-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${intersection.phase === "NS" ? "bg-mint" : "bg-sky"}`} />
            <span className="w-9 font-mono text-[10px] text-slate-300">{intersection.id}</span>
            <span className={`w-6 font-mono text-[9px] ${intersection.phase === "NS" ? "text-mint" : "text-sky"}`}>
              {intersection.phase}
            </span>
            <div className="flex flex-1 gap-1">
              {(["N", "S", "E", "W"] as const).map((approach) => (
                <span key={approach} className="flex-1 rounded bg-ink-950 px-1 py-0.5 text-center font-mono text-[9px] text-slate-500">
                  {approach} {intersection.queues[approach]}
                </span>
              ))}
            </div>
            <span className="w-8 text-right font-mono text-[9px] text-amber">{total}</span>
          </div>
        );
      })}
    </div>
  );
}

function PreviewMetrics({ state, scenario }: { state: SimState | null; scenario?: Scenario }) {
  if (!state) {
    return (
      <EmptyState
        icon={<Gauge className="h-6 w-6" />}
        title="No evaluation yet"
        detail="Launch a run to compute completion, on-time rate, fuel use, invalid actions, and latency from recorded transitions."
      />
    );
  }
  if (state.kind === "city_logistics") {
    const city = state as CityState;
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="label">initial conditions</div>
            <div className="mt-1 font-mono text-2xl font-semibold text-white">
              {city.packages.length}
              <span className="ml-1 text-xs font-normal text-fog">packages</span>
            </div>
          </div>
          <div className="text-right">
            <div className="label">fuel</div>
            <div className="mt-1 font-mono text-2xl font-semibold text-white">
              {num(city.vehicle.fuel_l, 1)}
              <span className="ml-1 text-xs font-normal text-fog">L</span>
            </div>
          </div>
        </div>
        <div className="space-y-1 text-[10px] text-fog">
          <Row label="Horizon" value={`${city.horizon_steps} ticks · ${city.horizon_steps * city.step_minutes} min`} />
          <Row label="Van capacity" value={`${city.vehicle.capacity} packages`} />
          <Row label="Fuel stations" value={`${city.stations.length}`} />
          <Row label="Observation" value={city.fog_radius ? `${city.fog_radius}-hop local view` : "full city"} />
        </div>
        <div className="rounded border border-line/60 bg-ink-900/50 p-2 text-[9px] leading-relaxed text-slate-500">
          Metrics appear after the first recorded step. The preview is never scored.
        </div>
      </div>
    );
  }
  const traffic = state as TrafficState;
  return (
    <div className="space-y-3">
      <div>
        <div className="label">signal network</div>
        <div className="mt-1 font-mono text-2xl font-semibold text-white">
          {traffic.intersections.length}
          <span className="ml-1 text-xs font-normal text-fog">intersections</span>
        </div>
      </div>
      <div className="space-y-1 text-[10px] text-fog">
        <Row label="Horizon" value={`${traffic.horizon_steps} ticks`} />
        <Row label="Min green" value={`${traffic.min_green} ticks`} />
        <Row label="Incidents" value={`${traffic.events.length}`} />
      </div>
      <div className="rounded border border-line/60 bg-ink-900/50 p-2 text-[9px] leading-relaxed text-slate-500">
        {scenario?.tagline}
      </div>
    </div>
  );
}