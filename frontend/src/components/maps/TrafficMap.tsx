import type { TrafficState } from "../../lib/types";
import { nodeXY } from "../../lib/format";

const PALETTE = {
  paper: "#E7DECD",
  roadCasing: "#C4B395",
  road: "#FBF8F1",
  mint: "#1F5A4A",
  sky: "#2E5A74",
  amber: "#A9771F",
  coral: "#A33A32",
  line: "#B3A487",
};

export default function TrafficMap({
  state,
  compact = false,
  fit = "auto",
}: {
  state: TrafficState;
  compact?: boolean;
  fit?: "auto" | "contain";
}) {
  const cell = compact ? 104 : 132;
  const pad = compact ? 34 : 46;
  const width = state.grid * cell + pad * 2;
  const height = state.grid * cell + pad * 2;
  const pos = (node: string): [number, number] => {
    const [x, y] = nodeXY(node);
    return [pad + x * cell, pad + y * cell];
  };
  const incidentMap = new Map(state.incidents.map((incident) => [`${incident.intersection}:${incident.approach}`, incident]));

  return (
    <div className="relative h-full w-full overflow-hidden rounded-md bg-[#E7DECD]">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio={fit === "contain" ? "xMidYMid meet" : compact ? "xMidYMid slice" : "xMidYMid meet"}
        className="h-full w-full"
        role="img"
        aria-label={`Traffic signal state at simulation step ${state.step}`}
      >
        <defs>
          <pattern id="tgrid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M24 0 L0 0 0 24" fill="none" stroke="rgba(30,39,36,0.04)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill={PALETTE.paper} />
        <rect width={width} height={height} fill="url(#tgrid)" />

        {state.intersections.map((from) => {
          const [ax, ay] = pos(from.id);
          return state.intersections
            .filter((to) => {
              const [bx, by] = nodeXY(to.id);
              const [fx, fy] = nodeXY(from.id);
              return Math.abs(bx - fx) + Math.abs(by - fy) === 1 && to.id > from.id;
            })
            .map((to) => {
              const [bx, by] = pos(to.id);
              return (
                <g key={`${from.id}-${to.id}`}>
                  <line x1={ax} y1={ay} x2={bx} y2={by} stroke={PALETTE.roadCasing} strokeWidth={compact ? 18 : 22} strokeLinecap="round" />
                  <line x1={ax} y1={ay} x2={bx} y2={by} stroke={PALETTE.road} strokeWidth={compact ? 11 : 14} strokeLinecap="round" />
                  <line x1={ax} y1={ay} x2={bx} y2={by} stroke="rgba(30,39,36,0.12)" strokeWidth={1} strokeDasharray="4 8" />
                </g>
              );
            });
        })}

        {state.intersections.map((intersection) => {
          const [x, y] = pos(intersection.id);
          const phaseColor = intersection.phase === "NS" ? PALETTE.mint : PALETTE.sky;
          const total = Object.values(intersection.queues).reduce((sum, value) => sum + value, 0);
          const approaches: Array<{ key: "N" | "S" | "E" | "W"; x: number; y: number; w: number; h: number }> = [];
          const inner = compact ? 22 : 26;
          const maxBar = compact ? 26 : 36;
          const queueScale = compact ? 3.4 : 4.2;
          (Object.keys(intersection.queues) as Array<"N" | "S" | "E" | "W">).forEach((approach) => {
            const count = intersection.queues[approach];
            if (!count) return;
            const length = Math.min(maxBar, 5 + count * queueScale);
            if (approach === "N") approaches.push({ key: approach, x: x - 3, y: y - inner - length, w: 6, h: length });
            if (approach === "S") approaches.push({ key: approach, x: x - 3, y: y + inner, w: 6, h: length });
            if (approach === "E") approaches.push({ key: approach, x: x + inner, y: y - 3, w: length, h: 6 });
            if (approach === "W") approaches.push({ key: approach, x: x - inner - length, y: y - 3, w: length, h: 6 });
          });
          return (
            <g key={intersection.id}>
              <circle cx={x} cy={y} r={inner + 4} fill={PALETTE.paper} stroke={PALETTE.line} strokeWidth={1} />
              <circle cx={x} cy={y} r={inner} fill="#F8F3E9" stroke={phaseColor} strokeWidth={1.4} opacity={0.95} />
              {approaches.map((bar) => {
                const blocked = incidentMap.get(`${intersection.id}:${bar.key}`);
                return (
                  <rect
                    key={`${intersection.id}-${bar.key}`}
                    x={bar.x}
                    y={bar.y}
                    width={bar.w}
                    height={bar.h}
                    rx={1.5}
                    fill={blocked ? "rgba(163,58,50,0.55)" : "rgba(169,119,31,0.72)"}
                  >
                    <title>{`${intersection.id} ${bar.key}: ${intersection.queues[bar.key]} waiting`}</title>
                  </rect>
                );
              })}
              {approaches.map((bar) => {
                const count = intersection.queues[bar.key];
                const cx = bar.x + bar.w / 2;
                const cy = bar.y + bar.h / 2;
                return (
                  <text
                    key={`${intersection.id}-${bar.key}-label`}
                    x={cx}
                    y={cy + 2}
                    textAnchor="middle"
                    fill="#1E2724"
                    fontSize={compact ? 5 : 6}
                    fontFamily="ui-monospace"
                    fontWeight={700}
                  >
                    {count}
                  </text>
                );
              })}
              {incidentMap.size > 0
                ? state.incidents
                    .filter((incident) => incident.intersection === intersection.id)
                    .map((incident, index) => (
                      <text
                        key={`${incident.intersection}-${incident.approach}-${index}`}
                        x={x + inner + 4}
                        y={y - inner - 2}
                        fill={PALETTE.coral}
                        fontSize={compact ? 6 : 7}
                        fontFamily="ui-monospace"
                      >
                        !
                      </text>
                    ))
                : null}
              <text x={x} y={y + 3} textAnchor="middle" fill={phaseColor} fontSize={compact ? 6 : 7} fontFamily="ui-monospace" fontWeight={700}>
                {intersection.phase}
              </text>
              {!compact ? (
                <text x={x} y={y + inner + 14} textAnchor="middle" fill="#6C7870" fontSize={6} fontFamily="ui-monospace">
                  {intersection.id}
                </text>
              ) : null}
              {!compact ? (
                <text x={x} y={y - inner - 4} textAnchor="middle" fill="#6C7870" fontSize={5.5} fontFamily="ui-monospace">
                  {total} queued
                </text>
              ) : null}
              <title>{`${intersection.id}: phase ${intersection.phase}, ${total} waiting, oldest ${intersection.oldest_wait_ticks} ticks`}</title>
            </g>
          );
        })}
      </svg>
      {!compact ? (
      <div className="pointer-events-none absolute bottom-2 right-2 flex items-center gap-2 rounded border border-line/60 bg-paper/80 px-2 py-1 font-mono text-[9px]">
        <span className="flex items-center gap-1 text-pine">
          <span className="h-1.5 w-1.5 rounded-full bg-pine" /> NS
        </span>
        <span className="flex items-center gap-1 text-steel">
          <span className="h-1.5 w-1.5 rounded-full bg-steel" /> EW
        </span>
        <span className="flex items-center gap-1 text-ochre">
          <span className="h-1.5 w-1.5 rounded-full bg-ochre" /> queue
        </span>
      </div>
      ) : null}
    </div>
  );
}