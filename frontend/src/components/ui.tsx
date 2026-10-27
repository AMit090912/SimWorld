import { AlertTriangle, ArrowUpRight, Check, Copy, Loader2, RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { useCopy } from "../hooks/useApiData";
import { pct, scoreTone } from "../lib/format";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="label mb-1.5 text-mint/80">{eyebrow}</div>
        <h1 className="text-balance text-2xl font-semibold tracking-tight text-white">{title}</h1>
        {description ? (
          <p className="mt-1.5 max-w-2xl text-xs leading-relaxed text-fog">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  action,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      {title ? (
        <header className="flex items-center justify-between gap-3 border-b border-line/70 px-3.5 py-2.5">
          <div className="text-2xs font-semibold uppercase tracking-[0.14em] text-fog">{title}</div>
          {action}
        </header>
      ) : null}
      <div className={`min-h-0 ${bodyClassName || "p-3.5"}`}>{children}</div>
    </section>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-fog">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-coral/30 bg-coral/[0.07] px-3 py-2.5 text-xs text-coral">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0 flex-1 leading-relaxed">{message}</div>
      {onRetry ? (
        <button className="inline-flex items-center gap-1 font-semibold hover:underline" onClick={onRetry}>
          <RotateCw className="h-3 w-3" /> Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  detail,
  action,
}: {
  icon?: ReactNode;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 rounded-lg border border-dashed border-line px-5 py-10 text-center">
      {icon ? <div className="text-slate-600">{icon}</div> : null}
      <div className="text-sm font-medium text-slate-300">{title}</div>
      {detail ? <p className="max-w-sm text-xs leading-relaxed text-fog">{detail}</p> : null}
      {action}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label mb-1.5 block">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[10px] leading-relaxed text-slate-500">{hint}</span> : null}
    </label>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, copy] = useCopy();
  return (
    <button
      onClick={() => copy(text)}
      className="inline-flex items-center gap-1.5 rounded border border-line bg-ink-900 px-2 py-1 text-[10px] font-medium text-fog transition hover:border-slate-600 hover:text-slate-200"
    >
      {copied ? <Check className="h-3 w-3 text-mint" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : label}
    </button>
  );
}

export function ScoreRing({
  score,
  size = 116,
  caption,
}: {
  score: number | null | undefined;
  size?: number;
  caption?: string;
}) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const tone = scoreTone(score);
  const stroke =
    tone === "mint" ? "#38e3ab" : tone === "amber" ? "#f5b84c" : tone === "coral" ? "#ff7272" : "#3a4a58";
  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#16232f"
          strokeWidth="7"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 500ms ease, stroke 300ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pb-1">
        <div className="font-mono text-2xl font-semibold tabular-nums text-white">
          {score === null || score === undefined ? "—" : value.toFixed(1)}
        </div>
        <div className="text-[9px] uppercase tracking-[0.18em] text-fog">Score</div>
      </div>
      {caption ? <div className="mt-1 text-[10px] text-fog">{caption}</div> : null}
    </div>
  );
}

const COMPONENT_LABELS: Record<string, { label: string; weight: string }> = {
  completion: { label: "Completion", weight: "50" },
  on_time: { label: "On time", weight: "20" },
  fuel_efficiency: { label: "Efficiency", weight: "15" },
  compliance: { label: "Compliance", weight: "10" },
  reliability: { label: "Reliability", weight: "5" },
  throughput: { label: "Throughput", weight: "45" },
  wait: { label: "Wait time", weight: "30" },
  congestion: { label: "Congestion", weight: "15" },
};

export function ScoreComponents({ components }: { components: Record<string, number> }) {
  return (
    <div className="space-y-1.5">
      {Object.entries(components).map(([key, value]) => {
        const meta = COMPONENT_LABELS[key] || { label: key, weight: "" };
        const width = Math.max(2, Math.min(100, value * 100));
        const tone = value >= 0.75 ? "bg-mint" : value >= 0.4 ? "bg-amber" : "bg-coral";
        return (
          <div key={key} className="flex items-center gap-2 text-[10px]">
            <span className="w-[78px] shrink-0 text-fog">{meta.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-950">
              <div className={`h-full rounded-full ${tone}`} style={{ width: `${width}%` }} />
            </div>
            <span className="w-9 text-right font-mono tabular-nums text-slate-400">
              {pct(value, 0)}
            </span>
            <span className="w-6 text-right text-[9px] text-slate-600">{meta.weight ? `${meta.weight}%` : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-0.5 text-mint hover:underline"
    >
      {children}
      <ArrowUpRight className="h-3 w-3" />
    </a>
  );
}

export function Toast({
  message,
  tone = "mint",
  onClose,
}: {
  message: string;
  tone?: "mint" | "coral" | "amber";
  onClose: () => void;
}) {
  const border = tone === "coral" ? "border-coral/40" : tone === "amber" ? "border-amber/40" : "border-mint/40";
  const text = tone === "coral" ? "text-coral" : tone === "amber" ? "text-amber" : "text-mint";
  return (
    <div
      className={`fixed bottom-5 right-5 z-50 flex max-w-sm items-start gap-2 rounded-lg border ${border} bg-ink-850 px-3.5 py-2.5 text-xs ${text} shadow-panel animate-fade-up`}
      role="status"
    >
      <span className="leading-relaxed">{message}</span>
      <button onClick={onClose} className="ml-2 text-fog hover:text-white" aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}