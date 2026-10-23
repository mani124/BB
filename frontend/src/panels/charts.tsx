import React from 'react';
import type { HistBin } from '../features/analytics/types';

const W = 320;
const H = 120;
const PAD = { l: 4, r: 4, t: 6, b: 16 };

/** SVG histogram. Colour never carries meaning alone: the axis labels and a text summary sit next to it. */
export const Histogram: React.FC<{ bins: HistBin[]; label: string; fmt?: (n: number) => string; zeroLine?: boolean }> = ({ bins, label, fmt = (n) => String(Math.round(n * 100) / 100), zeroLine }) => {
  if (bins.length === 0) return <p className="text-xs desk-muted p-2">Not enough data.</p>;
  const lo = bins[0].lo;
  const hi = bins[bins.length - 1].hi;
  const maxC = Math.max(1, ...bins.map((b) => b.count));
  const span = hi - lo || 1;
  const x = (v: number) => PAD.l + ((v - lo) / span) * (W - PAD.l - PAD.r);
  const single = bins.length === 1 && bins[0].lo === bins[0].hi;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="w-full" style={{ maxHeight: 150 }}>
      {bins.map((b, i) => {
        const h = (b.count / maxC) * (H - PAD.t - PAD.b);
        const x0 = single ? W / 2 - 6 : x(b.lo);
        const w = single ? 12 : Math.max(1, x(b.hi) - x(b.lo) - 1);
        const neg = b.hi <= 0;
        return <rect key={i} x={x0} y={H - PAD.b - h} width={w} height={h} fill={zeroLine ? (neg ? 'var(--down)' : 'var(--up)') : 'var(--accent)'}><title>{`${fmt(b.lo)} to ${fmt(b.hi)}: ${b.count}`}</title></rect>;
      })}
      {zeroLine && lo < 0 && hi > 0 && <line x1={x(0)} x2={x(0)} y1={PAD.t} y2={H - PAD.b} stroke="var(--fg)" strokeDasharray="3 2" />}
      <text x={PAD.l} y={H - 3} fontSize="9" fill="var(--muted)">{fmt(lo)}</text>
      <text x={W - PAD.r} y={H - 3} fontSize="9" fill="var(--muted)" textAnchor="end">{fmt(hi)}</text>
      <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--line-strong)" />
    </svg>
  );
};

export const Scatter: React.FC<{ points: { x: number; y: number }[]; label: string; xLabel: string; yLabel: string; diagonal?: boolean }> = ({ points, label, xLabel, yLabel, diagonal }) => {
  if (points.length === 0) return <p className="text-xs desk-muted p-2">Not enough data.</p>;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x0 = Math.min(0, ...xs); const x1 = Math.max(0, ...xs) || 1;
  const y0 = Math.min(0, ...ys); const y1 = Math.max(0, ...ys) || 1;
  const sx = (v: number) => PAD.l + 12 + ((v - x0) / (x1 - x0 || 1)) * (W - PAD.l - PAD.r - 12);
  const sy = (v: number) => H - PAD.b - ((v - y0) / (y1 - y0 || 1)) * (H - PAD.t - PAD.b);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}. ${points.length} points.`} className="w-full" style={{ maxHeight: 160 }}>
      <line x1={sx(x0)} x2={sx(x1)} y1={sy(0)} y2={sy(0)} stroke="var(--line-strong)" />
      <line x1={sx(0)} x2={sx(0)} y1={sy(y0)} y2={sy(y1)} stroke="var(--line-strong)" />
      {diagonal && <line x1={sx(x0)} y1={sy(x0)} x2={sx(x1)} y2={sy(x1)} stroke="var(--muted)" strokeDasharray="2 3" />}
      {points.map((p, i) => <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="2.5" fill="var(--accent)" fillOpacity="0.7" />)}
      <text x={W - PAD.r} y={H - 3} fontSize="9" fill="var(--muted)" textAnchor="end">{xLabel}</text>
      <text x={PAD.l} y={10} fontSize="9" fill="var(--muted)">{yLabel}</text>
    </svg>
  );
};
