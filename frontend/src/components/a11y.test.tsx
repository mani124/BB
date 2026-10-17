import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Tabs } from './Tabs';
import { Dialog } from './Dialog';
import { TodaySummary } from './TodaySummary';
import { formatTradeSpan } from './tradeUtils';
import { SignalTable } from './SignalTable';
import type { PaperPosition } from '../types';

const Demo = () => {
  const [v, setV] = useState<'a' | 'b' | 'c'>('a');
  return (
    <Tabs idPrefix="t" label="Demo" tabClassName="x" value={v} onChange={setV}
      items={[{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }, { id: 'c', label: 'C' }]} />
  );
};

describe('Tabs', () => {
  it('moves selection and focus with arrow keys and wraps', () => {
    render(<Demo />);
    const a = screen.getByRole('tab', { name: 'A' });
    expect(a).toHaveAttribute('aria-selected', 'true');
    expect(a).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(a, { key: 'ArrowRight' });
    const b = screen.getByRole('tab', { name: 'B' });
    expect(b).toHaveAttribute('aria-selected', 'true');
    expect(document.activeElement).toBe(b);
    fireEvent.keyDown(b, { key: 'End' });
    expect(screen.getByRole('tab', { name: 'C' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tab', { name: 'C' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'A' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('Dialog', () => {
  it('focuses inside, traps Tab, closes on Escape and returns focus', () => {
    const onClose = vi.fn();
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = render(
      <Dialog label="Test" onClose={onClose}>
        <button>one</button>
        <button>two</button>
      </Dialog>,
    );
    const dlg = screen.getByRole('dialog', { name: 'Test' });
    expect(dlg).toHaveAttribute('aria-modal', 'true');
    expect(document.activeElement).toBe(screen.getByText('one'));
    screen.getByText('two').focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByText('one'));
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText('two'));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});

describe('formatTradeSpan short', () => {
  it('drops seconds only when asked', () => {
    const t = { entry_time: '14:36:00', exit_time: '16:40:12' };
    expect(formatTradeSpan(t)).toBe('14:36:00 → 16:40:12');
    expect(formatTradeSpan(t, { short: true })).toBe('14:36 → 16:40');
  });
});

describe('TodaySummary', () => {
  const t = (id: string, setup: string, net: number): PaperPosition => ({
    id, setup_type: setup, net_pnl: net, gross_pnl: net, pnl_rupees: net,
    exit_datetime: '2026-10-16T14:00:00', entry_datetime: '2026-10-16T13:00:00',
  } as unknown as PaperPosition);
  it('groups the latest session by setup', () => {
    render(<TodaySummary trades={[t('1', 'Setup 5: Option Chart', -500), t('2', 'Setup 5: Option Chart', 200), t('3', 'Setup 1: Squeeze', 900)]} />);
    expect(screen.getByText(/Last session/)).toBeInTheDocument();
    expect(screen.getByText('S5')).toBeInTheDocument();
    expect(screen.getByText('S1')).toBeInTheDocument();
    expect(screen.getByText(/3 trades/)).toBeInTheDocument();
  });
  it('shows an empty state', () => {
    render(<TodaySummary trades={[]} />);
    expect(screen.getByText(/No closed trades yet/)).toBeInTheDocument();
  });
});

describe('SignalTable loading', () => {
  it('renders placeholders, not the empty state', () => {
    render(<SignalTable signals={[]} loading />);
    expect(screen.getByRole('status', { name: 'Loading signals' })).toBeInTheDocument();
    expect(screen.queryByText(/No Active Signals/)).toBeNull();
  });
});
