import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ControlScreen } from './ControlScreen';
import type { PaperPortfolio, RiskStatus } from '../types';

const portfolio = { auto_trade_enabled: true, active_positions: [] } as unknown as PaperPortfolio;
const risk = { kill_switch_active: false, entries_blocked: false, daily_loss_limit: 5000, day_pnl: 0 } as RiskStatus;

describe('ControlScreen', () => {
  it('keeps every detailed workspace and manual tools reachable', () => {
    const onOpenView = vi.fn();
    render(<ControlScreen portfolio={portfolio} risk={risk} onPause={vi.fn()} onKillSwitch={vi.fn()}
      onOpenView={onOpenView} onScanNow={vi.fn()} onOpenAccessKey={vi.fn()} settings={<div>Runtime settings panel</div>} />);
    for (const name of ['Review and journal', 'Setup 16', 'Commodities & FX', 'Earnings calendar and IV', 'Runtime settings and audit']) {
      fireEvent.click(screen.getByRole('button', { name }));
    }
    expect(onOpenView).toHaveBeenCalledTimes(5);
    expect(screen.getByText('Runtime settings panel')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Scan now' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dashboard key' })).toBeInTheDocument();
  });

  it('separates reversible paper entry pause from confirmed emergency close', () => {
    const onPause = vi.fn();
    const onKillSwitch = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ControlScreen portfolio={portfolio} risk={risk} onPause={onPause} onKillSwitch={onKillSwitch}
      onOpenView={vi.fn()} onScanNow={vi.fn()} onOpenAccessKey={vi.fn()} settings={null} />);
    expect(screen.getByText(/does not close open positions/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pause paper entries' }));
    expect(onPause).toHaveBeenCalledWith(false);
    expect(window.confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Kill switch' }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('closes ALL open positions'));
    expect(onKillSwitch).toHaveBeenCalledWith(true);
  });
});
