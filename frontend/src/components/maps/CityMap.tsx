import { useState } from "react";
import type { CityState, SimPackage } from "../../lib/types";
import { nodeXY } from "../../lib/format";

const PALETTE = {
  paper: "#E3D8C3",
  roadCasing: "#BFAE90",
  road: "#FDFBF6",
  roadLine: "rgba(30,39,36,0.18)",
  block: "#D2C3A6",
  blockEdge: "#B5A382",
  blockAccent: "#E4D9C5",
  roof: "#F5EDDE",
  node: "#AA997A",
  mint: "#1F5A4A",
  accent: "#C8552B",
  amber: "#A9771F",
  coral: "#A33A32",
  sky: "#2E5A74",
  fog: "#6C7870",
};

export default function CityMap({
  state,
  trail = [],
  compact = false,
}: {
  state: CityState;
  trail?: string[];
  compact?: boolean;
}) {
  const cell = compact ? 62 : 82;
  const footprint = cell * 0.56;
  const labelPad = compact ? 22 : 62;
  const pad = labelPad - cell / 2 + footprint / 2;
  const width = (state.grid - 1) * cell + footprint + labelPad * 2;
  const height = width;
  const sheetX = labelPad - 36;
  const sheetSize = width - sheetX * 2;
  const pos = (node: string): [number, number] => {
    const [x, y] = nodeXY(node);
    return [pad + x * cell, pad + y * cell];
  };

  const destinations = new Map<string, SimPackage[]>();
  for (const pkg of state.packages) {
    const list = destinations.get(pkg.dest) || [];
    list.push(pkg);
    destinations.set(pkg.dest, list);
  }

  const stationMap = new Map(state.stations.map((station) => [station.node, station]));
  const [legendOpen, setLegendOpen] = useState(true);
  const [vx, vy] = pos(state.vehicle.node);
  const uniqueTrail: string[] = [];
  for (const node of trail) {
    if (uniqueTrail[uniqueTrail.length - 1] !== node) uniqueTrail.push(node);
  }
  if (uniqueTrail[uniqueTrail.length - 1] !== state.vehicle.node) uniqueTrail.push(state.vehicle.node);
  const trailPoints = uniqueTrail.map((node) => pos(node).join(",")).join(" ");

  let heading = 0;
  if (uniqueTrail.length >= 2) {
    const [px, py] = pos(uniqueTrail[uniqueTrail.length - 2]);
    heading = (Math.atan2(vy - py, vx - px) * 180) / Math.PI + 90;
  }

  const blocks = [];
  for (let x = 0; x < state.grid; x += 1) {
    for (let y = 0; y < state.grid; y += 1) {
      const cx = pad + (x + 0.5) * cell;
      const cy = pad + (y + 0.5) * cell;
      const size = cell * 0.56;
      const park = (x * 7 + y * 11) % 19 === 0;
      const inset = size * 0.13;
      const bx = cx - size / 2 + inset;
      const by = cy - size / 2 + inset;
      const inner = size - inset * 2;
      const gap = 2.4;
      const variant = compact ? 0 : (x * 5 + y * 7 + x * y * 3) % 6;
      const roofTone = (x * 3 + y * 5) % 5 === 0 ? "#F0E5D0" : PALETTE.roof;
      const pond = park && (x + y) % 3 === 0;

      let roofs;
      if (variant === 1) {
        const h = (inner - gap) / 2;
        roofs = (
          <>
            <rect x={bx} y={by} width={inner} height={h} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
            <rect x={bx} y={by + h + gap} width={inner} height={h} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
          </>
        );
      } else if (variant === 2) {
        const w = inner * 0.4;
        roofs = (
          <>
            <rect x={bx} y={by} width={w} height={inner} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
            <rect x={bx + w + gap} y={by + inner * 0.5} width={inner - w - gap} height={inner * 0.5} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
          </>
        );
      } else if (variant === 3) {
        roofs = (
          <>
            <rect x={bx} y={by} width={inner} height={inner} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
            <rect x={bx + inner * 0.3} y={by + inner * 0.3} width={inner * 0.4} height={inner * 0.4} rx={1} fill={PALETTE.block} />
          </>
        );
      } else if (variant === 4) {
        const w = (inner - gap * 2) / 3;
        roofs = (
          <>
            {[0, 1, 2].map((i) => (
              <rect
                key={i}
                x={bx + i * (w + gap)}
                y={by + (i % 2 === 1 ? inner * 0.12 : 0)}
                width={w}
                height={inner - (i % 2 === 1 ? inner * 0.12 : 0)}
                rx={1.5}
                fill={roofTone}
                stroke="rgba(30,39,36,0.10)"
                strokeWidth={0.8}
              />
            ))}
          </>
        );
      } else if (variant === 5) {
        roofs = (
          <>
            <rect x={bx} y={by} width={inner * 0.62} height={inner} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
            <rect x={bx + inner * 0.66} y={by + inner * 0.35} width={inner * 0.34} height={inner * 0.65} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />
          </>
        );
      } else {
        roofs = <rect x={bx} y={by} width={inner} height={inner} rx={1.5} fill={roofTone} stroke="rgba(30,39,36,0.10)" strokeWidth={0.8} />;
      }

      blocks.push(
        <g key={`b-${x}-${y}`}>
          <rect
            x={cx - size / 2}
            y={cy - size / 2}
            width={size}
            height={size}
            rx={compact ? 3 : 5}
            fill={park ? "rgba(31,90,74,0.10)" : PALETTE.block}
            stroke={park ? "rgba(31,90,74,0.30)" : PALETTE.blockEdge}
            strokeWidth={1}
          />
          {park ? (
            !compact ? (
              <>
                <circle cx={cx - 5} cy={cy + 1} r={6} fill="rgba(31,90,74,0.11)" stroke="rgba(31,90,74,0.35)" strokeWidth={0.8} />
                <circle cx={cx + 7} cy={cy - 6} r={4.5} fill="rgba(31,90,74,0.08)" stroke="rgba(31,90,74,0.28)" strokeWidth={0.8} />
                {pond ? <ellipse cx={cx + 5} cy={cy + 8} rx={7} ry={4} fill="rgba(46,90,116,0.18)" stroke="rgba(46,90,116,0.35)" strokeWidth={0.7} /> : null}
              </>
            ) : null
          ) : compact ? null : (
            roofs
          )}
        </g>,
      );
    }
  }

  return (
    <div className="relative flex h-full w-full overflow-hidden rounded-md bg-[#E3D8C3]">
      <div className="relative min-h-0 min-w-0 flex-1">
        <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio={compact ? "xMidYMin slice" : "xMidYMid meet"}
        className="h-full w-full"
        role="img"
        aria-label={`City map, simulation step ${state.step}, van at ${state.vehicle.node}`}
      >
        <defs>
          <radialGradient id="fog-vignette" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#E3D8C3" stopOpacity="0" />
            <stop offset="70%" stopColor="#E3D8C3" stopOpacity="0" />
            <stop offset="100%" stopColor="#E3D8C3" stopOpacity="0.55" />
          </radialGradient>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0 L0 0 0 20" fill="none" stroke="rgba(30,39,36,0.055)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill={PALETTE.paper} />
        <rect width={width} height={height} fill="url(#grid)" />
        {!compact ? (
          <>
            <rect
              x={sheetX + 2}
              y={sheetX + 2}
              width={sheetSize}
              height={sheetSize}
              fill="rgba(30,39,36,0.10)"
            />
            <rect
              x={sheetX}
              y={sheetX}
              width={sheetSize}
              height={sheetSize}
              fill="#F7F2E8"
              stroke="rgba(30,39,36,0.20)"
              strokeWidth={1}
            />
          </>
        ) : null}
        {blocks}

        {!compact ? (
          <g>
            <rect
              x={pad}
              y={pad}
              width={cell * state.grid}
              height={cell * state.grid}
              fill="none"
              stroke={PALETTE.roadCasing}
              strokeWidth={15}
              strokeLinejoin="round"
            />
            <rect
              x={pad}
              y={pad}
              width={cell * state.grid}
              height={cell * state.grid}
              fill="none"
              stroke={PALETTE.road}
              strokeWidth={10}
              strokeLinejoin="round"
            />
            <rect
              x={pad}
              y={pad}
              width={cell * state.grid}
              height={cell * state.grid}
              fill="none"
              stroke={PALETTE.roadLine}
              strokeWidth={1}
              strokeDasharray="3 6"
              strokeLinejoin="round"
            />
          </g>
        ) : null}

        {state.edges.map((edge) => {
          const [ax, ay] = pos(edge.a);
          const [bx, by] = pos(edge.b);
          const mx = (ax + bx) / 2;
          const my = (ay + by) / 2;
          return (
            <g key={edge.id}>
              <line x1={ax} y1={ay} x2={bx} y2={by} stroke={PALETTE.roadCasing} strokeWidth={compact ? 12 : 15} strokeLinecap="round" />
              <line x1={ax} y1={ay} x2={bx} y2={by} stroke={PALETTE.road} strokeWidth={compact ? 8 : 10} strokeLinecap="round" />
              {!edge.open ? (
                <>
                  <line
                    x1={ax}
                    y1={ay}
                    x2={bx}
                    y2={by}
                    stroke={PALETTE.coral}
                    strokeWidth={3}
                    strokeDasharray="5 5"
                    opacity={0.9}
                  />
                  <circle cx={mx} cy={my} r={compact ? 7 : 8} fill={PALETTE.roof} stroke={PALETTE.coral} strokeWidth={1.4} />
                  <path
                    d={`M${mx - 3} ${my - 3} L${mx + 3} ${my + 3} M${mx + 3} ${my - 3} L${mx - 3} ${my + 3}`}
                    stroke={PALETTE.coral}
                    strokeWidth={1.4}
                    strokeLinecap="round"
                  />
                  {!compact ? (
                    <text x={mx} y={my + 20} textAnchor="middle" fill={PALETTE.coral} fontSize={7} fontFamily="ui-monospace">
                      CLOSED
                    </text>
                  ) : null}
                </>
              ) : (
                <line
                  x1={ax}
                  y1={ay}
                  x2={bx}
                  y2={by}
                  stroke={PALETTE.roadLine}
                  strokeWidth={1}
                  strokeDasharray="3 6"
                />
              )}
            </g>
          );
        })}

        {uniqueTrail.length > 1 ? (
          <polyline
            points={trailPoints}
            fill="none"
            stroke={PALETTE.accent}
            strokeWidth={compact ? 1.5 : 2.2}
            strokeDasharray="3 5"
            opacity={0.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}

        {Object.keys(state.edges.reduce<Record<string, boolean>>((acc, edge) => {
          acc[edge.a] = true;
          acc[edge.b] = true;
          return acc;
        }, {})).map((node) => {
          const [x, y] = pos(node);
          return <circle key={`n-${node}`} cx={x} cy={y} r={compact ? 2.2 : 2.8} fill={PALETTE.node} />;
        })}

        {[...destinations.entries()].map(([node, packages]) => {
          const [x, y] = pos(node);
          const delivered = packages.every((pkg) => pkg.status === "delivered");
          const late = packages.some((pkg) => pkg.late);
          const tone = delivered ? (late ? PALETTE.coral : PALETTE.mint) : PALETTE.amber;
          const deadline = Math.min(...packages.map((pkg) => pkg.deadline_min));
          const label = packages[0].dest_label;
          const shortLabel = label.length > 18 ? `${label.slice(0, 17)}...` : label;
          const pillW = Math.min(132, Math.max(70, shortLabel.length * 5.6 + 14));
          const [gx, gy] = node.split(",").map((part) => Number(part));
          const onRight = gx < state.grid / 2;
          const pillX = Math.max(
            pad / 2,
            Math.min(width - pillW - pad / 2, onRight ? x + 14 : x - 14 - pillW),
          );
          const pillAbove = (gx + gy * 2) % 3 !== 1;
          const pillY = pillAbove ? y - 19 : y + 7;
          const titleY = pillAbove ? y - 9 : y + 17;
          const dueY = pillAbove ? y - 1 : y + 25;
          return (
            <g key={`d-${node}`}>
              <circle
                cx={x}
                cy={y}
                r={compact ? 7 : delivered ? 7 : 9}
                fill={PALETTE.roof}
                stroke={tone}
                strokeWidth={delivered ? 1 : 1.8}
                opacity={delivered ? 0.55 : 1}
              />
              <circle cx={x} cy={y} r={compact ? 2 : delivered ? 2 : 2.6} fill={tone} opacity={delivered ? 0.6 : 1} />
              {packages.length > 1 ? (
                <>
                  <circle cx={x + 7} cy={y - 7} r={5} fill={PALETTE.roof} stroke={tone} strokeWidth={1} />
                  <text x={x + 7} y={y - 4.7} textAnchor="middle" fill={tone} fontSize={5.5} fontFamily="ui-monospace">
                    {packages.length}
                  </text>
                </>
              ) : null}
              {!compact && !delivered ? (
                <>
                  <rect
                    x={pillX}
                    y={pillY}
                    width={pillW}
                    height={27}
                    rx={4}
                    fill="rgba(251,248,241,0.94)"
                    stroke={tone}
                    strokeOpacity={0.3}
                  />
                  <text x={pillX + 6} y={titleY} fill="#1E2724" fontSize={9.6} fontFamily="ui-sans-serif" fontWeight={600}>
                    {shortLabel}
                  </text>
                  <text x={pillX + 6} y={dueY} fill={tone} fontSize={7.6} fontFamily="ui-monospace">
                    due {deadline}m
                  </text>
                </>
              ) : null}
            </g>
          );
        })}

        {[...stationMap.entries()]
          .filter(([node]) => node !== state.depot)
          .map(([node]) => {
            const [x, y] = pos(node);
            return (
              <g key={`s-${node}`}>
                <rect
                  x={x + 8}
                  y={y + 4}
                  width={compact ? 9 : 11}
                  height={compact ? 9 : 11}
                  rx={2}
                  fill="rgba(46,90,116,0.12)"
                  stroke={PALETTE.sky}
                  strokeWidth={0.8}
                />
                <text x={x + (compact ? 12.5 : 13.5)} y={y + (compact ? 15.6 : 12.5)} textAnchor="middle" fill={PALETTE.sky} fontSize={5.5} fontFamily="ui-monospace">
                  F
                </text>
              </g>
            );
          })}

        {(() => {
          const [dx, dy] = pos(state.depot);
          return (
            <g>
              <rect
                x={dx - 12}
                y={dy - 12}
                width={24}
                height={24}
                rx={4}
                fill="rgba(31,90,74,0.10)"
                stroke={PALETTE.mint}
                strokeWidth={1.2}
              />
              <path d={`M${dx - 5} ${dy + 2} L${dx - 5} ${dy - 3} L${dx} ${dy - 6} L${dx + 5} ${dy - 3} L${dx + 5} ${dy + 2} Z`} fill="none" stroke={PALETTE.mint} strokeWidth={1} />
              {!compact ? (
                <text x={dx} y={dy - 16} textAnchor="middle" fill={PALETTE.mint} fontSize={7} fontFamily="ui-monospace" letterSpacing={1.2}>
                  DEPOT
                </text>
              ) : null}
            </g>
          );
        })()}

        <g transform={`translate(${vx} ${vy})`} style={{ transition: "transform 420ms cubic-bezier(.4,0,.2,1)" }}>
          <circle r={compact ? 10 : 13} fill="rgba(200,85,43,0.10)" />
          <g transform={`rotate(${heading})`}>
            <path
              d={`M0 ${compact ? -9 : -11} L${compact ? 6 : 7.5} ${compact ? 5 : 6} L0 ${compact ? 2 : 2.5} L${compact ? -6 : -7.5} ${compact ? 5 : 6} Z`}
              fill={PALETTE.accent}
            />
          </g>
          {state.vehicle.cargo.length > 0 ? (
            <circle cx={compact ? 9 : 11} cy={compact ? -9 : -11} r={4.5} fill={PALETTE.roof} stroke={PALETTE.mint} strokeWidth={0.9}>
              <title>{`${state.vehicle.cargo.length} package(s) on board`}</title>
            </circle>
          ) : null}
          {state.vehicle.cargo.length > 0 ? (
            <text x={compact ? 9 : 11} y={compact ? -7 : -8.6} textAnchor="middle" fill={PALETTE.accent} fontSize={5.5} fontFamily="ui-monospace">
              {state.vehicle.cargo.length}
            </text>
          ) : null}
          {!compact ? (
            <text x={0} y={22} textAnchor="middle" fill={PALETTE.accent} fontSize={6.4} fontFamily="ui-monospace" letterSpacing={1.4}>
              VAN
            </text>
          ) : null}
          <title>{`Van at ${state.vehicle.node}, fuel ${state.vehicle.fuel_l.toFixed(2)} L`}</title>
        </g>

        {state.fog_radius ? (
          <rect width={width} height={height} fill="url(#fog-vignette)" opacity={0.55} pointerEvents="none" />
        ) : null}
      </svg>

      {state.fog_radius && !compact ? (
        <div className="absolute left-2 top-2 rounded border border-steel/30 bg-paper/85 px-1.5 py-0.5 font-mono text-[9px] text-steel">
          sensor range {state.fog_radius} hops
        </div>
      ) : null}
      <div className="pointer-events-none absolute bottom-2 right-2 rounded border border-line/60 bg-paper/80 px-1.5 py-0.5 font-mono text-[9px] text-ink-500">
        {state.vehicle.node} / {state.vehicle.fuel_l.toFixed(1)} L
      </div>

      {!compact ? (
        <div className="pointer-events-none absolute left-3 top-1/2 hidden -translate-y-1/2 -rotate-90 font-mono text-[8px] uppercase tracking-[0.38em] text-ink-400 min-[1460px]:block">
          Riverside
        </div>
      ) : null}
      </div>

      {!compact ? (
        <aside
          className={`relative z-10 hidden h-full shrink-0 flex-col overflow-hidden border-l border-line/70 bg-surface/95 shadow-panel transition-[width] min-[1460px]:flex ${
            legendOpen ? "w-[118px]" : "w-9"
          }`}
          data-testid="map-legend"
        >
          <button
            type="button"
            onClick={() => setLegendOpen((open) => !open)}
            aria-expanded={legendOpen}
            aria-label={legendOpen ? "Minimize legend" : "Expand legend"}
            className={
              legendOpen
                ? "flex w-full items-center justify-between px-2.5 py-2 text-left"
                : "flex h-full w-full flex-col items-center gap-2 px-1 py-2"
            }
          >
            {legendOpen ? (
              <>
                <span className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">Legend</span>
                <span className="flex items-center gap-1.5">
                  <svg width="16" height="20" viewBox="0 0 18 22" aria-hidden>
                    <path d="M9 1 13 11 9 9 5 11Z" fill="#1E2724" />
                    <path d="M9 9 13 11 9 17 5 11Z" fill="#C8552B" />
                  </svg>
                  <span className="font-mono text-[13px] leading-none text-ink-400">-</span>
                </span>
              </>
            ) : (
              <>
                <svg width="16" height="20" viewBox="0 0 18 22" aria-hidden>
                  <path d="M9 1 13 11 9 9 5 11Z" fill="#1E2724" />
                  <path d="M9 9 13 11 9 17 5 11Z" fill="#C8552B" />
                </svg>
                <span className="font-mono text-[13px] leading-none text-ink-400">+</span>
                <span className="[writing-mode:vertical-rl] font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">
                  Legend
                </span>
              </>
            )}
          </button>
          {legendOpen ? (
            <div className="border-t border-line/70 px-2.5 pb-2.5 pt-2" data-testid="map-legend-items">
              <ul className="space-y-1.5 text-[9px] text-ink-600">
                <li className="flex items-center gap-2"><span className="h-2 w-2 rotate-45 bg-accent" /> Van</li>
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm bg-pine" /> Depot</li>
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-full border-2 border-ochre" /> Stop</li>
                <li className="flex items-center gap-2"><span className="h-0.5 w-2 bg-brick" /> Closed</li>
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm bg-pine/20 ring-1 ring-pine/40" /> Park</li>
              </ul>
              <div className="mt-2 border-t border-line/70 pt-1.5 font-mono text-[8px] uppercase tracking-[0.1em] text-ink-400">
                Grid {state.grid}x{state.grid}
              </div>
            </div>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}