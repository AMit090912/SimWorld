import { ArrowRight, GitCompareArrows, History, Inbox, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { num, pct, relativeTime, statusTone } from "../lib/format";
import type { RunSummary } from "../lib/types";
import { useApiData, useInterval } from "../hooks/useApiData";
import { EmptyState, ErrorBanner, PageHeader, Panel, Spinner } from "../components/ui";
import { StatusPill } from "../components/sim";

function summary(run: RunSummary): string {
  if (!run.metrics) return "—";
  if (run.kind === "city_logistics") {
    return `${run.metrics.packages_delivered}/${run.metrics.packages_total} delivered · ${num(
      Number(run.metrics.fuel_consumed_l),
      1,
    )} L`;
  }
  return `${pct(Number(run.metrics.throughput_rate), 0)} cleared · ${num(
    Number(run.metrics.avg_wait_ticks),
    1,
  )} wait`;
}

export default function Runs() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const scenarioFilter = params.get("scenario") || "";
  const [query, setQuery] = useState("");
  const { data, error, loading, reload } = useApiData(
    () => api.listRuns(80, 0, scenarioFilter || undefined),
    [scenarioFilter],
  );
  const { data: scenarioData } = useApiData(() => api.scenarios(), []);
  const scenarios = scenarioData?.scenarios ?? [];
  const scenarioNames = useMemo(
    () => Object.fromEntries(scenarios.map((scenario) => [scenario.id, scenario.name])),
    [scenarios],
  );

  useInterval(reload, 6000);

  const runs = (data?.runs ?? []).filter((run) => {
    if (!query.trim()) return true;
    const haystack = `${run.id} ${run.scenario_id} ${run.agent.label} ${run.seed}`.toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });
  const scored = (data?.runs ?? []).filter((run) => typeof run.score === "number");
  const average = scored.length
    ? scored.reduce((sum, run) => sum + Number(run.score), 0) / scored.length
    : null;

  return (
    <div>
      <PageHeader
        eyebrow="Run history"
        title="Every experiment leaves evidence"
        description="Runs store their scenario version, seed, agent identity, action history, transitions, metrics, and state hashes. Open a run to replay exactly what happened."
        actions={
          <Link to="/compare" className="btn-ghost">
            <GitCompareArrows className="h-3.5 w-3.5" /> Compare runs
          </Link>
        }
      />

      {error ? <ErrorBanner message={error} onRetry={reload} /> : null}

      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <div className="panel-flat px-3 py-2.5">
          <div className="label">Stored runs</div>
          <div className="stat-value mt-1">{data?.total ?? "—"}</div>
        </div>
        <div className="panel-flat px-3 py-2.5">
          <div className="label">Mean score</div>
          <div className="stat-value mt-1">{average === null ? "—" : average.toFixed(1)}</div>
        </div>
        <div className="panel-flat px-3 py-2.5">
          <div className="label">Failing runs</div>
          <div className="stat-value mt-1 text-coral">
            {(data?.runs ?? []).filter((run) => run.status === "failed").length}
          </div>
        </div>
      </div>

      <Panel
        title={
          <span className="flex items-center gap-2">
            <History className="h-3 w-3" /> Run log
          </span>
        }
        action={
          <div className="flex items-center gap-1.5">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-600" />
              <input
                className="input !py-1.5 !pl-7 !text-[10px]"
                placeholder="Search id, agent, seed"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <select
              className="select !w-auto !py-1.5 !text-[10px]"
              value={scenarioFilter}
              onChange={(event) => {
                const next = event.target.value;
                if (next) setParams({ scenario: next });
                else setParams({});
              }}
            >
              <option value="">All scenarios</option>
              {scenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </select>
          </div>
        }
        bodyClassName="p-0"
      >
        {loading && !data ? (
          <div className="p-4">
            <Spinner label="Loading runs" />
          </div>
        ) : null}
        {!loading && runs.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={<Inbox className="h-6 w-6" />}
              title="No runs yet"
              detail="Launch a scenario from the workspace. The run, every action, and every transition will appear here."
              action={
                <Link to="/" className="btn-primary mt-1">
                  Open workspace
                </Link>
              }
            />
          </div>
        ) : null}
        {runs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse">
              <thead>
                <tr>
                  <th className="table-head">Run</th>
                  <th className="table-head">Scenario</th>
                  <th className="table-head">Agent</th>
                  <th className="table-head">Seed</th>
                  <th className="table-head">Status</th>
                  <th className="table-head">Score</th>
                  <th className="table-head">Outcome</th>
                  <th className="table-head">Steps</th>
                  <th className="table-head">When</th>
                  <th className="table-head" />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.id}
                    className="group cursor-pointer transition hover:bg-white/[0.025]"
                    onClick={() => navigate(`/runs/${run.id}`)}
                  >
                    <td className="table-cell font-mono text-[10px] text-mint">{run.id}</td>
                    <td className="table-cell">
                      <div className="text-[11px] text-slate-300">{scenarioNames[run.scenario_id] || run.scenario_id}</div>
                      <div className="text-[9px] text-slate-600">{run.options ? Object.entries(run.options).map(([k, v]) => `${k}=${v}`).join(" · ") : ""}</div>
                    </td>
                    <td className="table-cell">
                      <div className="text-[11px] text-slate-300">{run.agent.label}</div>
                      <div className="text-[9px] capitalize text-slate-600">{run.agent.type}</div>
                    </td>
                    <td className="table-cell font-mono text-[10px]">{run.seed}</td>
                    <td className="table-cell"><StatusPill status={run.status} /></td>
                    <td className="table-cell">
                      <span
                        className={`font-mono text-sm font-semibold ${
                          run.score === null
                            ? "text-slate-600"
                            : statusTone(run.status) === "coral"
                              ? "text-coral"
                              : Number(run.score) >= 75
                                ? "text-mint"
                                : Number(run.score) >= 45
                                  ? "text-amber"
                                  : "text-coral"
                        }`}
                      >
                        {run.score === null ? "—" : Number(run.score).toFixed(1)}
                      </span>
                    </td>
                    <td className="table-cell text-[10px] text-fog">{summary(run)}</td>
                    <td className="table-cell font-mono text-[10px]">{run.steps}</td>
                    <td className="table-cell whitespace-nowrap text-[10px] text-slate-500">{relativeTime(run.created_at)}</td>
                    <td className="table-cell text-right">
                      <span className="inline-flex items-center gap-1 text-[10px] text-fog group-hover:text-mint">
                        replay <ArrowRight className="h-3 w-3" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}