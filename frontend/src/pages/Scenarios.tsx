import { ArrowRight, Blocks, MapPin, Radar, Timer } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Scenario } from "../lib/types";
import { useApiData } from "../hooks/useApiData";
import CityMap from "../components/maps/CityMap";
import TrafficMap from "../components/maps/TrafficMap";
import { ErrorBanner, PageHeader, Panel, Spinner } from "../components/ui";

function Preview({ scenario }: { scenario: Scenario }) {
  const { data, loading } = useApiData(() => api.preview(scenario.id, 7), [scenario.id]);
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-[#E7DECD]">
        <Spinner label="Rendering map" />
      </div>
    );
  }
  if (!data) return <div className="h-full bg-[#E7DECD]" />;
  return data.snapshot.kind === "city_logistics" ? (
    <CityMap state={data.snapshot} compact />
  ) : (
    <TrafficMap state={data.snapshot} compact fit="contain" />
  );
}

function ScenarioCard({ scenario, index }: { scenario: Scenario; index: number }) {
  return (
    <article className="panel group flex flex-col overflow-hidden animate-fade-up" style={{ animationDelay: `${index * 45}ms` }}>
      <div className="relative h-[200px] overflow-hidden border-b border-line/70 bg-[#E7DECD]">
        <Preview scenario={scenario} />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#FBF8F1] via-[#FBF8F1]/55 to-transparent" />
        <div className="absolute left-3 top-3 flex items-center gap-1.5">
          <span className={scenario.kind === "city_logistics" ? "chip-sky" : "chip-mint"}>
            {scenario.kind === "city_logistics" ? "Logistics" : "Traffic"}
          </span>
          <span
            className={
              scenario.difficulty === "Brutal" || scenario.difficulty === "Hard"
                ? "chip-coral"
                : scenario.difficulty === "Tight"
                  ? "chip-amber"
                  : "chip"
            }
          >
            {scenario.difficulty}
          </span>
        </div>
        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink-900">{scenario.name}</h3>
          <span className="font-mono text-[9px] text-ink-500">{scenario.horizon_steps} ticks</span>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-3.5">
        <p className="text-[11px] leading-relaxed text-ink-500">{scenario.tagline}</p>

        <div className="mt-2.5 space-y-1">
          {scenario.objectives.slice(0, 2).map((objective) => (
            <div key={objective} className="flex items-start gap-1.5 text-[10px] leading-relaxed text-ink-600">
              <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-pine/70" />
              {objective}
            </div>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-1">
          <span className="chip">
            <Timer className="h-2.5 w-2.5" /> {scenario.variations.length} variations
          </span>
          <span className="chip">
            <Radar className="h-2.5 w-2.5" /> {scenario.metrics.length} metrics
          </span>
          <span className="chip">
            <MapPin className="h-2.5 w-2.5" /> seed {scenario.default_seeds[0]}
          </span>
        </div>

        <div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2.5">
          <Link to={`/?scenario=${encodeURIComponent(scenario.id)}`} className="btn-primary !px-2.5 !py-1.5 !text-[11px]">
            Open in workspace <ArrowRight className="h-3 w-3" />
          </Link>
          <Link to={`/runs?scenario=${encodeURIComponent(scenario.id)}`} className="text-[10px] text-ink-500 hover:text-ink-800">
            View runs
          </Link>
        </div>
      </div>
    </article>
  );
}

export default function Scenarios() {
  const { data, error, loading, reload } = useApiData(() => api.scenarios(), []);
  const scenarios = data?.scenarios ?? [];
  const city = scenarios.filter((scenario) => scenario.kind === "city_logistics");
  const traffic = scenarios.filter((scenario) => scenario.kind === "traffic_control");

  return (
    <div>
      <PageHeader
        eyebrow="Scenario browser"
        title="Environments that enforce their own rules"
        description="Every scenario below is a real, deterministic simulation with its own state, action validation, scheduled disruptions, and evaluation metrics. Nothing here is a mock-up."
        actions={
          <div className="flex gap-1.5">
            <span className="chip">
              <Blocks className="h-2.5 w-2.5" /> 2 environments
            </span>
            <span className="chip">{scenarios.length} scenarios</span>
          </div>
        }
      />

      {error ? <ErrorBanner message={error} onRetry={reload} /> : null}
      {loading ? (
        <Panel>
          <Spinner label="Loading scenarios" />
        </Panel>
      ) : null}

      {[
        { title: "City logistics", items: city, caption: "Routing, batching, fuel, deadlines." },
        { title: "Traffic control", items: traffic, caption: "Signal phases, queues, safety constraints." },
      ].map((group) =>
        group.items.length ? (
          <section key={group.title} className="mb-7">
            <div className="mb-2.5 flex items-baseline justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-700">{group.title}</h2>
              <span className="text-[10px] text-ink-500">{group.caption}</span>
            </div>
            <div className="grid gap-3.5 md:grid-cols-2 xl:grid-cols-3">
              {group.items.map((scenario, index) => (
                <ScenarioCard key={scenario.id} scenario={scenario} index={index} />
              ))}
            </div>
          </section>
        ) : null,
      )}

      <div className="rounded-lg border border-line/70 bg-surface/40 px-4 py-3 text-[10px] leading-relaxed text-ink-500">
        Scenario ids are stable, versioned, and stored with every run. Add a new environment by implementing the
        same <span className="font-mono text-ink-700">observation / legal actions / apply / metrics</span> contract —
        the engine, API, replay, and comparison surfaces do not need to change.
      </div>
    </div>
  );
}