import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { EarningsPanel } from './EarningsPanel';
import type { EarningsSummary } from '../types';

const summary: EarningsSummary = {
  starting_capital: 500000, realized_net_pnl: 1500, unrealized_net_pnl: -200, equity: 501300, open_positions: 1, closed_trades: 2,
  win_rate: 50, profit_factor: 1.4, avg_win: 2000, avg_loss: -500, total_charges: 320, enabled: false,
  by_mode: {}, last_cycle: { status: 'no_credentials' },
};

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../api/client';

const json = (body: unknown, ok = true) => ({ ok, json: async () => body }) as unknown as Response;

describe('EarningsPanel', () => {
  afterEach(() => vi.mocked(apiFetch).mockReset());

  it('still shows the summary when the candidates preview fails', async () => {
    vi.mocked(apiFetch).mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith('/summary')) return json(summary);
      if (u.endsWith('/candidates')) throw new Error('timeout');
      return json([]);
    });
    render(<EarningsPanel />);
    await waitFor(() => expect(screen.getByTestId('earnings-summary')).toHaveTextContent('Equity₹5,01,300'));
    expect(screen.getByText(/1 of 4 sections could not be refreshed/)).toBeInTheDocument();
    expect(screen.queryByText('Could not reach the server.')).not.toBeInTheDocument();
  });

  it('says the server is unreachable only when every section fails', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('down'));
    render(<EarningsPanel />);
    await waitFor(() => expect(screen.getByText('Could not reach the server.')).toBeInTheDocument());
  });

  it('says entries are off and paper only, and shows the summary', () => {
    render(<EarningsPanel initial={{ summary, positions: [], candidates: [], calendar: [] }} />);
    expect(screen.getByText(/Entries off/)).toBeInTheDocument();
    expect(screen.getByText('Paper only')).toBeInTheDocument();
    expect(screen.getByTestId('earnings-summary')).toHaveTextContent('Equity₹5,01,300');
    expect(screen.getByTestId('earnings-summary')).toHaveTextContent('no_credentials');
  });

  it('lists a calendar row and a skipped candidate with its reason', () => {
    render(<EarningsPanel initial={{
      summary, positions: [],
      candidates: [{ symbol: 'TCS', mode: 'MODE_A_RUNUP', ready: false, code: 'SPREAD_TOO_WIDE', detail: 'CE spread 40%' }],
      calendar: [{ symbol: 'TCS', earnings_date: '2026-10-20', session: 'AMC', sector: 'IT', note: '', effective_session: 'AMC', session_origin: 'inferred' }],
    }} />);
    fireEvent.click(screen.getByRole('tab', { name: /Signals now/ }));
    expect(screen.getByText('SPREAD_TOO_WIDE')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Calendar/ }));
    expect(screen.getByRole('button', { name: 'Remove TCS' })).toBeInTheDocument();
    expect(screen.getByTestId('origin-TCS')).toHaveTextContent('inferred');
  });
});
