import React, { useEffect, useState } from 'react';
import { Pause, Play, SkipBack, SkipForward, StepBack, StepForward, X } from 'lucide-react';

export const REPLAY_SPEEDS = [0.5, 1, 2, 4, 8] as const;
const BASE_STEP_MS = 800;

interface Timed { time: number }
interface Sliceable<C extends Timed, P extends Timed> {
  candles: C[];
  indicators: Record<string, P[]>;
}

/** The index of the first candle to show when a replay starts: the entry candle, else the first. */
export function startIndex(candles: Timed[], entryTime: number | null): number {
  if (entryTime == null) return 0;
  let hit = 0;
  candles.forEach((c, i) => { if (c.time <= entryTime) hit = i; });
  return hit;
}

/** The series as it looked once candle `upTo` had closed: later candles and indicator points are dropped. */
export function sliceSeries<C extends Timed, P extends Timed, S extends Sliceable<C, P>>(series: S, upTo: number): S {
  const last = series.candles[Math.min(upTo, series.candles.length - 1)];
  if (!last) return series;
  const indicators: Record<string, P[]> = {};
  for (const [k, pts] of Object.entries(series.indicators)) indicators[k] = pts.filter((p) => p.time <= last.time);
  return { ...series, candles: series.candles.filter((c) => c.time <= last.time), indicators };
}

/** Play/pause, stepping and speed over `total` candles. Playback stops by itself on the last candle. */
export function useReplay(total: number, initial: number) {
  const [index, setIndex] = useState(initial);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const last = Math.max(total - 1, 0);
  const at = Math.min(index, last);
  const atEnd = at >= last;
  const playingNow = playing && !atEnd;

  useEffect(() => {
    if (!playingNow) return;
    const id = window.setInterval(() => {
      setIndex((i) => Math.min(i + 1, last));
    }, BASE_STEP_MS / speed);
    return () => window.clearInterval(id);
  }, [playingNow, speed, last]);

  useEffect(() => { if (playing && atEnd) setPlaying(false); }, [playing, atEnd]);

  return {
    index: at,
    playing: playingNow,
    speed,
    setSpeed,
    atStart: at <= 0,
    atEnd,
    toggle: () => {
      if (atEnd) { setIndex(0); setPlaying(true); } else setPlaying((p) => !p);
    },
    step: (d: number) => { setPlaying(false); setIndex((i) => Math.max(0, Math.min(i + d, last))); },
    seek: (i: number) => { setPlaying(false); setIndex(Math.max(0, Math.min(i, last))); },
  };
}

export type Replay = ReturnType<typeof useReplay>;

export const ReplayControls: React.FC<{ replay: Replay; total: number; label: string; onExit: () => void }> = ({ replay, total, label, onExit }) => (
  <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs" style={{ borderTop: '1px solid var(--line)' }} data-testid="replay-controls">
    <button type="button" className="desk-btn" onClick={() => replay.seek(0)} disabled={replay.atStart} aria-label="Restart replay"><SkipBack className="h-4 w-4" /></button>
    <button type="button" className="desk-btn" onClick={() => replay.step(-1)} disabled={replay.atStart} aria-label="Step back"><StepBack className="h-4 w-4" /></button>
    <button type="button" className="desk-btn" onClick={replay.toggle} aria-label={replay.playing ? 'Pause replay' : 'Play replay'}>
      {replay.playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
    </button>
    <button type="button" className="desk-btn" onClick={() => replay.step(1)} disabled={replay.atEnd} aria-label="Step forward"><StepForward className="h-4 w-4" /></button>
    <button type="button" className="desk-btn" onClick={() => replay.seek(total - 1)} disabled={replay.atEnd} aria-label="Jump to end"><SkipForward className="h-4 w-4" /></button>
    <input
      type="range" min={0} max={Math.max(total - 1, 0)} value={replay.index}
      onChange={(e) => replay.seek(Number(e.target.value))}
      className="flex-1 min-w-[120px]" aria-label="Replay position"
    />
    <span className="desk-muted tabular-nums" data-testid="replay-position">{label} · {replay.index + 1}/{total}</span>
    <label className="flex items-center gap-1 desk-muted">
      Speed
      <select value={replay.speed} onChange={(e) => replay.setSpeed(Number(e.target.value))} aria-label="Replay speed" className="desk-btn">
        {REPLAY_SPEEDS.map((s) => <option key={s} value={s}>{s}x</option>)}
      </select>
    </label>
    <button type="button" className="desk-btn" onClick={onExit} aria-label="Exit replay"><X className="h-4 w-4" /></button>
  </div>
);
