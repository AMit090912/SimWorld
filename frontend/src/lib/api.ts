import type {
  AgentCatalogue,
  AgentSpec,
  AgentTestResult,
  Evaluation,
  Experiment,
  LLMStatus,
  MetricDefinition,
  ReplayPayload,
  RunPayload,
  RunSummary,
  Scenario,
} from "./types";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new ApiError("Cannot reach the SimWorld API. Is the backend running?", 0);
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as Record<string, unknown>).detail)
        : `Request failed with HTTP ${response.status}.`;
    const code =
      body && typeof body === "object" && "code" in body
        ? String((body as Record<string, unknown>).code)
        : undefined;
    throw new ApiError(detail, response.status, code);
  }
  return body as T;
}

export const api = {
  health: () => request<{ ok: boolean; version: string; runs: number }>("/health"),
  stats: () => request<{ runs: number; experiments: number; scenarios: number }>("/stats"),

  scenarios: () => request<{ scenarios: Scenario[] }>("/scenarios"),
  scenario: (id: string) => request<Scenario>(`/scenarios/${id}`),
  preview: (id: string, seed = 7) =>
    request<{ scenario: Scenario; snapshot: import("./types").SimState }>(
      `/scenarios/${id}/preview?seed=${seed}`,
    ),
  metrics: () => request<{ metrics: MetricDefinition[] }>("/metrics"),

  agents: () => request<AgentCatalogue>("/agents"),
  llmStatus: () => request<LLMStatus>("/agents/llm/status"),
  testAgent: (agent: AgentSpec, scenario_id: string) =>
    request<AgentTestResult>("/agents/test", {
      method: "POST",
      body: JSON.stringify({ agent, scenario_id }),
    }),

  createRun: (payload: {
    scenario_id: string;
    seed: number;
    options: Record<string, string>;
    agent: AgentSpec;
  }) =>
    request<RunPayload>("/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listRuns: (limit = 40, offset = 0, scenarioId?: string) =>
    request<{ runs: RunSummary[]; total: number }>(
      `/runs?limit=${limit}&offset=${offset}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`,
    ),
  getRun: (id: string) => request<RunPayload>(`/runs/${id}`),
  startRun: (id: string, delay_ms: number) =>
    request<RunPayload>(`/runs/${id}/start`, {
      method: "POST",
      body: JSON.stringify({ delay_ms }),
    }),
  pauseRun: (id: string) =>
    request<RunPayload>(`/runs/${id}/pause`, { method: "POST" }),
  stepRun: (id: string) =>
    request<RunPayload>(`/runs/${id}/step`, { method: "POST" }),
  resetRun: (id: string) =>
    request<RunPayload>(`/runs/${id}/reset`, { method: "POST" }),
  disrupt: (id: string, payload: { type: string; edges?: string[] }) =>
    request<RunPayload>(`/runs/${id}/disrupt`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  replay: (id: string) => request<ReplayPayload>(`/runs/${id}/replay`),

  createExperiment: (payload: {
    scenario_id: string;
    seeds: number[];
    agents: AgentSpec[];
    options: Record<string, string>;
  }) =>
    request<Experiment>("/experiments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listExperiments: (limit = 20) =>
    request<{ experiments: Experiment[] }>(`/experiments?limit=${limit}`),
  getExperiment: (id: string) => request<Experiment>(`/experiments/${id}`),
};

export function evaluationScore(evaluation: Evaluation | null | undefined): number | null {
  return evaluation && typeof evaluation.score === "number" ? evaluation.score : null;
}