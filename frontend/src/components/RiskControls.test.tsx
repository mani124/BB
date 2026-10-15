import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { RiskControls } from './RiskControls';
import type { RiskStatus } from '../types';

const base: RiskStatus = {
  daily_loss_limit: 24000, day_pnl: -3000, loss_cap_tripped: false,
  kill_switch_active: false, entries_blocked: false,
};

afterEach(() => vi.restoreAllMocks());

describe('RiskControls', () => {
  it('shows day P&L against the cap', () => {
    render(<RiskControls risk={base} onKillSwitch={vi.fn()} />);
    expect(screen.getByText(/Day .*3,000 \/ cap/)).toBeInTheDocument();
  });

  it('shows the tripped cap and the kill switch states', () => {
    const { rerender } = render(<RiskControls risk={{ ...base, loss_cap_tripped: true, entries_blocked: true }} />);
    expect(screen.getByText(/Loss cap hit/)).toBeInTheDocument();
    rerender(<RiskControls risk={{ ...base, kill_switch_active: true, entries_blocked: true }} onKillSwitch={vi.fn()} />);
    expect(screen.getByText(/KILL SWITCH ON/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /re-enable entries/i })).toBeInTheDocument();
  });

  it('only engages after the user confirms', () => {
    const onKill = vi.fn();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<RiskControls risk={base} onKillSwitch={onKill} />);
    fireEvent.click(screen.getByRole('button', { name: /kill switch/i }));
    expect(onKill).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /kill switch/i }));
    expect(onKill).toHaveBeenCalledWith(true);
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('renders nothing without risk data', () => {
    const { container } = render(<RiskControls />);
    expect(container).toBeEmptyDOMElement();
  });
});
