import {
  ArrowRight,
  Beaker,
  CheckCircle2,
  GitCompareArrows,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { formatMetric, num, pct, relativeTime } from "../lib/format";
import type { AggregateBlock, Experiment, RunSummary, Scenario } from "../lib/types";
import { useApiData, useInterval } from "../hooks/useApiData";
import { EmptyState, ErrorBanner, Field, PageHeader, Panel, Spinner } from "../components/ui";
import { StatusPill } from "../components/sim";

const PALETTE = ["#38e3ab", "#72a9ff", "#f5b84c"];

function meanOf(block: AggregateBlock | undefined, key: string): number | null {
  const entry = block?.metrics?.[key];
  return entry ? entry.mean : null;
}

function ScoreBars({ items }: { items: { label: string; value: number }[] }) {
  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-[10px]">
            <span className="truncate text-slate-300">{item.label}</span>
            <span className="font-mono text-slate-400">{item.value.toFixed(1)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-ink-950">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${Math.max(1, Math.min(100, item.value))}%`, background: PALETTE[index % PALETTE.length] }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Compare() {
  const [params] = useSearchParams();
  const preselected = params.get("run");
  const [tab, setTab] = useState<"experiments" | "runs">(preselected ? "runs" : "experiments");
  const { data: scenarioData } = useApiData(() => api.scenarios(), []);
  const scenarios = scenarioData?.scenarios ?? [];
  const [scenarioId, setScenarioId] = useState("city-logistics/standard");
  const scenario: Scenario | undefined = scenarios.find((item) => item.id === scenarioId) || scenarios[0];
  const [options, setOptions] = useState<Record<string, string>>({});
  const [selectedAgents, setSelectedAgents] = useState<string[]>(["city-baseline", "city-greedy"]);
  const [seeds, setSeeds] = useState("7, 11, 23");
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: recent, reload: reloadRecent } = useApiData(() => api.listExperiments(12), []);
  const { data: runData, loading: runsLoading } = useApiData(() => api.listRuns(80), []);
  const [selectedRuns, setSelectedRuns] = useState<string[]>(preselected ? [preselected] : []);

  useEffect(() => {
    if (scenario) {
      setOptions({ ...scenario.default_options });
      const agents = scenario.kind === "city_logistics" ? ["city-baseline", "city-greedy"] : ["traffic-adaptive", "traffic-fixed"];
      setSelectedAgents(agents);
      setExperiment(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.id]);

  useInterval(
    () => {
      if (!experiment || experiment.status !== "running") return;
      api
        .getExperiment(experiment.id)
        .then((next) => {
          setExperiment(next);
          if (next.status === "finished") reloadRecent();
        })
        .catch((err: Error) => setError(err.message));
    },
    experiment?.status === "running" ? 1000 : null,
  );

  const runs = (runData?.runs ?? []).filter((run) => run.status === "finished" || run.status === "failed");
  const selected = selectedRuns
    .map((id) => runs.find((run) => run.id === id))
    .filter(Boolean) as RunSummary[];
  const mixedScenarios = new Set(selected.map((run) => run.scenario_id)).size > 1;
  const isCity = selected.length > 0 && selected.every((run) => run.kind === "city_logistics");
  const comparisonRows: Array<[string, (run: RunSummary) => string]> = [
    ["Scenario", (run) => run.scenario_id],
    ["Agent", (run) => run.agent.label],
    ["Status", (run) => run.status],
    ["Score", (run) => (run.score === null ? "?" : run.score.toFixed(1))],
    ["Completion", (run) => formatMetric("completion_rate", run.metrics?.completion_rate)],
    ["On time", (run) => formatMetric("on_time_rate", run.metrics?.on_time_rate)],
    ...(isCity
      ? ([
          ["Fuel", (run: RunSummary) => formatMetric("fuel_consumed_l", run.metrics?.fuel_consumed_l)],
          ["Distance", (run: RunSummary) => formatMetric("distance_km", run.metrics?.distance_km)],
        ] as Array<[string, (run: RunSummary) => string]>)
      : ([
          ["Throughput", (run: RunSummary) => formatMetric("throughput_rate", run.metrics?.throughput_rate)],
          ["Avg wait", (run: RunSummary) => formatMetric("avg_wait_ticks", run.metrics?.avg_wait_ticks)],
          ["Congestion", (run: RunSummary) => formatMetric("avg_queue_length", run.metrics?.avg_queue_length)],
          ["Rule violations", (run: RunSummary) => formatMetric("rule_violations", run.metrics?.rule_violations)],
        ] as Array<[string, (run: RunSummary) => string]>)),
    ["Invalid actions", (run) => formatMetric("invalid_actions", run.metrics?.invalid_actions)],
    ["Agent latency", (run) => formatMetric("agent_latency_ms", run.metrics?.agent_latency_ms)],
    ["Recovery", (run) => formatMetric("recovery_steps", run.metrics?.recovery_steps)],
    ["Steps", (run) => String(run.steps)],
    ["Created", (run) => relativeTime(run.created_at)],
  ];

  async function launchExperiment() {
    if (!scenario) return;
    setCreating(true);
    setError(null);
    try {
      const parsedSeeds = seeds
        .split(/[,\s]+/)
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value) && value >= 0);
      if (!parsedSeeds.length) throw new Error("Enter at least one non-negative integer seed.");
      const result = await api.createExperiment({
        scenario_id: scenario.id,
        seeds: parsedSeeds,
        agents: selectedAgents.map((id) => ({ type: "builtin", id })),
        options,
      });
      setExperiment(result);
      reloadRecent();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function loadExperiment(id: string) {
    setError(null);
    try {
      const result = await api.getExperiment(id);
      setExperiment(result);
      setScenarioId(result.scenario_id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function toggleRun(id: string) {
    setSelectedRuns((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 3) return [...current.slice(1), id];
      return [...current, id];
    });
  }

  const compatibleAgents = useMemo(() => {
    const kind = scenario?.kind ?? "city_logistics";
    return kind === "city_logistics"
      ? [
          { id: "city-baseline", label: "Disruption-aware" },
          { id: "city-greedy", label: "Greedy nearest" },
          { id: "city-blind", label: "Blind static" },
        ]
      : [
          { id: "traffic-adaptive", label: "Adaptive pressure" },
          { id: "traffic-fixed", label: "Fixed cycle" },
        ];
  }, [scenario?.kind]);

  return (
    <div>
      <PageHeader
        eyebrow="Comparison"
        title="Same conditions. Different strategies."
        description="Launch a reproducible experiment across seeds and agents, or line up completed runs. The aggregate is computed from each run's recorded metrics — never from agent claims."
        actions={
          <div className="flex rounded-md border border-line bg-ink-950/60 p-0.5">
            {(
              [
                ["experiments", "Experiments", Beaker],
                ["runs", "Runs", GitCompareArrows],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                onClick={() => setTab(value)}
                className={`flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[10px] font-medium transition ${
                  tab === value ? "bg-ink-750 text-white" : "text-fog hover:text-slate-200"
                }`}
              >
                <Icon className="h-3 w-3" />
                {label}
              </button>
            ))}
          </div>
        }
      />

      {error ? <div className="mb-3"><ErrorBanner message={error} onRetry={() => setError(null)} /></div> : null}

      {tab === "experiments" ? (
        <div className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]">
          <div className="space-y-3">
            <Panel title="Experiment setup">
              <div className="space-y-3">
                <Field label="Scenario">
                  <select className="select" value={scenario?.id} onChange={(event) => setScenarioId(event.target.value)}>
                    {scenarios.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </Field>

                <div>
                  <div className="label mb-1.5">Agents</div>
                  <div className="space-y-1">
                    {compatibleAgents.map((agent) => {
                      const checked = selectedAgents.includes(agent.id);
                      return (
                        <label
                          key={agent.id}
                          className={`flex cursor-pointer items-center gap-2 rounded border px-2 py-1.5 text-[10px] transition ${
                            checked ? "border-mint/30 bg-mint/[0.05] text-slate-200" : "border-line/60 text-fog hover:border-slate-600"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              setSelectedAgents((current) =>
                                checked ? current.filter((id) => id !== agent.id) : [...current, agent.id],
                              )
                            }
                            className="accent-mint"
                          />
                          <span className="flex-1">{agent.label}</span>
                          <span className="font-mono text-[9px] text-slate-600">{agent.id}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <Field label="Seeds" hint="Comma-separated. Each seed is a full reproducible run per agent.">
                  <input className="input font-mono" value={seeds} onChange={(event) => setSeeds(event.target.value)} />
                </Field>

                {scenario?.variations.map((variation) => (
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

                <div className="rounded border border-line/60 bg-ink-900/40 px-2 py-1.5 text-[9px] leading-relaxed text-slate-500">
                  {selectedAgents.length} agent(s) × {seeds.split(/[,\s]+/).filter(Boolean).length} seed(s) ={" "}
                  {selectedAgents.length * seeds.split(/[,\s]+/).filter(Boolean).length} runs
                </div>

                <button
                  className="btn-primary w-full"
                  onClick={launchExperiment}
                  disabled={creating || !scenario || selectedAgents.length === 0}
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  Launch experiment
                </button>
              </div>
            </Panel>

            <Panel title="Recent experiments">
              {recent?.experiments.length ? (
                <div className="space-y-1">
                  {recent.experiments.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => loadExperiment(item.id)}
                      className={`flex w-full items-center gap-2 rounded border px-2 py-1.5 text-left transition ${
                        experiment?.id === item.id ? "border-mint/30 bg-mint/[0.05]" : "border-line/50 hover:border-slate-600"
                      }`}
                    >
                      <RefreshCw className={`h-3 w-3 ${item.status === "running" ? "animate-spin text-sky" : "text-slate-600"}`} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[10px] text-slate-300">{item.scenario_id}</div>
                        <div className="text-[9px] text-slate-600">
                          {item.config.agents.length} agents · seeds {item.config.seeds.join(", ")}
                        </div>
                      </div>
                      <span className={`chip !text-[9px] ${item.status === "finished" ? "chip-mint" : item.status === "failed" ? "chip-coral" : "chip-sky"}`}>
                        {item.status}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-slate-600">No experiments yet.</div>
              )}
            </Panel>
          </div>

          <div className="space-y-3">
            {experiment ? (
              <>
                <Panel
                  title={
                    <span className="flex items-center gap-2">
                      Experiment <span className="font-mono text-[10px] text-mint">{experiment.id}</span>
                    </span>
                  }
                  action={<StatusPill status={experiment.status} />}
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="text-[10px] text-fog">
                      {experiment.completed_runs} / {experiment.total_runs} runs complete
                    </div>
                    <div className="h-1.5 min-w-[140px] flex-1 overflow-hidden rounded-full bg-ink-950">
                      <div
                        className="h-full rounded-full bg-mint transition-all"
                        style={{ width: `${(experiment.completed_runs / Math.max(1, experiment.total_runs)) * 100}%` }}
                      />
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {experiment.config.seeds.map((seed) => (
                        <span key={seed} className="chip-mint !text-[9px]">seed {seed}</span>
                      ))}
                    </div>
                  </div>
                  {experiment.status === "failed" ? <div className="mt-2 text-[10px] text-coral">{experiment.error}</div> : null}
                </Panel>

                {experiment.aggregate ? (
                  <>
                    <Panel title="Aggregate by agent" action={<span className="text-[9px] text-slate-600">mean across seeds</span>}>
                      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
                        <ScoreBars
                          items={Object.entries(experiment.aggregate.by_agent).map(([label, block]) => ({
                            label,
                            value: block.scores.mean,
                          }))}
                        />
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse">
                            <thead>
                              <tr>
                                <th className="table-head">Agent</th>
                                <th className="table-head">Score</th>
                                <th className="table-head">Completion</th>
                                <th className="table-head">On time</th>
                                <th className="table-head">Invalid</th>
                                <th className="table-head">Latency</th>
                                <th className="table-head">Runs</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(experiment.aggregate.by_agent).map(([label, block]) => (
                                <tr key={label}>
                                  <td className="table-cell text-[11px] text-slate-300">{label}</td>
                                  <td className="table-cell font-mono text-mint">{block.scores.mean.toFixed(1)} <span className="text-[9px] text-slate-600">±{block.scores.std.toFixed(1)}</span></td>
                                  <td className="table-cell font-mono">{meanOf(block, "completion_rate") === null ? "—" : pct(meanOf(block, "completion_rate"), 0)}</td>
                                  <td className="table-cell font-mono">{meanOf(block, "on_time_rate") === null ? "—" : pct(meanOf(block, "on_time_rate"), 0)}</td>
                                  <td className="table-cell font-mono">{meanOf(block, "invalid_actions") === null ? "—" : num(meanOf(block, "invalid_actions"), 1)}</td>
                                  <td className="table-cell font-mono">{meanOf(block, "agent_latency_ms") === null ? "—" : `${num(meanOf(block, "agent_latency_ms"), 0)} ms`}</td>
                                  <td className="table-cell font-mono">{block.runs}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </Panel>

                    <Panel title="Per-run evidence" action={<span className="text-[9px] text-slate-600">click a row to open replay</span>} bodyClassName="p-0">
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[760px] border-collapse">
                          <thead>
                            <tr>
                              <th className="table-head">Run</th>
                              <th className="table-head">Agent</th>
                              <th className="table-head">Seed</th>
                              <th className="table-head">Status</th>
                              <th className="table-head">Score</th>
                              <th className="table-head">Primary</th>
                              <th className="table-head">Steps</th>
                              <th className="table-head" />
                            </tr>
                          </thead>
                          <tbody>
                            {experiment.aggregate.runs.map((run) => (
                              <tr key={run.id} className="hover:bg-white/[0.025]">
                                <td className="table-cell font-mono text-[10px] text-mint">{run.id}</td>
                                <td className="table-cell text-[10px] text-slate-300">{run.agent}</td>
                                <td className="table-cell font-mono text-[10px]">{run.seed}</td>
                                <td className="table-cell"><StatusPill status={run.status} /></td>
                                <td className="table-cell font-mono text-sm text-slate-200">{run.score === null ? "—" : run.score.toFixed(1)}</td>
                                <td className="table-cell text-[10px] text-fog">
                                  {run.metrics
                                    ? run.metrics.packages_total !== undefined
                                      ? `${run.metrics.packages_delivered}/${run.metrics.packages_total} delivered`
                                      : `${pct(Number(run.metrics.throughput_rate), 0)} throughput`
                                    : "—"}
                                </td>
                                <td className="table-cell font-mono text-[10px]">{String(run.metrics?.steps ?? "n/a")}</td>
                                <td className="table-cell text-right">
                                  <Link to={`/runs/${run.id}`} className="inline-flex items-center gap-1 text-[10px] text-fog hover:text-mint">
                                    replay <ArrowRight className="h-3 w-3" />
                                  </Link>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </Panel>
                  </>
                ) : (
                  <Panel>
                    <div className="flex items-center gap-2">
                      <Spinner label="Running experiment" />
                      <span className="text-[10px] text-fog">Results appear as runs finish.</span>
                    </div>
                  </Panel>
                )}
              </>
            ) : (
              <Panel>
                <EmptyState
                  icon={<Beaker className="h-6 w-6" />}
                  title="No experiment loaded"
                  detail="Choose a scenario, at least two agents, and a few seeds to see how strategies diverge under identical conditions."
                />
              </Panel>
            )}
          </div>
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
          <Panel title="Select completed runs" bodyClassName="p-2">
            {runsLoading ? <Spinner label="Loading runs" /> : null}
            <div className="max-h-[620px] space-y-1 overflow-y-auto">
              {runs.map((run) => {
                const active = selectedRuns.includes(run.id);
                return (
                  <button
                    key={run.id}
                    onClick={() => toggleRun(run.id)}
                    className={`flex w-full items-center gap-2 rounded border px-2 py-1.5 text-left transition ${
                      active ? "border-mint/30 bg-mint/[0.05]" : "border-line/50 hover:border-slate-600"
                    }`}
                  >
                    <span className={`flex h-4 w-4 items-center justify-center rounded border ${active ? "border-mint bg-mint text-ink-950" : "border-line"}`}>
                      {active ? <CheckCircle2 className="h-3 w-3" /> : null}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[10px] text-slate-300">{run.id}</span>
                        <span className="text-[9px] text-slate-600">seed {run.seed}</span>
                      </div>
                      <div className="truncate text-[9px] text-fog">{run.agent.label}</div>
                    </div>
                    <span className="font-mono text-xs text-slate-300">{run.score === null ? "—" : run.score.toFixed(1)}</span>
                  </button>
                );
              })}
              {!runsLoading && runs.length === 0 ? <div className="px-2 py-4 text-[10px] text-slate-600">No completed runs yet.</div> : null}
            </div>
            <div className="mt-2 flex items-center justify-between border-t border-line/60 px-1 pt-2 text-[9px] text-slate-600">
              <span>{selectedRuns.length}/3 selected</span>
              <button className="inline-flex items-center gap-1 hover:text-slate-300" onClick={() => setSelectedRuns([])}>
                <X className="h-3 w-3" /> clear
              </button>
            </div>
          </Panel>

          <div className="space-y-3">
            {mixedScenarios ? (
              <ErrorBanner message="These runs use different scenarios. Metric differences may come from the environment, not the agent." />
            ) : null}
            {selected.length ? (
              <>
                <Panel title="Score comparison">
                  <ScoreBars
                    items={selected.map((run) => ({
                      label: `${run.agent.label} · seed ${run.seed}`,
                      value: Number(run.score ?? 0),
                    }))}
                  />
                </Panel>

                <Panel title="Metric matrix" bodyClassName="p-0">
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[720px] border-collapse">
                      <thead>
                        <tr>
                          <th className="table-head">Metric</th>
                          {selected.map((run, index) => (
                            <th key={run.id} className="table-head" style={{ color: PALETTE[index % PALETTE.length] }}>
                              {run.id} · seed {run.seed}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {comparisonRows.map(([label, getter]) => (
                          <tr key={label as string}>
                            <td className="table-cell text-[10px] uppercase tracking-[0.08em] text-fog">{label}</td>
                            {selected.map((run) => (
                              <td key={run.id} className="table-cell font-mono text-[10px] text-slate-300">
                                {getter(run)}
                              </td>
                            ))}
                          </tr>
                        ))}
                        <tr>
                          <td className="table-cell" />
                          {selected.map((run) => (
                            <td key={run.id} className="table-cell">
                              <Link to={`/runs/${run.id}`} className="inline-flex items-center gap-1 text-[10px] text-mint hover:underline">
                                open replay <ArrowRight className="h-3 w-3" />
                              </Link>
                            </td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <div className="grid gap-3 md:grid-cols-2">
                  {selected.map((run, index) => (
                    <Panel
                      key={run.id}
                      title={
                        <span className="flex items-center gap-1.5" style={{ color: PALETTE[index % PALETTE.length] }}>
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: PALETTE[index % PALETTE.length] }} />
                          {run.id}
                        </span>
                      }
                      action={<StatusPill status={run.status} />}
                    >
                      <div className="space-y-1 text-[10px]">
                        <div className="flex justify-between gap-2"><span className="text-fog">Agent</span><span className="text-slate-300">{run.agent.label}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-fog">Seed</span><span className="font-mono text-slate-300">{run.seed}</span></div>
                        <div className="flex justify-between gap-2"><span className="text-fog">Terminal</span><span className="text-slate-300">{run.terminal_reason?.replace(/_/g, " ") || "—"}</span></div>
                        {run.metrics?.failures?.slice(0, 2).map((failure) => (
                          <div key={failure} className="pt-1 text-[9px] leading-relaxed text-amber/80">{failure}</div>
                        ))}
                      </div>
                    </Panel>
                  ))}
                </div>
              </>
            ) : (
              <Panel>
                <EmptyState
                  icon={<Plus className="h-6 w-6" />}
                  title="Pick up to three runs"
                  detail="Choose completed runs from the left. Same scenario and seed comparisons are the most defensible."
                />
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}