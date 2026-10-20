import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SessionScreen } from './SessionScreen';
import type { DashboardSession } from '../types/dashboard';

const session: DashboardSession = {
  day: '2026-10-19', timezone: 'Asia/Kolkata',
  by_book: [
    { book: 'paper', display_book: 'Main + Setup 16', entries: 1, exits: 0, realized_net: null, estimated_net: 30 },
    { book: 'cx', display_book: 'Commodities & FX', entries: 0, exits: 1, realized_net: -60, estimated_net: null },
  ],
  events: [
    { id: 'decision:1', at: '2026-10-19T09:01:00+05:30', type: 'decision', book: 'paper', trade_id: null, instrument: 'NIFTY', title: 'SKIPPED · NIFTY', reason: 'SPREAD', metrics: { spread: 9 }, evidence_id: 'decision:1', evidence_state: 'recorded' },
    { id: 'entry:paper:p1', at: '2026-10-19T09:10:00+05:30', type: 'entry', book: 'paper', trade_id: 'paper:p1', instrument: 'NIFTY CE', title: 'Entry · NIFTY CE', reason: null, metrics: {}, evidence_id: null, evidence_state: 'unavailable' },
  ],
  observations: [{ id: 'skip:paper:SPREAD', title: '2 skips: SPREAD', detail: 'paper recorded two skips', event_ids: ['decision:1'] }],
};

describe('SessionScreen', () => {
  it('shows factual counts, selects timeline evidence, and opens the linked trade', async () => {
    const openTrade = vi.fn();
    render(<SessionScreen initialDay="2026-10-19" loadSession={async () => session} onOpenTrade={openTrade} />);
    expect(await screen.findByRole('button', { name: /SKIPPED · NIFTY/i })).toBeInTheDocument();
    expect(screen.getByText('2 skips: SPREAD')).toBeInTheDocument();
    expect(screen.getByText('Current estimate ₹30')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Entry · NIFTY CE/i }));
    expect(screen.getByText(/No saved decision for this older trade/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'View trade and chart' }));
    expect(openTrade).toHaveBeenCalledWith('paper:p1');
  });

  it('uses a selected day and describes days without events', async () => {
    const loadSession = vi.fn().mockResolvedValue({ ...session, events: [], observations: [], by_book: [] });
    render(<SessionScreen initialDay="2026-10-19" loadSession={loadSession} onOpenTrade={vi.fn()} />);
    expect(await screen.findByText(/No recorded session events/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Session date'), { target: { value: '2026-10-18' } });
    expect(loadSession).toHaveBeenCalledWith('2026-10-18');
  });
});
