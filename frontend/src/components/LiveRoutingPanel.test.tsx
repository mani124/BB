import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { LiveRoutingPanel } from './LiveRoutingPanel';
import type { LiveStatus } from '../types';

const base: LiveStatus = {
  mode: 'off', halted: '', broker: 'definedge', broker_session: true, env_confirmed: true, armed: false,
  preconditions: [], entries_today: 0, orders_today: 0, realized_today: 0, positions: [],
};

afterEach(() => vi.restoreAllMocks());

describe('LiveRoutingPanel', () => {
  it('shows the mode and cannot go live without the typed code and phrase', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) =>
      String(url).endsWith('/arm')
        ? new Response(JSON.stringify({ code: '123456', expires_in: 120, phrase: 'ENABLE LIVE TRADING' }), { status: 200 })
        : String(url).includes('/orders')
          ? new Response('[]', { status: 200 })
          : new Response(JSON.stringify(base), { status: 200 }));
    render(<LiveRoutingPanel initial={base} initialOrders={[]} />);
    expect(screen.getByRole('status')).toHaveTextContent('Off');
    fireEvent.click(screen.getByRole('button', { name: 'Go live…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Enable live trading' });
    expect(dialog).toBeInTheDocument();
    const enable = screen.getByRole('button', { name: 'Enable live' });
    expect(enable).toBeDisabled();
    fireEvent.change(screen.getByLabelText('One-time code'), { target: { value: '123456' } });
    expect(enable).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'ENABLE LIVE TRADING' } });
    expect(enable).toBeEnabled();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/enable'))).toBe(false);
  });

  it('shows a halt and offers resume', () => {
    render(<LiveRoutingPanel initial={{ ...base, mode: 'live', halted: 'POSITION_MISMATCH' }} initialOrders={[]} />);
    expect(screen.getByText('Halted: POSITION_MISMATCH')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume after check' })).toBeInTheDocument();
  });

  it('logs in with the typed TOTP only when it has six digits', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ broker_session: true }), { status: 200 }));
    render(<LiveRoutingPanel initial={base} initialOrders={[]} />);
    const btn = screen.getByRole('button', { name: 'Log in to broker' });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Broker TOTP'), { target: { value: '123456' } });
    fireEvent.click(btn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/live/broker/login');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ totp: '123456' });
  });
});
