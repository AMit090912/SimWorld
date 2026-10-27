import {
  ArrowRight,
  Boxes,
  ChevronDown,
  Cpu,
  ExternalLink,
  Fuel,
  Gauge,
  Globe,
  ListChecks,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  SkipForward,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { clock, duration, num } from "../lib/format";
import type {
  AgentSpec,
  BuiltinAgent,
  CityState,
  Evaluation,
  LastStep,
  LLMStatus,
  RunPayload,
  Scenario,
  SimState,
  TrafficState,
} from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import { EmptyState, ErrorBanner, Field, Panel, ScoreComponents, ScoreRing, Spinner, Toast } from "../components/ui";
import { EventFeed, PackageList, SimulationMap, StatusPill } from "../components/sim";

type AgentMode = "builtin" | "external" | "llm";
type Tab = "events" | "packages" | "decisions";
type DecisionItem = LastStep & { step: number };

function specFor(mode: AgentMode, builtinId: string, url: string, model: string): AgentSpec {
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
  const [advanced, setAdvanced] = useState(false);

  const [payload, setPayload] = useState<RunPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "mint" | "coral" | "amber" } | null>(null);
  const [speed, setSpeed] = useState(300);
  const [trail, setTrail] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("events");
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
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
      setDecisions([]);
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
    const last = payload?.last_step;
    if (!last) return;
    const step = Number(last.step ?? payload?.state.step ?? 0);
    setDecisions((previous) => {
      if (previous[0]?.step === step) return previous;
      return [{ ...last, step }, ...previous].slice(0, 30);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload?.last_step?.step]);

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
  const spec = specFor(mode, builtinId, externalUrl, llmModel);
  const liveState = payload?.state ?? preview.data?.snapshot ?? null;
  const evaluation = payload?.evaluation ?? null;

  async function launch() {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createRun({ scenario_id: scenario.id, seed, options, agent: spec });
      setPayload(created);
      setTrail(created.state.kind === "city_logistics" ? [created.state.vehicle.node] : []);
      setDecisions([]);
      setTab("decisions");
      if (startImmediately) {
        const started = await api.startRun(created.run.id, speed);
        setPayload(started);
      }
      setToast({ message: `Run ${created.run.id} created.`, tone: "mint" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
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
        setDecisions([]);
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
      setTab("events");
      setToast({ message: next.injected?.message || "Disruption injected.", tone: "amber" });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (scenarioError) return <ErrorBanner message={scenarioError} />;

  const disruptions =
    (liveState?.kind ?? "city_logistics") === "city_logistics"
      ? [
          { type: "road_closure", label: "Close road" },
          { type: "deadline_change", label: "Move deadline" },
          { type: "fuel_cut", label: "Cut fuel" },
        ]
      : [
          { type: "incident", label: "Lane incident" },
          { type: "surge", label: "Traffic surge" },
        ];

  return (
    <div className="space-y-3">
      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      {/* ------------------------------- setup bar ------------------------------- */}
      <div className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[210px] flex-1">
            <Field label="Scenario">
              <select
                className="select"
                value={scenario?.id}
                onChange={(event) => {
                  setScenarioId(event.target.value);
                  setPayload(null);
                  setTrail([]);
                  setDecisions([]);
                }}
              >
                {scenarios.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="w-[84px]">
            <Field label="Seed">
              <div className="flex gap-1">
                <input
                  type="number"
                  min={0}
                  className="input font-mono"
                  value={seed}
                  onChange={(event) => setSeed(Math.max(0, Number(event.target.value) || 0))}
                />
                <button
                  className="btn-icon !h-[34px] !w-[34px]"
                  onClick={() => setSeed(Math.floor(Math.random() * 1_000_000))}
                  title="New seed"
                  aria-label="New seed"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </div>
            </Field>
          </div>

          <div className="min-w-[150px]">
            <Field label="Agent">
              <div className="grid grid-cols-3 gap-0.5 rounded-md border border-line bg-ink-950/60 p-0.5">
                {(
                  [
                    { id: "builtin", icon: Cpu, title: "Built-in" },
                    { id: "external", icon: Globe, title: "HTTP" },
                    { id: "llm", icon: Sparkles, title: "Model" },
                  ] as const
                ).map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setMode(item.id)}
                      title={item.title}
                      className={`flex items-center justify-center gap-1 rounded px-1 py-1.5 text-[10px] font-medium transition ${
                        mode === item.id ? "bg-ink-750 text-white" : "text-fog hover:text-slate-200"
                      }`}
                    >
                      <Icon className="h-3 w-3" />
                      <span className="hidden sm:inline">{item.title}</span>
                    </button>
                  );
                })}
              </div>
            </Field>
          </div>

          <div className="w-full min-w-0 sm:flex-1">
            {mode === "builtin" ? (
              <Field label="Strategy" hint={selectedBuiltin?.description}>
                <select className="select" value={builtinId} onChange={(event) => setBuiltinId(event.target.value)}>
                  {compatible.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.label}
                    </option>
                  ))}
                </select>
              </Field>
            ) : mode === "external" ? (
              <Field label="Agent endpoint">
                <input
                  className="input font-mono !text-[10px]"
                  value={externalUrl}
                  onChange={(event) => setExternalUrl(event.target.value)}
                  placeholder="http://127.0.0.1:9100/agent"
                />
              </Field>
            ) : (
              <Field
                label="Model"
                hint={
                  llmStatus
                    ? llmStatus.probe.available
                      ? `${llmStatus.model} · reachable`
                      : "No model answering — runs will record fallbacks"
                    : "Checking endpoint"
                }
              >
                <input
                  className="input font-mono !text-[10px]"
                  value={llmModel}
                  onChange={(event) => setLlmModel(event.target.value)}
                  placeholder={llmStatus?.model || "qwen2.5:1.5b-instruct"}
                />
              </Field>
            )}
          </div>

          <div className="flex w-full items-center gap-2 sm:w-auto">
            <label className="hidden items-center gap-1.5 text-[10px] text-fog sm:flex">
              <input
                type="checkbox"
                checked={startImmediately}
                onChange={(event) => setStartImmediately(event.target.checked)}
                className="accent-mint"
              />
              auto-start
            </label>
            <button className="btn-primary h-[38px] w-full px-4 sm:w-auto" onClick={launch} disabled={busy || !scenario}>
              {busy ? <Spinner label="" /> : payload ? <RotateCcw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {payload ? "New run" : "Launch run"}
            </button>
          </div>
        </div>

        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {scenario ? (
              <>
                <span className={scenario.kind === "city_logistics" ? "chip-sky" : "chip-mint"}>
                  {scenario.kind === "city_logistics" ? "City logistics" : "Traffic control"}
                </span>
                <span className="chip">{scenario.difficulty}</span>
                <span className="hidden text-[10px] text-slate-500 sm:inline">{scenario.tagline}</span>
              </>
            ) : null}
          </div>
          <button
            className="inline-flex items-center gap-1 text-[10px] text-fog transition hover:text-slate-200"
            onClick={() => setAdvanced((value) => !value)}
          >
            <Settings2 className="h-3 w-3" />
            {advanced ? "Hide options" : "Stress options"}
            <ChevronDown className={`h-3 w-3 transition ${advanced ? "rotate-180" : ""}`} />
          </button>
        </div>

        {advanced && scenario ? (
          <div className="mt-2 grid gap-2 border-t border-line/60 pt-2 sm:grid-cols-2 lg:grid-cols-4">
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
        ) : null}
      </div>

      {/* ------------------------------- workspace ------------------------------- */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_336px]">
        <div className="min-w-0">
          <section className="panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/70 px-3.5 py-2.5">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate text-xs font-semibold text-white">
                  {scenario?.name ?? "Simulation"}
                </span>
                <StatusPill status={payload?.run.status ?? "preview"} />
                {payload ? (
                  <span className="hidden font-mono text-[9px] text-slate-600 sm:inline">{payload.run.id}</span>
                ) : null}
              </div>
              <div className="flex items-center gap-2 text-[10px] text-fog">
                {liveState ? (
                  <>
                    <span className="font-mono">{clock(liveState.time_min)}</span>
                    <span className="text-slate-600">·</span>
                    <span className="font-mono">{liveState.step}/{liveState.horizon_steps}</span>
                  </>
                ) : null}
                {payload ? (
                  <Link to={`/runs/${payload.run.id}`} className="inline-flex items-center gap-1 text-mint hover:underline">
                    replay <ExternalLink className="h-3 w-3" />
                  </Link>
                ) : null}
              </div>
            </div>

            <div className="relative h-[clamp(430px,calc(100vh-310px),820px)] bg-[#070d13]">
              {liveState ? (
                <SimulationMap
                  state={liveState}
                  trail={liveState.kind === "city_logistics" ? liveState.trail ?? trail : trail}
                />
              ) : (
                <div className="flex h-full items-center justify-center">
                  {preview.loading ? <Spinner label="Loading map" /> : <span className="text-xs text-slate-600">No map</span>}
                </div>
              )}

              {/* live vitals */}
              {liveState?.kind === "city_logistics" ? (
                <div className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-1.5">
                  <span className="rounded-md border border-line/70 bg-ink-950/85 px-2 py-1 font-mono text-[10px] text-sky backdrop-blur">
                    <Fuel className="mr-1 inline h-3 w-3" />
                    {num(liveState.vehicle.fuel_l, 2)} L
                  </span>
                  <span className="rounded-md border border-line/70 bg-ink-950/85 px-2 py-1 font-mono text-[10px] text-amber backdrop-blur">
                    <Boxes className="mr-1 inline h-3 w-3" />
                    {liveState.vehicle.cargo.length}/{liveState.vehicle.capacity}
                  </span>
                  <span className="rounded-md border border-line/70 bg-ink-950/85 px-2 py-1 font-mono text-[10px] text-slate-300 backdrop-blur">
                    {num(liveState.vehicle.distance_km, 1)} km
                  </span>
                </div>
              ) : null}
              {liveState?.kind === "traffic_control" ? (
                <div className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-1.5">
                  <span className="rounded-md border border-line/70 bg-ink-950/85 px-2 py-1 font-mono text-[10px] text-slate-300 backdrop-blur">
                    <Gauge className="mr-1 inline h-3 w-3" />
                    {num(Number(liveState.metrics.vehicles_discharged), 0)} cleared
                  </span>
                  <span className="rounded-md border border-line/70 bg-ink-950/85 px-2 py-1 font-mono text-[10px] text-amber backdrop-blur">
                    min green {liveState.min_green}
                  </span>
                </div>
              ) : null}

              {!payload && liveState ? (
                <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-[#070d13] via-[#070d13]/60 to-transparent px-3 pb-2.5 pt-10">
                  <div className="text-[10px] text-fog">
                    Preview only. Set up a run above, then launch.
                  </div>
                  <span className="chip">not recorded</span>
                </div>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-1.5 border-t border-line/70 px-2.5 py-2">
              {payload ? (
                <>
                  {payload.run.status === "running" ? (
                    <button className="btn-ghost" onClick={() => control("pause")} disabled={busy}>
                      <Pause className="h-3.5 w-3.5" /> Pause
                    </button>
                  ) : payload.run.status === "finished" || payload.run.status === "failed" ? (
                    <span className={`inline-flex h-8 items-center rounded-md border px-2.5 text-[11px] font-semibold ${payload.run.status === "failed" ? "border-coral/40 bg-coral/10 text-coral" : "border-mint/40 bg-mint/10 text-mint"}`}>
                      {payload.run.status === "failed" ? "run failed" : "complete"}
                    </span>
                  ) : (
                    <button className="btn-primary" onClick={() => control("start")} disabled={busy}>
                      <Play className="h-3.5 w-3.5" /> {payload.run.status === "paused" ? "Resume" : "Start"}
                    </button>
                  )}
                  <button className="btn-ghost" onClick={() => control("step")} disabled={busy || payload.run.status === "finished" || payload.run.status === "failed"}>
                    <SkipForward className="h-3.5 w-3.5" /> Step
                  </button>
                  <button className="btn-ghost" onClick={() => control("reset")} disabled={busy}>
                    <RotateCcw className="h-3.5 w-3.5" /> Reset
                  </button>
                  <span className="mx-1 hidden h-5 w-px bg-line sm:block" />
                  <div className="flex flex-wrap items-center gap-1">
                    <span className="text-[9px] uppercase tracking-[0.14em] text-slate-600">inject</span>
                    {disruptions.map((item) => (
                      <button
                        key={item.type}
                        onClick={() => disrupt(item.type)}
                        disabled={busy || payload.run.status !== "running"}
                        className="rounded border border-line bg-ink-900/70 px-2 py-1 text-[10px] text-fog transition hover:border-amber/40 hover:text-amber disabled:opacity-40"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                  <div className="ml-auto flex items-center gap-1.5">
                    <span className="hidden text-[9px] uppercase tracking-[0.12em] text-slate-600 sm:inline">tick</span>
                    <select className="select !w-[76px] !py-1 !text-[10px]" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
                      <option value={0}>max</option>
                      <option value={150}>150 ms</option>
                      <option value={300}>300 ms</option>
                      <option value={600}>600 ms</option>
                      <option value={1200}>1.2 s</option>
                    </select>
                  </div>
                </>
              ) : null}
            </div>
          </section>
        </div>

        {/* ------------------------------- right rail ------------------------------- */}
        <aside className="min-w-0 space-y-3">
          <Panel title="Evaluation" action={<span className="text-[9px] text-slate-600">{payload ? "recorded" : "not scored"}</span>}>
            {payload && evaluation ? (
              <ScoreSummary state={payload.state} evaluation={evaluation} />
            ) : (
              <PreviewSummary state={preview.data?.snapshot ?? null} scenario={scenario} />
            )}
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-1.5">
                <ListChecks className="h-3 w-3" /> Activity
              </span>
            }
            action={
              <div className="flex gap-0.5 rounded border border-line bg-ink-950/60 p-0.5">
                {(
                  [
                    ["events", "Events"],
                    ["packages", "Packages"],
                    ["decisions", "Decisions"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setTab(value)}
                    className={`rounded px-1.5 py-0.5 text-[9px] font-medium transition ${tab === value ? "bg-ink-750 text-white" : "text-fog hover:text-slate-200"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            }
            bodyClassName="p-2.5"
          >
            {tab === "events" ? <EventFeed events={payload?.state.events ?? []} /> : null}
            {tab === "packages" ? (
              payload?.state.kind === "city_logistics" ? (
                <PackageList packages={(payload.state as CityState).packages} />
              ) : payload?.state.kind === "traffic_control" ? (
                <TrafficList state={payload.state as TrafficState} />
              ) : (
                <EmptyState title="No packages" detail="Start a city run to see the drop list." />
              )
            ) : null}
            {tab === "decisions" ? <DecisionList decisions={decisions} /> : null}
          </Panel>

          {payload && payload.run.status !== "running" ? (
            <Panel title="Run">
              <div className="space-y-1 text-[10px]">
                <Row label="Terminal" value={payload.state.terminal_reason?.replace(/_/g, " ") || "—"} />
                <Row label="Duration" value={duration(payload.run.duration_ms)} />
                <Row label="Steps" value={num(payload.state.step, 0)} />
                <Row label="Seed" value={String(payload.run.seed)} />
                <Row label="Agent" value={payload.agent.label} />
                <Link to={`/runs/${payload.run.id}`} className="btn-ghost mt-2 w-full !py-1.5 !text-[10px]">
                  Open replay <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </Panel>
          ) : null}
        </aside>
      </div>

      {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} /> : null}
    </div>
  );
}

function ScoreSummary({ state, evaluation }: { state: SimState; evaluation: Evaluation }) {
  const city = state.kind === "city_logistics" ? (state as CityState) : null;
  const traffic = state.kind === "traffic_control" ? (state as TrafficState) : null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <ScoreRing score={evaluation.score} size={104} />
        <div className="min-w-0 space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-mint">
            {Number(evaluation.score) >= 75 ? "on track" : Number(evaluation.score) >= 45 ? "partial" : "failing"}
          </div>
          <div className="text-[10px] leading-relaxed text-fog">
            {state.status === "running" ? "Live score from recorded transitions." : "Final score from the recorded run."}
          </div>
          <div className="flex flex-wrap gap-1">
            <span className="chip">{num(evaluation.agent_latency_ms, 0)} ms</span>
            <span className="chip">{num(state.step, 0)} steps</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {city ? (
          <>
            <Mini label="Delivered" value={`${city.metrics.packages_delivered}/${city.metrics.packages_total}`} tone="mint" />
            <Mini label="On time" value={`${city.metrics.packages_on_time}/${city.metrics.packages_total}`} tone="amber" />
            <Mini label="Fuel used" value={`${num(Number(city.metrics.fuel_consumed_l), 1)} L`} />
            <Mini label="Invalid" value={num(Number(city.metrics.invalid_actions), 0)} tone={Number(city.metrics.invalid_actions) ? "coral" : "mint"} />
          </>
        ) : null}
        {traffic ? (
          <>
            <Mini label="Throughput" value={`${Math.round(Number(traffic.metrics.throughput_rate) * 100)}%`} tone="mint" />
            <Mini label="Avg wait" value={num(Number(traffic.metrics.avg_wait_ticks), 1)} tone="amber" />
            <Mini label="Avg queue" value={num(Number(traffic.metrics.avg_queue_length), 1)} />
            <Mini label="Violations" value={num(Number(traffic.metrics.rule_violations), 0)} tone={Number(traffic.metrics.rule_violations) ? "coral" : "mint"} />
          </>
        ) : null}
      </div>

      <details className="group rounded border border-line/60 bg-ink-900/40 px-2.5 py-2">
        <summary className="flex cursor-pointer list-none items-center justify-between text-[10px] text-fog">
          Score breakdown
          <ChevronDown className="h-3 w-3 transition group-open:rotate-180" />
        </summary>
        <div className="mt-2">
          <ScoreComponents components={evaluation.score_components || {}} />
        </div>
      </details>

      {state.status !== "running" && evaluation.failures?.length ? (
        <div className="rounded border border-amber/25 bg-amber/[0.05] px-2 py-1.5 text-[10px] leading-relaxed text-amber/90">
          {evaluation.failures[0]}
        </div>
      ) : null}
    </div>
  );
}

function PreviewSummary({ state, scenario }: { state: SimState | null; scenario?: Scenario }) {
  if (!state) {
    return <Spinner label="Preparing preview" />;
  }
  if (state.kind === "city_logistics") {
    const city = state as CityState;
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-1.5">
          <Mini label="Packages" value={String(city.packages.length)} tone="mint" />
          <Mini label="Fuel" value={`${num(city.vehicle.fuel_l, 1)} L`} />
          <Mini label="Horizon" value={`${city.horizon_steps} t`} />
        </div>
        <p className="text-[10px] leading-relaxed text-fog">{scenario?.tagline}</p>
        <details className="group rounded border border-line/60 bg-ink-900/40 px-2.5 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between text-[10px] text-fog">
            Scenario brief
            <ChevronDown className="h-3 w-3 transition group-open:rotate-180" />
          </summary>
          <div className="mt-2 space-y-1.5">
            {scenario?.objectives.map((objective) => (
              <div key={objective} className="flex items-start gap-1.5 text-[10px] leading-relaxed text-slate-300">
                <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-mint/70" />
                {objective}
              </div>
            ))}
            <div className="divider" />
            {scenario?.constraints.map((constraint) => (
              <div key={constraint} className="flex items-start gap-1.5 text-[9px] leading-relaxed text-fog">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber" />
                {constraint}
              </div>
            ))}
          </div>
        </details>
        <div className="text-[9px] text-slate-600">Metrics appear after the first recorded step.</div>
      </div>
    );
  }
  const traffic = state as TrafficState;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1.5">
        <Mini label="Signals" value={String(traffic.intersections.length)} tone="mint" />
        <Mini label="Min green" value={`${traffic.min_green} t`} />
        <Mini label="Horizon" value={`${traffic.horizon_steps} t`} />
      </div>
      <p className="text-[10px] leading-relaxed text-fog">{scenario?.tagline}</p>
      <div className="text-[9px] text-slate-600">Metrics appear after the first recorded step.</div>
    </div>
  );
}

function Mini({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "mint" | "amber" | "coral" }) {
  const color = tone === "mint" ? "text-mint" : tone === "amber" ? "text-amber" : tone === "coral" ? "text-coral" : "text-white";
  return (
    <div className="rounded border border-line/60 bg-ink-900/50 px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">{label}</div>
      <div className={`font-mono text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function DecisionList({ decisions }: { decisions: DecisionItem[] }) {
  if (!decisions.length) {
    return <div className="px-2 py-6 text-center text-[10px] text-slate-600">Start or step the run to see decisions.</div>;
  }
  return (
    <div className="max-h-[300px] space-y-1 overflow-y-auto pr-0.5">
      {decisions.map((item) => (
        <div key={item.step} className="rounded border border-line/50 bg-ink-900/40 px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[9px] text-slate-600">t{item.step}</span>
            <span className={`text-[9px] ${item.ok ? "text-mint" : "text-coral"}`}>{item.ok ? "accepted" : item.code}</span>
            {item.agent_error ? <span className="chip-amber !text-[8px]">fallback</span> : null}
            <span className="ml-auto font-mono text-[9px] text-slate-600">{num(item.latency_ms, 0)} ms</span>
          </div>
          <div className="truncate font-mono text-[10px] text-slate-300">{JSON.stringify(item.action)}</div>
          <div className="line-clamp-2 text-[9px] leading-relaxed text-fog">{item.reasoning || item.reason}</div>
        </div>
      ))}
    </div>
  );
}

function TrafficList({ state }: { state: TrafficState }) {
  return (
    <div className="max-h-[300px] space-y-1 overflow-y-auto pr-0.5">
      {state.intersections.map((intersection) => {
        const total = Object.values(intersection.queues).reduce((sum, value) => sum + value, 0);
        return (
          <div key={intersection.id} className="flex items-center gap-2 rounded border border-line/40 bg-ink-900/40 px-2 py-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${intersection.phase === "NS" ? "bg-mint" : "bg-sky"}`} />
            <span className="w-9 font-mono text-[10px] text-slate-300">{intersection.id}</span>
            <span className={`w-6 font-mono text-[9px] ${intersection.phase === "NS" ? "text-mint" : "text-sky"}`}>{intersection.phase}</span>
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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-fog">{label}</span>
      <span className="truncate font-mono text-[10px] text-slate-300">{value}</span>
    </div>
  );
}