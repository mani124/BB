import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render, renderHook, screen, fireEvent } from '@testing-library/react';
import { ReplayControls, sliceSeries, startIndex, useReplay } from './ReplayControls';

const candles = [300, 600, 900, 1200].map((time) => ({ time, open: 1, high: 1, low: 1, close: 1 }));
const series = {
  candles,
  indicators: { ema_9: [300, 600, 900, 1200].map((time) => ({ time, value: time })) },
};

afterEach(() => vi.useRealTimers());

describe('startIndex', () => {
  it('starts on the entry candle, or the first when entry is unknown or earlier', () => {
    expect(startIndex(candles, 650)).toBe(1);
    expect(startIndex(candles, 100)).toBe(0);
    expect(startIndex(candles, null)).toBe(0);
  });
});

describe('sliceSeries', () => {
  it('drops candles and indicator points after the shown candle', () => {
    const s = sliceSeries(series, 1);
    expect(s.candles.map((c) => c.time)).toEqual([300, 600]);
    expect(s.indicators.ema_9.map((p) => p.time)).toEqual([300, 600]);
  });
  it('clamps past the end', () => {
    expect(sliceSeries(series, 99).candles).toHaveLength(4);
  });
});

describe('useReplay', () => {
  it('steps within bounds and pauses on manual step', () => {
    const { result } = renderHook(() => useReplay(4, 1));
    act(() => result.current.toggle());
    expect(result.current.playing).toBe(true);
    act(() => result.current.step(-1));
    expect(result.current.index).toBe(0);
    expect(result.current.playing).toBe(false);
    act(() => result.current.step(-1));
    expect(result.current.index).toBe(0);
    act(() => result.current.seek(99));
    expect(result.current.index).toBe(3);
  });

  it('advances on a timer scaled by speed and stops at the end', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useReplay(4, 0));
    act(() => result.current.toggle());
    act(() => { vi.advanceTimersByTime(800); });
    expect(result.current.index).toBe(1);
    act(() => result.current.setSpeed(4));
    act(() => { vi.advanceTimersByTime(200); });
    expect(result.current.index).toBe(2);
    act(() => { vi.advanceTimersByTime(2000); });
    expect(result.current.index).toBe(3);
    expect(result.current.playing).toBe(false);
  });

  it('restarts from the beginning when played at the end', () => {
    const { result } = renderHook(() => useReplay(3, 2));
    act(() => result.current.toggle());
    expect(result.current.index).toBe(0);
    expect(result.current.playing).toBe(true);
  });
});

describe('ReplayControls', () => {
  it('renders position and wires buttons', () => {
    const Harness = () => {
      const r = useReplay(4, 0);
      return <ReplayControls replay={r} total={4} label="09:20" onExit={() => {}} />;
    };
    render(<Harness />);
    expect(screen.getByTestId('replay-position').textContent).toContain('1/4');
    fireEvent.click(screen.getByLabelText('Step forward'));
    expect(screen.getByTestId('replay-position').textContent).toContain('2/4');
    fireEvent.change(screen.getByLabelText('Replay speed'), { target: { value: '4' } });
    fireEvent.click(screen.getByLabelText('Jump to end'));
    expect(screen.getByTestId('replay-position').textContent).toContain('4/4');
    expect((screen.getByLabelText('Step forward') as HTMLButtonElement).disabled).toBe(true);
  });
});
