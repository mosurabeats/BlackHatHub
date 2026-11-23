import { useState } from "react";

// Palette validated with the dataviz validator on the dark surface #0b0f15:
// slot 1 blue, slot 2 orange (CVD dE 26.8, normal 31.8, contrast >= 3:1).
export const SERIES = ["#3987e5", "#d95926"];

type Series = { name: string; values: number[] };

/** Grouped vertical bars with one y-axis, recessive grid, legend for >=2 series and hover tooltip. */
export default function BarChart({ labels, series, format, height = 180 }: { labels: string[]; series: Series[]; format: (v: number) => string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640;
  const H = height;
  const padL = 52, padB = 22, padT = 8;
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const nice = (() => {
    const p = Math.pow(10, Math.floor(Math.log10(max)));
    return Math.ceil(max / p) * p;
  })();
  const plotW = W - padL - 4;
  const plotH = H - padB - padT;
  const groupW = plotW / Math.max(1, labels.length);
  const gap = 2;
  const barW = Math.max(2, Math.min(18, (groupW * 0.7 - gap * (series.length - 1)) / series.length));
  const y = (v: number) => padT + plotH - (v / nice) * plotH;
  const ticks = [0, 0.5, 1].map((t) => t * nice);

  return (
    <div className="relative">
      {series.length > 1 && (
        <div className="mb-2 flex gap-4 text-xs text-slate-400">
          {series.map((s, i) => (
            <span key={s.name} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[i] }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={series.map((s) => s.name).join(" and ") + " by period"}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(t)} y2={y(t)} stroke="#1e2633" strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="#64748b">{format(t)}</text>
          </g>
        ))}
        {labels.map((lab, gi) => {
          const gx = padL + gi * groupW + (groupW - (barW * series.length + gap * (series.length - 1))) / 2;
          return (
            <g key={lab} onMouseEnter={() => setHover(gi)} onMouseLeave={() => setHover(null)}>
              <rect x={padL + gi * groupW} y={padT} width={groupW} height={plotH} fill={hover === gi ? "#151b25" : "transparent"} />
              {series.map((s, si) => {
                const v = s.values[gi] || 0;
                const h = Math.max(0, padT + plotH - y(v));
                const x = gx + si * (barW + gap);
                const r = Math.min(4, barW / 2, h);
                return h > 0 ? (
                  <path key={s.name} fill={SERIES[si]}
                    d={`M${x},${padT + plotH} V${padT + plotH - h + r} Q${x},${padT + plotH - h} ${x + r},${padT + plotH - h} H${x + barW - r} Q${x + barW},${padT + plotH - h} ${x + barW},${padT + plotH - h + r} V${padT + plotH} Z`} />
                ) : null;
              })}
              {(labels.length <= 14 || gi % Math.ceil(labels.length / 12) === 0) && (
                <text x={padL + gi * groupW + groupW / 2} y={H - 6} textAnchor="middle" fontSize="10" fill="#64748b">{lab}</text>
              )}
            </g>
          );
        })}
        <line x1={padL} x2={W} y1={padT + plotH} y2={padT + plotH} stroke="#2a3444" />
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-md border border-ink-600 bg-ink-850 px-2.5 py-1.5 text-xs shadow-lg">
          <div className="mb-0.5 text-slate-400">{labels[hover]}</div>
          {series.map((s, i) => (
            <div key={s.name} className="flex items-center gap-2 text-slate-200">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: SERIES[i] }} />
              {s.name}: <span className="num">{format(s.values[hover] || 0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
