import {
  AlertTriangle,
  Boxes,
  Clock3,
  Fuel,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  Satellite,
  ShieldAlert,
  SkipForward,
  Siren,
  Timer,
  TriangleAlert,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";
import { clock, num, pct, scoreTone, statusTone } from "../lib/format";
import type {
  CityState,
  Evaluation,
  SimEvent,
  SimPackage,
  SimState,
  TrafficState,
} from "../lib/types";
import { ScoreComponents, ScoreRing } from "./ui";
import CityMap from "./maps/CityMap";
import TrafficMap from "./maps/TrafficMap";

export function StatusPill({ status }: { status: string }) {
  const tone = statusTone(status);
  const cls =
    tone === "mint"
      ? "border-mint/40 bg-mint/10 text-mint"
      : tone === "amber"
        ? "border-amber/40 bg-amber/10 text-amber"
        : tone === "coral"
          ? "border-coral/40 bg-coral/10 text-coral"
          : tone === "sky"
            ? "border-sky/40 bg-sky/10 text-sky"
            : "border-line bg-ink-800 text-fog";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${tone === "sky" ? "animate-pulse-dot bg-sky" : tone === "mint" ? "bg-mint" : tone === "amber" ? "bg-amber" : tone === "coral" ? "bg-coral" : "bg-fog"}`} />
      {status}
    </span>
  );
}

export function SimulationMap({
  state,
  trail,
  compact,
}: {
  state: SimState;
  trail?: string[];
  compact?: boolean;
}) {
  if (state.kind === "city_logistics") {
    return <CityMap state={state as CityState} trail={trail} compact={compact} />;
  }
  return <TrafficMap state={state as TrafficState} compact={compact} />;
}

export function RunControls({
  status,
  step,
  horizon,
  speed,
  onSpeed,
  onStart,
  onPause,
  onStep,
  onReset,
  onDisrupt,
  busy,
  kind,
  disabled,
}: {
  status: string;
  step: number;
  horizon: number;
  speed: number;
  onSpeed: (value: number) => void;
  onStart: () => void;
  onPause: () => void;
  onStep: () => void;
  onReset: () => void;
  onDisrupt: (type: string) => void;
  busy: boolean;
  kind: string;
  disabled?: boolean;
}) {
  const finished = status === "finished" || status === "failed";
  const running = status === "running";
  const disruptions =
    kind === "city_logistics"
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
      <div className="flex flex-wrap items-center gap-1.5">
        {finished ? (
          <span className={`inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-xs font-semibold ${status === "failed" ? "border-coral/40 bg-coral/10 text-coral" : "border-mint/40 bg-mint/10 text-mint"}`}>
            {status === "failed" ? "run failed" : "run complete"}
          </span>
        ) : running ? (
          <button className="btn-ghost" onClick={onPause} disabled={busy || disabled}>
            <Pause className="h-3.5 w-3.5" /> Pause
          </button>
        ) : (
          <button className="btn-primary" onClick={onStart} disabled={busy || disabled}>
            <Play className="h-3.5 w-3.5" /> {status === "paused" ? "Resume" : "Start"}
          </button>
        )}
        <button className="btn-ghost" onClick={onStep} disabled={busy || disabled || finished}>
          <SkipForward className="h-3.5 w-3.5" /> Step
        </button>
        <button className="btn-ghost" onClick={onReset} disabled={busy || disabled}>
          <RotateCcw className="h-3.5 w-3.5" /> Reset
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-[9px] uppercase tracking-[0.14em] text-slate-500">tick</span>
          <select className="select !w-[74px] !py-1 !text-[10px]" value={speed} onChange={(event) => onSpeed(Number(event.target.value))}>
            <option value={0}>max</option>
            <option value={150}>150 ms</option>
            <option value={300}>300 ms</option>
            <option value={600}>600 ms</option>
            <option value={1200}>1.2 s</option>
          </select>
        </div>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] text-fog">
          <span>shift clock {clock(0)} → {clock(horizon * 2)}</span>
          <span className="font-mono">{step}/{horizon}</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-ink-950">
          <div
            className="h-full rounded-full bg-gradient-to-r from-mint/60 to-mint transition-all"
            style={{ width: `${Math.min(100, (step / Math.max(1, horizon)) * 100)}%` }}
          />
        </div>
      </div>

      <div>
        <div className="label mb-1.5 flex items-center gap-1.5">
          <Zap className="h-3 w-3 text-amber" /> inject disruption
        </div>
        <div className="flex flex-wrap gap-1.5">
          {disruptions.map((item) => (
            <button
              key={item.type}
              className="rounded border border-line bg-ink-900/70 px-2 py-1 text-[10px] text-fog transition hover:border-amber/40 hover:text-amber disabled:opacity-40"
              onClick={() => onDisrupt(item.type)}
              disabled={busy || disabled || finished || !running}
            >
              {item.label}
            </button>
          ))}
        </div>
        {!running && !finished ? (
          <div className="mt-1 text-[9px] text-slate-600">Start the run to inject live events.</div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "mint" | "amber" | "coral";
}) {
  const color =
    tone === "mint" ? "text-mint" : tone === "amber" ? "text-amber" : tone === "coral" ? "text-coral" : "text-white";
  return (
    <div className="rounded-md border border-line/60 bg-ink-900/50 px-2.5 py-2">
      <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-[0.12em] text-slate-500">
        {icon}
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-base font-semibold tabular-nums ${color}`}>{value}</div>
      {hint ? <div className="text-[9px] text-slate-600">{hint}</div> : null}
    </div>
  );
}

export function MetricsPanel({
  state,
  evaluation,
  compact = false,
  final = false,
}: {
  state: SimState;
  evaluation: Evaluation;
  compact?: boolean;
  final?: boolean;
}) {
  const tone = scoreTone(evaluation.score);
  const city = state.kind === "city_logistics" ? (state as CityState) : null;
  const traffic = state.kind === "traffic_control" ? (state as TrafficState) : null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <ScoreRing score={evaluation.score} size={compact ? 92 : 108} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${tone === "mint" ? "text-mint" : tone === "amber" ? "text-amber" : tone === "coral" ? "text-coral" : "text-fog"}`}>
            {lateness(evaluation.score)}
          </div>
          <div className="text-[10px] leading-relaxed text-fog">
            {!final && state.status === "running"
              ? "Live score from recorded transitions so far."
              : "Final score from the recorded run."}
          </div>
          <div className="flex flex-wrap gap-1">
            <span className="chip">{num(evaluation.agent_latency_ms, 0)} ms agent</span>
            <span className="chip">{num(Number(evaluation.steps ?? state.step), 0)} steps</span>
          </div>
        </div>
      </div>

      <ScoreComponents components={evaluation.score_components || {}} />

      <div className="grid grid-cols-2 gap-1.5">
        {city ? (
          <>
            <Stat
              icon={<Boxes className="h-3 w-3" />}
              label="Delivered"
              value={`${Number(evaluation.packages_delivered ?? city.metrics.packages_delivered)}/${Number(evaluation.packages_total ?? city.metrics.packages_total)}`}
              hint={`${pct(evaluation.completion_rate as number, 0)} complete`}
              tone={evaluation.completion_rate === 1 ? "mint" : "default"}
            />
            <Stat
              icon={<Clock3 className="h-3 w-3" />}
              label="On time"
              value={`${Number(evaluation.packages_on_time ?? city.metrics.packages_on_time)}/${Number(evaluation.packages_total ?? city.metrics.packages_total)}`}
              hint={`${pct(evaluation.on_time_rate as number, 0)} on time`}
              tone={Number(evaluation.on_time_rate) > 0.6 ? "mint" : "amber"}
            />
            <Stat icon={<Fuel className="h-3 w-3" />} label="Fuel used" value={`${num(Number(evaluation.fuel_consumed_l), 1)} L`} hint={`${num(Number(evaluation.fuel_remaining_l), 1)} L left`} tone={Number(evaluation.fuel_remaining_l) < 1 ? "coral" : "default"} />
            <Stat icon={<ShieldAlert className="h-3 w-3" />} label="Invalid" value={num(Number(evaluation.invalid_actions), 0)} hint="engine rejections" tone={Number(evaluation.invalid_actions) > 0 ? "coral" : "mint"} />
          </>
        ) : null}
        {traffic ? (
          <>
            <Stat
              icon={<Gauge className="h-3 w-3" />}
              label="Throughput"
              value={pct(evaluation.throughput_rate as number, 0)}
              hint={`${Number(evaluation.vehicles_discharged ?? traffic.metrics.vehicles_discharged)}/${Number(evaluation.vehicles_arrived ?? traffic.metrics.vehicles_arrived)} cleared`}
              tone={Number(evaluation.throughput_rate) > 0.85 ? "mint" : "amber"}
            />
            <Stat icon={<Timer className="h-3 w-3" />} label="Avg wait" value={`${num(Number(evaluation.avg_wait_ticks), 1)}`} hint="ticks to clear" />
            <Stat icon={<Satellite className="h-3 w-3" />} label="Congestion" value={`${num(Number(evaluation.avg_queue_length), 1)}`} hint="mean queue" />
            <Stat icon={<ShieldAlert className="h-3 w-3" />} label="Violations" value={num(Number(evaluation.rule_violations), 0)} hint="min-green blocks" tone={Number(evaluation.rule_violations) > 0 ? "coral" : "mint"} />
          </>
        ) : null}
      </div>

      {evaluation.failures?.length ? (
        <div className="space-y-1">
          {evaluation.failures.slice(0, 4).map((failure) => (
            <div key={failure} className="flex items-start gap-1.5 rounded border border-line/60 bg-ink-900/50 px-2 py-1.5 text-[10px] leading-relaxed text-fog">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber" />
              {failure}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function lateness(score: number | null | undefined): string {
  if (score === null || score === undefined) return "unscored";
  if (score >= 85) return "mission capable";
  if (score >= 70) return "competent";
  if (score >= 45) return "partial success";
  return "failing";
}

export function EventFeed({ events, limit = 40 }: { events: SimEvent[]; limit?: number }) {
  const ordered = [...events].reverse().slice(0, limit);
  if (!ordered.length) {
    return (
      <div className="flex h-full min-h-[120px] items-center justify-center px-4 text-center text-[11px] text-slate-600">
        No events yet. Scheduled disruptions and agent failures appear here.
      </div>
    );
  }
  return (
    <div className="max-h-[280px] space-y-1 overflow-y-auto pr-0.5">
      {ordered.map((event) => {
        const critical = event.severity === "critical";
        const warning = event.severity === "warning";
        const Icon = critical ? Siren : warning ? TriangleAlert : Satellite;
        const color = critical ? "text-coral" : warning ? "text-amber" : "text-sky";
        return (
          <div key={`${event.seq}-${event.step}`} className="flex items-start gap-2 rounded border border-line/40 bg-ink-900/40 px-2 py-1.5 animate-fade-up">
            <Icon className={`mt-0.5 h-3 w-3 shrink-0 ${color}`} />
            <div className="min-w-0 flex-1">
              <div className="text-[10px] leading-relaxed text-slate-300">{event.message || event.type}</div>
              <div className="flex items-center gap-1.5 font-mono text-[9px] text-slate-600">
                <span>t{event.step}</span>
                <span>·</span>
                <span>{clock(event.time_min)}</span>
                <span>·</span>
                <span className="uppercase">{event.type.replace(/_/g, " ")}</span>
                {event.source === "live" ? <span className="text-amber">live</span> : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function PackageList({ packages }: { packages: SimPackage[] }) {
  const ordered = [...packages].sort((a, b) => {
    const rank = (pkg: SimPackage) => (pkg.status === "in_transit" ? 0 : pkg.status === "at_depot" ? 1 : 2);
    return rank(a) - rank(b) || a.deadline_min - b.deadline_min;
  });
  return (
    <div className="space-y-1">
      {ordered.map((pkg) => {
        const delivered = pkg.status === "delivered";
        const overdue = !delivered && pkg.deadline_min < 0;
        const tone = delivered ? (pkg.late ? "coral" : "mint") : pkg.status === "in_transit" ? "sky" : "amber";
        return (
          <div key={pkg.id} className="flex items-center gap-2 rounded border border-line/40 bg-ink-900/40 px-2 py-1.5">
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                tone === "mint" ? "bg-mint" : tone === "coral" ? "bg-coral" : tone === "sky" ? "bg-sky" : "bg-amber"
              }`}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-[10px] text-slate-300">{pkg.id}</span>
                <span className="truncate text-[9px] text-slate-600">{pkg.dest_label}</span>
              </div>
              <div className="text-[9px] text-slate-600">
                {delivered
                  ? `delivered t+${pkg.delivered_at_min}${pkg.late ? " · late" : ""}`
                  : `due ${pkg.deadline_min} min · ${pkg.dest}`}
              </div>
            </div>
            {overdue ? <span className="text-[9px] text-coral">overdue</span> : null}
            <span className={`text-[9px] font-medium ${tone === "mint" ? "text-mint" : tone === "coral" ? "text-coral" : tone === "sky" ? "text-sky" : "text-amber"}`}>
              {pkg.status === "in_transit" ? "loaded" : pkg.status === "at_depot" ? "queued" : pkg.late ? "late" : "done"}
            </span>
          </div>
        );
      })}
    </div>
  );
}