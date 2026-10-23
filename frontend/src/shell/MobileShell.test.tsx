import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MobileShell } from './MobileShell';
import { ConfirmProvider } from '../features/confirm/ConfirmProvider';
import { appStore, markReady, resetAppStore } from '../data/appStore';
import { PANELS } from '../panels/registry';
import { KillSwitchButton } from './KillSwitch';
import { axeCheck } from '../test/axe';

beforeEach(() => {
  resetAppStore();
  appStore.setState((st) => ({ scanner: { ...st.scanner, paper_portfolio: { active_positions: [], auto_trade_enabled: true, default_lots: 2 } as never } }));
  markReady('scanner'); markReady('portfolio');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', { status: 500 }));
});

const ui = () => <ConfirmProvider><KillSwitchButton compact /><MobileShell /></ConfirmProvider>;

describe('MobileShell', () => {
  it('shows the signals pane first and the bottom nav', async () => {
    render(ui());
    expect(await screen.findByText(/No active signals match/)).toBeTruthy();
    const nav = screen.getByRole('navigation', { name: 'Screen sections' });
    for (const n of ['Signals', 'Detail', 'Positions', 'Tables', 'More']) expect(within(nav).getByRole('button', { name: n })).toBeTruthy();
    expect(within(nav).getByRole('button', { name: 'Signals' }).getAttribute('aria-current')).toBe('page');
  });

  it('switches panes with the nav', async () => {
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Detail' }));
    expect(await screen.findByText('Nothing selected')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Positions' }));
    expect(await screen.findByText(/No open paper positions/)).toBeTruthy();
  });

  it('selecting from Signals or Positions jumps to Detail', async () => {
    render(ui());
    await screen.findByText(/No active signals match/);
    act(() => { appStore.setState({ selection: { kind: 'signal', id: 'S1' } }); });
    expect(screen.getByRole('button', { name: 'Detail' }).getAttribute('aria-current')).toBe('page');
  });

  it('a selection made on the Tables pane does not move the user', async () => {
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Tables' }));
    act(() => { appStore.setState({ selection: { kind: 'position', id: 'P1' } }); });
    expect(screen.getByRole('button', { name: 'Tables' }).getAttribute('aria-current')).toBe('page');
  });

  it('More lists every registered panel and opens one with a back button', async () => {
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'More' }));
    const list = screen.getByLabelText('All panels');
    for (const d of PANELS) expect(within(list).getByRole('button', { name: d.title }), d.id).toBeTruthy();
    fireEvent.click(within(list).getByRole('button', { name: 'Controls' }));
    expect(await screen.findByRole('button', { name: 'Back' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText('All panels')).toBeTruthy();
  });

  it('keeps the kill switch present', () => {
    render(ui());
    expect(screen.getByTestId('kill-switch')).toBeTruthy();
  });

  it('passes axe', async () => {
    const { container } = render(ui());
    await screen.findByText(/No active signals match/);
    expect(await axeCheck(container)).toEqual([]);
  });
});
