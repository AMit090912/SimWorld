import type { CityState, SimPackage } from "../../lib/types";
import { nodeXY } from "../../lib/format";

const PALETTE = {
  roadCasing: "#0a121a",
  road: "#2a3d4f",
  roadLine: "rgba(255,255,255,0.16)",
  block: "#0a131c",
  blockEdge: "#1a2a38",
  blockAccent: "#0f1d28",
  node: "#3a5266",
  mint: "#38e3ab",
  amber: "#f5b84c",
  coral: "#ff7272",
  sky: "#72a9ff",
  fog: "#8b9dae",
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
  const pad = compact ? 30 : 40;
  const width = state.grid * cell + pad * 2;
  const height = state.grid * cell + pad * 2;
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
      const accent = (x * 5 + y * 3) % 4 === 0;
      blocks.push(
        <g key={`b-${x}-${y}`}>
          <rect
            x={cx - size / 2}
            y={cy - size / 2}
            width={size}
            height={size}
            rx={compact ? 3 : 5}
            fill={accent ? PALETTE.blockAccent : PALETTE.block}
            stroke={PALETTE.blockEdge}
            strokeWidth={1}
          />
          <rect
            x={cx - size / 2 + 5}
            y={cy - size / 2 + 5}
            width={size - 10}
            height={(size - 10) * 0.34}
            rx={2}
            fill="rgba(255,255,255,0.022)"
          />
          {!compact && (x + y) % 3 === 0 ? (
            <rect
              x={cx + size / 2 - 15}
              y={cy + size / 2 - 15}
              width={7}
              height={7}
              rx={1}
              fill="rgba(56,227,171,0.18)"
            />
          ) : null}
        </g>,
      );
    }
  }

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg bg-[#070d13]">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio={compact ? "xMidYMid slice" : "xMidYMid meet"}
        className="h-full w-full"
        role="img"
        aria-label={`City map, simulation step ${state.step}, van at ${state.vehicle.node}`}
      >
        <defs>
          <radialGradient id="fog-vignette" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#05080c" stopOpacity="0" />
            <stop offset="70%" stopColor="#05080c" stopOpacity="0" />
            <stop offset="100%" stopColor="#05080c" stopOpacity="0.55" />
          </radialGradient>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0 L0 0 0 20" fill="none" stroke="rgba(255,255,255,0.022)" strokeWidth="1" />
          </pattern>
          <filter id="van-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={width} height={height} fill="#070d13" />
        <rect width={width} height={height} fill="url(#grid)" />
        {blocks}

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
                  <circle cx={mx} cy={my} r={compact ? 7 : 8} fill="#1a0f12" stroke={PALETTE.coral} strokeWidth={1.4} />
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
            stroke={PALETTE.mint}
            strokeWidth={compact ? 1.5 : 2}
            strokeDasharray="2 4"
            opacity={0.55}
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
          const rightSide = Number(node.split(",")[0]) < state.grid - 1;
          const labelX = x + (rightSide ? 15 : -15);
          const anchor = rightSide ? "start" : "end";
          return (
            <g key={`d-${node}`}>
              <circle cx={x} cy={y} r={compact ? 8 : 10} fill="#0a141d" stroke={tone} strokeWidth={1.6} />
              <circle cx={x} cy={y} r={compact ? 2 : 2.6} fill={tone} />
              {packages.length > 1 ? (
                <>
                  <circle cx={x + 7} cy={y - 7} r={5} fill="#0a141d" stroke={tone} strokeWidth={1} />
                  <text x={x + 7} y={y - 4.7} textAnchor="middle" fill={tone} fontSize={5.5} fontFamily="ui-monospace">
                    {packages.length}
                  </text>
                </>
              ) : null}
              {!compact ? (
                <>
                  <text x={labelX} y={y - 2} textAnchor={anchor} fill="#cfe0ee" fontSize={9.4} fontFamily="ui-sans-serif" fontWeight={600}>
                    {label.length > 17 ? `${label.slice(0, 16)}…` : label}
                  </text>
                  <text x={labelX} y={y + 8} textAnchor={anchor} fill={tone} fontSize={7.6} fontFamily="ui-monospace">
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
                  fill="rgba(114,169,255,0.12)"
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
                fill="rgba(56,227,171,0.12)"
                stroke={PALETTE.mint}
                strokeWidth={1.2}
              />
              <path d={`M${dx - 5} ${dy + 2} L${dx - 5} ${dy - 3} L${dx} ${dy - 6} L${dx + 5} ${dy - 3} L${dx + 5} ${dy + 2} Z`} fill="none" stroke={PALETTE.mint} strokeWidth={1} />
              {!compact ? (
                <text x={dx} y={dy + 22} textAnchor="middle" fill={PALETTE.mint} fontSize={6.5} fontFamily="ui-monospace" letterSpacing={1}>
                  DEPOT
                </text>
              ) : null}
            </g>
          );
        })()}

        <g transform={`translate(${vx} ${vy})`} style={{ transition: "transform 420ms cubic-bezier(.4,0,.2,1)" }}>
          <circle r={compact ? 10 : 13} fill="rgba(56,227,171,0.08)" />
          <g transform={`rotate(${heading})`}>
            <path
              d={`M0 ${compact ? -9 : -11} L${compact ? 6 : 7.5} ${compact ? 5 : 6} L0 ${compact ? 2 : 2.5} L${compact ? -6 : -7.5} ${compact ? 5 : 6} Z`}
              fill={PALETTE.mint}
              filter="url(#van-glow)"
            />
          </g>
          {state.vehicle.cargo.length > 0 ? (
            <circle cx={compact ? 9 : 11} cy={compact ? -9 : -11} r={4.5} fill="#0a141d" stroke={PALETTE.mint} strokeWidth={0.9}>
              <title>{`${state.vehicle.cargo.length} package(s) on board`}</title>
            </circle>
          ) : null}
          {state.vehicle.cargo.length > 0 ? (
            <text x={compact ? 9 : 11} y={compact ? -7 : -8.6} textAnchor="middle" fill={PALETTE.mint} fontSize={5.5} fontFamily="ui-monospace">
              {state.vehicle.cargo.length}
            </text>
          ) : null}
          {!compact ? (
            <text x={0} y={22} textAnchor="middle" fill={PALETTE.mint} fontSize={6.4} fontFamily="ui-monospace" letterSpacing={1.4}>
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
        <div className="absolute left-2 top-2 rounded border border-sky/30 bg-ink-950/85 px-1.5 py-0.5 font-mono text-[9px] text-sky">
          sensor range {state.fog_radius} hops
        </div>
      ) : null}
      <div className="pointer-events-none absolute bottom-2 right-2 rounded border border-line/60 bg-ink-950/80 px-1.5 py-0.5 font-mono text-[9px] text-fog">
        {state.vehicle.node} · {state.vehicle.fuel_l.toFixed(1)} L
      </div>
    </div>
  );
}