export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return `${Math.round(value)}`;
}

export function clock(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.round(totalMinutes % 60);
  const h = String(8 + hours).padStart(2, "0");
  const m = String(minutes).padStart(2, "0");
  return `${h}:${m}`;
}

export function duration(ms: number | null | undefined): string {
  if (!ms) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  if (diff < 45_000) return "just now";
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
  return `${Math.round(diff / 86_400_000)}d ago`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function scoreTone(score: number | null | undefined): "mint" | "amber" | "coral" | "fog" {
  if (score === null || score === undefined) return "fog";
  if (score >= 75) return "mint";
  if (score >= 45) return "amber";
  return "coral";
}

export function statusTone(status: string): "mint" | "amber" | "coral" | "sky" | "fog" {
  switch (status) {
    case "running":
    case "finished":
      return status === "running" ? "sky" : "mint";
    case "paused":
    case "ready":
      return "amber";
    case "failed":
      return "coral";
    default:
      return "fog";
  }
}

export function nodeXY(node: string): [number, number] {
  const [x, y] = node.split(",").map((part) => Number(part));
  return [x, y];
}

export function nodeLabel(node: string): string {
  const [x, y] = nodeXY(node);
  return `Block ${String.fromCharCode(65 + x)}${y + 1}`;
}

export function shortNode(node: string): string {
  return node.replace(",", "·");
}

export function formatMetric(key: string, value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return String(value ?? "—");
  switch (key) {
    case "completion_rate":
    case "on_time_rate":
    case "on_time_rate_delivered":
    case "throughput_rate":
    case "agent_error_rate":
      return pct(value, 1);
    case "fuel_consumed_l":
    case "fuel_refueled_l":
    case "fuel_remaining_l":
      return `${num(value, 2)} L`;
    case "distance_km":
      return `${num(value, 2)} km`;
    case "agent_latency_ms":
    case "agent_latency_p95_ms":
      return `${num(value, 0)} ms`;
    case "avg_wait_ticks":
      return `${num(value, 1)} ticks`;
    case "avg_queue_length":
      return `${num(value, 1)} veh`;
    case "score":
      return num(value, 1);
    case "sim_minutes":
      return `${num(value, 0)} min`;
    default:
      return Number.isInteger(value) ? String(value) : num(value, 2);
  }
}