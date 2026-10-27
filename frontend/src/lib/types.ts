export type Kind = "city_logistics" | "traffic_control";

export interface VariationOption {
  value: string;
  label: string;
}

export interface Variation {
  key: string;
  label: string;
  default: string;
  options: VariationOption[];
}

export interface Scenario {
  id: string;
  version: number;
  kind: Kind;
  name: string;
  tagline: string;
  description: string;
  difficulty: "Calm" | "Tight" | "Hard" | "Brutal" | string;
  objectives: string[];
  constraints: string[];
  variations: Variation[];
  default_options: Record<string, string>;
  metrics: string[];
  horizon_steps: number;
  default_seeds: number[];
}

export interface BuiltinAgent {
  id: string;
  label: string;
  kind: "builtin";
  environments: Kind[];
  description: string;
  traits: string[];
}

export interface AgentModeInfo {
  type: "external" | "llm";
  label: string;
  description?: string;
  protocol?: string;
  loopback_allowed?: boolean;
  model?: string;
  base_url?: string;
  provider?: string;
  api_key_configured?: boolean;
  configured?: boolean;
  probe?: ProbeResult;
}

export interface AgentCatalogue {
  builtin: BuiltinAgent[];
  modes: AgentModeInfo[];
}

export interface ProbeResult {
  available: boolean;
  error?: string;
  model?: string;
  base_url?: string;
  models?: string[];
  model_listed?: boolean | null;
}

export interface LLMStatus {
  provider: string;
  model: string;
  base_url: string;
  api_key_configured: boolean;
  configured: boolean;
  probe: ProbeResult;
}

export interface AgentSpec {
  type: "builtin" | "external" | "llm";
  id?: string | null;
  url?: string | null;
  timeout_ms?: number | null;
  auth_env?: string | null;
  model?: string | null;
  base_url?: string | null;
  provider?: string | null;
  temperature?: number | null;
  label?: string | null;
}

export interface AgentDescriptor {
  type: string;
  id: string;
  label: string;
  config: Record<string, unknown>;
  environment: Kind;
}

export interface SimEvent {
  seq: number;
  step: number;
  time_min: number;
  type: string;
  severity: "info" | "warning" | "critical" | string;
  message: string;
  payload: Record<string, unknown>;
  source: "plan" | "live" | string;
}

export interface SimPackage {
  id: string;
  origin: string;
  dest: string;
  dest_label: string;
  deadline_min: number;
  weight_kg: number;
  priority: string;
  status: "at_depot" | "in_transit" | "delivered" | string;
  delivered_at_min: number | null;
  late: boolean;
}

export interface SimEdge {
  id: string;
  a: string;
  b: string;
  open: boolean;
  km: number;
}

export interface IntersectionState {
  id: string;
  phase: "NS" | "EW";
  last_switch: number;
  queues: Record<"N" | "S" | "E" | "W", number>;
  oldest_wait_ticks: number;
}

export interface Incident {
  intersection: string;
  approach: "N" | "S" | "E" | "W";
  until_step: number;
}

export interface CityState {
  kind: "city_logistics";
  scenario_id: string;
  seed: number;
  step: number;
  time_min: number;
  horizon_steps: number;
  step_minutes: number;
  status: "running" | "finished" | "failed";
  terminal_reason: string | null;
  grid: number;
  depot: string;
  edge_km: number;
  fog_radius: number | null;
  options: Record<string, string>;
  edges: SimEdge[];
  vehicle: {
    node: string;
    fuel_l: number;
    fuel_capacity_l: number;
    capacity: number;
    cargo: string[];
    distance_km: number;
  };
  packages: SimPackage[];
  stations: { node: string; stock_l: number }[];
  events: SimEvent[];
  metrics: Record<string, number | Record<string, number>>;
  state_hash: string;
}

export interface TrafficState {
  kind: "traffic_control";
  scenario_id: string;
  seed: number;
  step: number;
  time_min: number;
  horizon_steps: number;
  step_minutes: number;
  status: "running" | "finished" | "failed";
  terminal_reason: string | null;
  grid: number;
  min_green: number;
  options: Record<string, string>;
  intersections: IntersectionState[];
  incidents: Incident[];
  events: SimEvent[];
  metrics: Record<string, number | Record<string, number>>;
  state_hash: string;
}

export type SimState = CityState | TrafficState;

export interface Evaluation extends Record<string, unknown> {
  score: number;
  score_components: Record<string, number>;
  failures: string[];
  agent_latency_ms: number;
  agent_latency_p95_ms: number;
  agent_errors: number;
  agent_fallbacks: number;
  invalid_actions: number;
  recovery_steps: number | null;
  post_disruption_deliveries: number | null;
  disruption_count: number;
}

export interface RunSummary {
  id: string;
  created_at: string;
  scenario_id: string;
  scenario_version: number;
  kind: Kind;
  seed: number;
  options: Record<string, string>;
  agent: AgentDescriptor;
  status: "ready" | "running" | "paused" | "finished" | "failed";
  terminal_reason: string | null;
  steps: number;
  score: number | null;
  metrics: Evaluation | null;
  config: Record<string, unknown>;
  error: string | null;
  duration_ms: number | null;
}

export interface LastStep {
  ok: boolean;
  code: string;
  reason: string;
  latency_ms: number;
  agent_error: string | null;
  action: Record<string, unknown>;
  fallback_used?: boolean;
  reasoning?: string | null;
  step?: number;
  message?: string;
}

export interface RunPayload {
  run: RunSummary;
  state: SimState;
  evaluation: Evaluation;
  agent: AgentDescriptor;
  last_step?: LastStep;
  injected?: SimEvent;
}

export interface DecisionRecord {
  reasoning: string | null;
  latency_ms: number;
  agent_latency_ms: number;
  fallback_used: boolean;
  error: string | null;
  raw: string | null;
  result: Record<string, unknown>;
  ok: boolean;
  code: string;
}

export interface ReplayStep {
  step: number;
  time_min: number;
  action: Record<string, unknown> | null;
  decision: DecisionRecord | null;
  valid: boolean;
  reason: string;
  latency_ms: number;
  state: SimState;
  metrics: Record<string, unknown>;
}

export interface ReplayPayload {
  run: Omit<RunSummary, "metrics"> & { metrics: Evaluation | null };
  agent: AgentDescriptor;
  initial_state: SimState;
  initial_snapshot: SimState;
  steps: ReplayStep[];
  evaluation: Evaluation;
  step_count: number;
}

export interface ExperimentRunSummary {
  id: string;
  seed: number;
  agent: string;
  status: string;
  score: number | null;
  metrics: Evaluation | null;
  terminal_reason: string | null;
}

export interface AggregateBlock {
  runs: number;
  metrics: Record<string, { mean: number; std: number; min: number; max: number }>;
  scores: { mean: number; std: number; min: number; max: number };
}

export interface Experiment {
  id: string;
  created_at: string;
  scenario_id: string;
  kind: Kind;
  config: { seeds: number[]; agents: AgentSpec[]; options: Record<string, string> };
  status: "running" | "finished" | "failed";
  aggregate: {
    overall: AggregateBlock;
    by_agent: Record<string, AggregateBlock>;
    runs: ExperimentRunSummary[];
  } | null;
  error: string | null;
  total_runs: number;
  completed_runs: number;
  runs?: RunSummary[];
}

export interface MetricDefinition {
  key: string;
  label: string;
  unit: string;
  direction: "higher" | "lower";
  description: string;
  weight: string;
}

export interface AgentTestResult {
  ok: boolean;
  code?: string;
  error?: string;
  latency_ms: number;
  agent_latency_ms?: number;
  action?: Record<string, unknown>;
  action_was_offered?: boolean;
  engine_accepted?: boolean;
  engine_result?: string;
  reasoning?: string | null;
  fallback_used?: boolean;
  protocol: string;
}