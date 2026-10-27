import {
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FastForward,
  GitCompareArrows,
  ListVideo,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  SkipBack,
  SkipForward,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { clock, duration, formatMetric, num, pct, relativeTime } from "../lib/format";
import type { CityState, ReplayPayload, ReplayStep, TrafficState } from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import CityMap from "../components/maps/CityMap";
import TrafficMap from "../components/maps/TrafficMap";
import { EmptyState, ErrorBanner, Panel, ScoreComponents, ScoreRing, Spinner } from "../components/ui";
import { EventFeed, MetricsPanel, PackageList, StatusPill } from "../components/sim";

function actionLabel(action: Record<string, unknown> | null): string {
  if (!action) return "—";
  const type = String(action.type || "action");
  if (type === "move") return `move → ${action.target}`;
  if (type === "deliver") return `deliver ${action.package_id}`;
  if (type === "pickup") {
    const ids = (action.package_ids as string[] | undefined) || [action.package_id];
    return `pickup ${ids.filter(Boolean).join(", ")}`;
  }
  if (type === "refuel") return `refuel ${action.amount ?? ""} L`;
  if (type === "set_phase") return `signal ${action.intersection} → ${action.phase}`;
  if (type === "wait") return "wait";
  return type;
}

function Sparkline({
  values,
  color = "#38e3ab",
  label,
  unit,
}: {
  values: number[];
  color?: string;
  label: string;
  unit?: string;
}) {
  const width = 220;
  const height = 46;
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * width;
      const y = height - 4 - ((value - min) / span) * (height - 10);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="rounded border border-line/50 bg-ink-900/40 p-2">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[9px] uppercase tracking-[0.12em] text-slate-500">{label}</span>
        <span className="font-mono text-[10px] text-slate-300">
          {unit === "%" ? pct(values[values.length - 1], 0) : num(values[values.length - 1], 1)}
          {unit && unit !== "%" ? ` ${unit}` : ""}
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[38px] w-full" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
        <polyline points={`0,${height} ${points} ${width},${height}`} fill={`${color}14`} stroke="none" />
      </svg>
    </div>
  );
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { data: replay, error, loading, reload } = useApiData<ReplayPayload>(
    () => (runId ? api.replay(runId) : Promise.reject(new Error("Missing run id"))),
    [runId],
  );
  const { data: scenarioData } = useApiData(() => api.scenarios(), []);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(600);

  useEffect(() => {
    if (!replay) return;
    setIndex(replay.steps.length);
    setPlaying(false);
  }, [replay?.run.id, replay?.steps.length]);

  useEffect(() => {
    if (!playing || !replay) return;
    if (index >= replay.steps.length) {
      setPlaying(false);
      return;
    }
    const handle = window.setTimeout(() => setIndex((value) => Math.min(replay.steps.length, value + 1)), speed);
    return () => window.clearTimeout(handle);
  }, [playing, index, speed, replay]);

  const scenario = scenarioData?.scenarios.find((item) => item.id === replay?.run.scenario_id);
  const state = replay
    ? index === 0
      ? replay.initial_snapshot
      : replay.steps[index - 1]?.state ?? replay.initial_snapshot
    : null;
  const currentStep: ReplayStep | null = replay && index > 0 ? replay.steps[index - 1] : null;

  const trail = useMemo(() => {
    if (!replay || !state || state.kind !== "city_logistics") return [];
    const nodes: string[] = [];
    for (let i = 0; i < index; i += 1) {
      const stepState = replay.steps[i]?.state;
      if (stepState?.kind === "city_logistics") nodes.push((stepState as CityState).vehicle.node);
    }
    nodes.push((state as CityState).vehicle.node);
    return nodes;
  }, [replay, index, state]);

  if (loading && !replay) {
    return (
      <Panel>
        <Spinner label="Loading replay" />
      </Panel>
    );
  }
  if (error) {
    return (
      <div className="space-y-3">
        <Link to="/runs" className="inline-flex items-center gap-1 text-[11px] text-fog hover:text-white">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to runs
        </Link>
        <ErrorBanner message={error} onRetry={reload} />
      </div>
    );
  }
  if (!replay || !state) return null;

  const evaluation = replay.evaluation;
  const total = replay.steps.length;
  const metricsAtStep = currentStep?.metrics || replay.initial_snapshot.metrics || {};
  const series = [replay.initial_snapshot.metrics || {}, ...replay.steps.map((step) => step.metrics)];
  const visibleSeries = series.slice(0, index + 1);
  const city = state.kind === "city_logistics" ? (state as CityState) : null;
  const traffic = state.kind === "traffic_control" ? (state as TrafficState) : null;

  const deliveredSeries = visibleSeries.map((item) => Number(item.packages_delivered ?? 0));
  const fuelSeries = visibleSeries.map((item) => Number(item.fuel_remaining_l ?? 0));
  const throughputSeries = visibleSeries.map((item) => Number(item.vehicles_discharged ?? 0));
  const waitSeries = visibleSeries.map((item) => Number(item.avg_wait_ticks ?? 0));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to="/runs" className="btn-icon" aria-label="Back to runs">
            <ArrowLeft className="h-3.5 w-3.5" />
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-white">{replay.run.id}</span>
              <StatusPill status={replay.run.status} />
              <span className="chip">{scenario?.name || replay.run.scenario_id}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-fog">
              <span>seed {replay.run.seed}</span>
              <span className="text-slate-600">·</span>
              <span>{replay.agent.label}</span>
              <span className="text-slate-600">·</span>
              <span>{relativeTime(replay.run.created_at)}</span>
              <span className="text-slate-600">·</span>
              <span>{duration(replay.run.duration_ms)}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" onClick={reload}>
            <RotateCcw className="h-3.5 w-3.5" /> Refresh
          </button>
          <Link to={`/compare?run=${replay.run.id}`} className="btn-ghost">
            <GitCompareArrows className="h-3.5 w-3.5" /> Compare
          </Link>
        </div>
      </div>

      <Panel bodyClassName="p-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-icon" onClick={() => setIndex(0)} disabled={index === 0} aria-label="First step">
            <SkipBack className="h-3.5 w-3.5" />
          </button>
          <button className="btn-icon" onClick={() => setIndex((value) => Math.max(0, value - 1))} disabled={index === 0} aria-label="Previous step">
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            className="btn-primary !px-3"
            onClick={() => {
              if (index >= total) setIndex(0);
              setPlaying((value) => !value);
            }}
            disabled={total === 0}
          >
            {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {playing ? "Pause" : "Replay"}
          </button>
          <button
            className="btn-icon"
            onClick={() => setIndex((value) => Math.min(total, value + 1))}
            disabled={index >= total}
            aria-label="Next step"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
          <button className="btn-icon" onClick={() => setIndex(total)} disabled={index >= total} aria-label="Last step">
            <SkipForward className="h-3.5 w-3.5" />
          </button>
          <div className="mx-2 flex min-w-[160px] flex-1 items-center gap-2">
            <input
              type="range"
              min={0}
              max={Math.max(1, total)}
              value={index}
              onChange={(event) => {
                setPlaying(false);
                setIndex(Number(event.target.value));
              }}
              className="h-1 flex-1 accent-mint"
              aria-label="Replay position"
            />
          </div>
          <span className="font-mono text-[10px] text-slate-400">
            t{state.step} / {total}
          </span>
          <select className="select !w-auto !py-1 !text-[10px]" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
            <option value={300}>0.3s</option>
            <option value={600}>0.6s</option>
            <option value={1000}>1s</option>
            <option value={1600}>1.6s</option>
          </select>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line/50 pt-2 text-[10px] text-fog">
          <Clock3 className="h-3 w-3 text-slate-500" />
          <span className="font-mono">{clock(state.time_min)}</span>
          <span className="text-slate-600">·</span>
          <span>state hash</span>
          <span className="font-mono text-slate-400">{state.state_hash}</span>
          {currentStep ? (
            <>
              <span className="text-slate-600">·</span>
              <span className={currentStep.valid ? "text-mint" : "text-coral"}>
                {currentStep.valid ? "action accepted" : `rejected: ${currentStep.decision?.code}`}
              </span>
              <span className="text-slate-600">·</span>
              <span className="font-mono">{num(currentStep.latency_ms, 0)} ms</span>
            </>
          ) : (
            <span className="text-slate-600">· initial state (step 0)</span>
          )}
          {replay.run.status === "running" ? <span className="chip-amber">live run — more steps may appear</span> : null}
        </div>
      </Panel>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <Panel bodyClassName="p-2" title={`${state.kind === "city_logistics" ? "City state" : "Signal state"} · step ${state.step}`}>
            <div className="h-[clamp(340px,48vh,560px)] overflow-hidden rounded-lg border border-line/60">
              {state.kind === "city_logistics" ? (
                <CityMap state={state as CityState} trail={(state as CityState).trail ?? trail} />
              ) : (
                <TrafficMap state={state as TrafficState} />
              )}
            </div>
          </Panel>

          <div className="grid gap-3 md:grid-cols-2">
            <Panel title="Decision at this step" action={currentStep ? <span className="font-mono text-[9px] text-slate-600">t{currentStep.step}</span> : null}>
              {currentStep ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5">
                    <span className={`chip ${currentStep.valid ? "chip-mint" : "chip-coral"} !text-[9px]`}>
                      {currentStep.valid ? "accepted" : currentStep.decision?.code}
                    </span>
                    <span className="font-mono text-[9px] text-slate-600">{num(currentStep.latency_ms, 0)} ms</span>
                    {currentStep.decision?.fallback_used ? <span className="chip-amber !text-[9px]">fallback</span> : null}
                  </div>
                  <div className="rounded border border-line/60 bg-ink-950/60 px-2 py-1.5 font-mono text-[10px] text-mint">
                    {actionLabel(currentStep.action)}
                  </div>
                  <p className="text-[10px] leading-relaxed text-fog">
                    {currentStep.decision?.reasoning || currentStep.reason || "No reasoning recorded."}
                  </p>
                  {currentStep.decision?.error ? (
                    <div className="flex items-start gap-1.5 rounded border border-coral/25 bg-coral/[0.05] px-2 py-1 text-[9px] leading-relaxed text-coral">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                      {currentStep.decision.error}
                    </div>
                  ) : null}
                  {!currentStep.valid ? (
                    <div className="rounded border border-amber/25 bg-amber/[0.05] px-2 py-1 text-[9px] leading-relaxed text-amber">
                      {currentStep.reason}
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-[10px] leading-relaxed text-fog">
                  This is the stored initial state. Move the replay forward to inspect the first action.
                </p>
              )}
            </Panel>

            <Panel title="Telemetry">
              <div className="space-y-2">
                {city ? (
                  <>
                    <Sparkline values={deliveredSeries} label="Delivered" />
                    <Sparkline values={fuelSeries} color="#72a9ff" label="Fuel remaining" unit="L" />
                    <div className="grid grid-cols-3 gap-1.5 pt-1">
                      <MetricChip label="Delivered" value={`${metricsAtStep.packages_delivered ?? 0}/${metricsAtStep.packages_total ?? 0}`} />
                      <MetricChip label="Fuel" value={`${num(Number(metricsAtStep.fuel_remaining_l), 1)} L`} />
                      <MetricChip label="Invalid" value={num(Number(metricsAtStep.invalid_actions), 0)} />
                    </div>
                  </>
                ) : (
                  <>
                    <Sparkline values={throughputSeries} label="Vehicles cleared" />
                    <Sparkline values={waitSeries} color="#f5b84c" label="Average wait" unit="ticks" />
                    <div className="grid grid-cols-3 gap-1.5 pt-1">
                      <MetricChip label="Cleared" value={num(Number(metricsAtStep.vehicles_discharged), 0)} />
                      <MetricChip label="Wait" value={num(Number(metricsAtStep.avg_wait_ticks), 1)} />
                      <MetricChip label="Violations" value={num(Number(metricsAtStep.rule_violations), 0)} />
                    </div>
                  </>
                )}
              </div>
            </Panel>
          </div>

          <Panel
            title={
              <span className="flex items-center gap-1.5">
                <ListVideo className="h-3 w-3" /> Action timeline
              </span>
            }
            action={<span className="text-[9px] text-slate-600">{total} recorded steps</span>}
            bodyClassName="p-2"
          >
            {total === 0 ? (
              <div className="p-3">
                <EmptyState icon={<FastForward className="h-5 w-5" />} title="No steps recorded" detail="This run was created but never stepped." />
              </div>
            ) : (
              <div className="max-h-[300px] overflow-y-auto">
                <table className="w-full border-collapse">
                  <thead className="sticky top-0 bg-ink-850">
                    <tr>
                      <th className="table-head !py-1.5">#</th>
                      <th className="table-head !py-1.5">Action</th>
                      <th className="table-head !py-1.5">Result</th>
                      <th className="table-head !py-1.5">Latency</th>
                      <th className="table-head !py-1.5">Reasoning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {replay.steps.map((step) => {
                      const active = index === step.step;
                      return (
                        <tr
                          key={step.step}
                          onClick={() => {
                            setPlaying(false);
                            setIndex(step.step);
                          }}
                          className={`cursor-pointer transition ${active ? "bg-mint/[0.06]" : "hover:bg-white/[0.025]"}`}
                        >
                          <td className={`table-cell font-mono ${active ? "text-mint" : "text-slate-500"}`}>{step.step}</td>
                          <td className="table-cell font-mono text-[10px] text-slate-300">{actionLabel(step.action)}</td>
                          <td className="table-cell">
                            <span className={`text-[9px] font-medium ${step.valid ? "text-mint" : "text-coral"}`}>
                              {step.valid ? "ok" : step.decision?.code || "rejected"}
                            </span>
                          </td>
                          <td className="table-cell font-mono text-[9px]">{num(step.latency_ms, 0)} ms</td>
                          <td className="table-cell max-w-[280px] truncate text-[9px] text-fog">{step.decision?.reasoning || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-3">
          <Panel title="Final evaluation" action={<span className="text-[9px] text-slate-600">recorded</span>}>
            <MetricsPanel state={state} evaluation={evaluation} compact final />
          </Panel>

          <Panel title="Failure analysis">
            <div className="space-y-1.5">
              {(evaluation.failures || []).map((failure) => (
                <div key={failure} className="flex items-start gap-1.5 rounded border border-line/60 bg-ink-900/40 px-2 py-1.5 text-[10px] leading-relaxed text-fog">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber" />
                  {failure}
                </div>
              ))}
              {evaluation.failures?.length === 0 ? (
                <div className="flex items-center gap-1.5 text-[10px] text-mint">
                  <ShieldCheck className="h-3.5 w-3.5" /> No objective failures recorded.
                </div>
              ) : null}
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                <MetricChip label="Agent errors" value={num(evaluation.agent_errors, 0)} />
                <MetricChip label="Fallbacks" value={num(evaluation.agent_fallbacks, 0)} />
                <MetricChip label="Recovery" value={evaluation.recovery_steps === null ? "n/a" : `${evaluation.recovery_steps} steps`} />
                <MetricChip label="Disruptions" value={num(evaluation.disruption_count, 0)} />
              </div>
            </div>
          </Panel>

          <Panel title="Run configuration">
            <div className="space-y-1 text-[10px]">
              <ConfigRow label="Scenario" value={replay.run.scenario_id} />
              <ConfigRow label="Version" value={String(replay.run.scenario_version)} />
              <ConfigRow label="Seed" value={String(replay.run.seed)} />
              <ConfigRow label="Agent" value={`${replay.agent.label} (${replay.agent.type})`} />
              <ConfigRow label="Terminal" value={replay.run.terminal_reason?.replace(/_/g, " ") || "—"} />
              <ConfigRow label="Duration" value={duration(replay.run.duration_ms)} />
              <ConfigRow label="State hash" value={replay.steps[replay.steps.length - 1]?.state.state_hash || replay.initial_snapshot.state_hash} mono />
              {Object.entries(replay.run.options || {}).map(([key, value]) => (
                <ConfigRow key={key} label={key.replace(/_/g, " ")} value={String(value)} />
              ))}
            </div>
          </Panel>

          <Panel title="Event timeline" bodyClassName="p-2.5">
            <EventFeed events={state.events} limit={60} />
          </Panel>

          {city ? (
            <Panel title="Packages at this step">
              <PackageList packages={city.packages} />
            </Panel>
          ) : null}

          {traffic ? (
            <Panel title="Signals at this step">
              <div className="space-y-1">
                {traffic.intersections.map((intersection) => (
                  <div key={intersection.id} className="flex items-center gap-2 rounded border border-line/40 bg-ink-900/40 px-2 py-1.5 text-[10px]">
                    <span className={`h-1.5 w-1.5 rounded-full ${intersection.phase === "NS" ? "bg-mint" : "bg-sky"}`} />
                    <span className="w-9 font-mono text-slate-300">{intersection.id}</span>
                    <span className={intersection.phase === "NS" ? "text-mint" : "text-sky"}>{intersection.phase}</span>
                    <span className="ml-auto font-mono text-[9px] text-slate-500">
                      {Object.values(intersection.queues).reduce((sum, value) => sum + value, 0)} queued
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          ) : null}
        </div>
      </div>

      <Panel title="Score breakdown">
        <div className="flex flex-wrap items-center gap-6">
          <ScoreRing score={evaluation.score} size={104} />
          <div className="min-w-[240px] flex-1">
            <ScoreComponents components={evaluation.score_components || {}} />
          </div>
          <div className="grid grid-cols-2 gap-1.5 text-[10px] sm:grid-cols-4">
            {[
              ["completion_rate", "Completion"],
              ["on_time_rate", "On time"],
              ["fuel_consumed_l", "Fuel"],
              ["invalid_actions", "Invalid"],
              ["agent_latency_ms", "Latency"],
              ["distance_km", "Distance"],
              ["recovery_steps", "Recovery"],
              ["score", "Score"],
            ].map(([key, label]) => (
              <MetricChip key={key} label={label} value={formatMetric(key, (evaluation as Record<string, unknown>)[key])} />
            ))}
          </div>
        </div>
      </Panel>
    </div>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line/50 bg-ink-900/40 px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">{label}</div>
      <div className="font-mono text-[11px] text-slate-300">{value}</div>
    </div>
  );
}

function ConfigRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="capitalize text-fog">{label}</span>
      <span className={`max-w-[190px] break-words text-right text-slate-300 ${mono ? "font-mono text-[9px]" : "font-mono text-[10px]"}`}>
        {value}
      </span>
    </div>
  );
}