import React from 'react';
import type { RiskStatus } from '../types';

export interface RiskControlsProps {
  risk?: RiskStatus;
  onKillSwitch?: (engage: boolean) => void;
  /** Button only, for narrow headers where the cap chip does not fit. */
  compact?: boolean;
}

const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`;

/** Header chip showing the daily loss cap / kill switch state, plus the kill-switch button. */
export const RiskControls: React.FC<RiskControlsProps> = ({ risk, onKillSwitch, compact = false }) => {
  if (!risk) return null;

  const confirmAndRun = (engage: boolean) => {
    const msg = engage
      ? 'Engage the kill switch? This closes ALL open positions now and pauses new entries until you re-enable them.'
      : 'Re-enable new entries?';
    if (onKillSwitch && window.confirm(msg)) onKillSwitch(engage);
  };

  let chip: React.ReactNode;
  if (risk.kill_switch_active) {
    chip = <span className="desk-pill down" title="All new entries are paused until re-enabled"><span className="desk-dot" />KILL SWITCH ON</span>;
  } else if (risk.loss_cap_tripped) {
    chip = (
      <span className="desk-pill down" title={risk.loss_cap_reason ?? undefined}>
        <span className="desk-dot" />Loss cap hit · entries off today
      </span>
    );
  } else if (risk.daily_loss_limit > 0) {
    chip = (
      <span className="desk-pill" title="Day P&L (realised + open, after charges) vs the daily loss limit">
        Day {inr(risk.day_pnl)} / cap −{inr(risk.daily_loss_limit)}
      </span>
    );
  } else {
    chip = <span className="desk-pill warn">Loss cap off</span>;
  }

  return (
    <span className="flex items-center gap-2" data-testid="risk-controls">
      {!compact && <span role="status" aria-live="polite">{chip}</span>}
      {onKillSwitch && (
        <button
          type="button"
          className={`desk-btn ${risk.kill_switch_active ? 'accent' : 'danger fill'}`}
          onClick={() => confirmAndRun(!risk.kill_switch_active)}
        >
          {risk.kill_switch_active ? 'Re-enable entries' : 'Kill switch'}
        </button>
      )}
    </span>
  );
};
