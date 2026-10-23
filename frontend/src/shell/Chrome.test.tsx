import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, within } from '@testing-library/react';

vi.mock('../api/client', () => ({ apiFetch: vi.fn(), getDashboardCapability: () => '', bootstrapDashboardSession: vi.fn() }));
import { apiFetch } from '../api/client';
import { ThemeProvider } from '../context/ThemeContext';
import { DhanAuthProvider } from '../context/DhanAuthContext';
import { ConfirmProvider } from '../features/confirm/ConfirmProvider';
import { appStore, resetAppStore } from '../data/appStore';
import { resetInFlight } from '../data/actions';
import { Chrome } from './Chrome';
import { ModeBanner } from './ModeBanner';
import { StatusBar } from './StatusBar';
import { axeCheck } from '../test/axe';

const fetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;
const res = (body: unknown, status = 200) => ({ status, ok: status < 300, json: async () => body }) as Response;

const wrap = (ui: React.ReactNode) => render(<ThemeProvider><DhanAuthProvider><ConfirmProvider>{ui}</ConfirmProvider></DhanAuthProvider></ThemeProvider>);

beforeEach(() => {
  resetAppStore();
  resetInFlight();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => res({ active_positions: [], closed_trades: [] }));
});

describe('Chrome', () => {
  it('always renders the kill switch, even with an empty store', () => {
    wrap(<Chrome />);
    expect(screen.getByTestId('kill-switch')).toBeInTheDocument();
    expect(screen.getByTestId('mode-pill').textContent).toBe('PAPER');
  });

  it('kill switch click opens the confirm and needs the typed phrase', async () => {
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: { active_positions: [{ id: 'p1', strike_symbol: 'NIFTY 24500 CE' }], risk: { kill_switch_active: false } } as never } }));
    wrap(<Chrome />);
    fireEvent.click(screen.getByTestId('kill-switch'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/NIFTY 24500 CE/)).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: 'Engage kill switch' });
    expect(confirm).toBeDisabled();
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('kill-switch'))).toBe(false);
    fireEvent.change(within(dialog).getByLabelText('Type KILL to confirm'), { target: { value: 'KILL' } });
    await act(async () => { fireEvent.click(confirm); });
    const call = fetchMock.mock.calls.find((c) => String(c[0]) === '/api/paper/kill-switch');
    expect(call).toBeTruthy();
  });

  it('Ctrl+Shift+K opens the dialog and never calls the action', async () => {
    wrap(<Chrome />);
    await act(async () => { fireEvent.keyDown(document, { key: 'K', ctrlKey: true, shiftKey: true }); });
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('kill-switch'))).toBe(false);
  });

  it('shows the release confirm when the switch is already on', async () => {
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: { active_positions: [], risk: { kill_switch_active: true } } as never } }));
    wrap(<Chrome />);
    fireEvent.click(screen.getByTestId('kill-switch'));
    const dialog = await screen.findByRole('dialog');
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Re-enable entries' })); });
    expect(fetchMock.mock.calls.some((c) => String(c[0]) === '/api/paper/kill-switch/release')).toBe(true);
  });

  it('shows the loss cap meter with a text value', () => {
    appStore.setState((s) => ({ scanner: { ...s.scanner, paper_portfolio: { active_positions: [], risk: { kill_switch_active: false, loss_cap_tripped: false, daily_loss_limit: 24000, day_pnl: -6000 } } as never } }));
    wrap(<Chrome />);
    expect(screen.getByRole('meter').getAttribute('aria-valuenow')).toBe('25');
    expect(screen.getByText(/cap/).textContent).toContain('24,000');
  });

  it('toggles density and persists it', () => {
    wrap(<Chrome />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle comfortable density' }));
    expect(appStore.getState().ui.density).toBe('comfortable');
    expect(document.documentElement.dataset.density).toBe('comfortable');
    expect(localStorage.getItem('bb_density')).toBe('comfortable');
  });

  it('has no axe violations', async () => {
    const { container } = wrap(<Chrome />);
    expect(await axeCheck(container)).toEqual([]);
  });
});

describe('ModeBanner', () => {
  it('is hidden for paper', () => {
    const { container } = render(<ModeBanner />);
    expect(container.firstChild).toBeNull();
  });
  it('shows LIVE DRY RUN and LIVE ARMED with distinct text', () => {
    appStore.setState({ live: { status: { mode: 'dry_run' }, orders: [] } });
    const { rerender } = render(<ModeBanner />);
    expect(screen.getByTestId('mode-banner').textContent).toContain('LIVE DRY RUN');
    appStore.setState({ live: { status: { mode: 'live' }, orders: [] } });
    rerender(<ModeBanner />);
    expect(screen.getByTestId('mode-banner').textContent).toContain('LIVE ARMED');
  });
});

describe('StatusBar', () => {
  it('marks a stale source with text', () => {
    appStore.setState((s) => ({ meta: { ...s.meta, stream: { asOf: 1, status: 'stale' }, trades: { asOf: Date.now(), status: 'ready' } } }));
    render(<StatusBar />);
    expect(screen.getByTestId('status-stream').textContent).toContain('Stale');
    expect(screen.getByTestId('status-trades').textContent).toContain('Fresh');
    expect(screen.getByTestId('status-live').textContent).toContain('Waiting');
  });
  it('has no axe violations', async () => {
    const { container } = render(<StatusBar />);
    expect(await axeCheck(container)).toEqual([]);
  });
});
