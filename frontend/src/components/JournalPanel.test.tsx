import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JournalPanel } from './JournalPanel';

const trade = { id: 't1', date: '2026-10-15', strike_symbol: 'NIFTY 25000 CE', setup_type: 'S2', exit_time: '11:30:00', net_pnl: 500, note: '', tag: '' };

describe('JournalPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lists trades and saves a note', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_u, init) =>
      new Response(init?.method === 'PUT' ? '{}' : JSON.stringify([trade]), { status: 200 }));
    render(<JournalPanel />);
    const note = await screen.findByLabelText('Note for NIFTY 25000 CE');
    fireEvent.change(note, { target: { value: 'patient entry' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(JSON.parse((put![1] as RequestInit).body as string)).toEqual({ note: 'patient entry', tag: '' });
    });
  });

  it('shows the empty state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }));
    render(<JournalPanel />);
    expect(await screen.findByText('No closed trades in this range.')).toBeTruthy();
  });
});
