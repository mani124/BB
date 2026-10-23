import React, { useCallback, useEffect } from 'react';
import { actions, useInFlight } from '../data/actions';
import { appStore, useApp } from '../data/appStore';
import { useConfirm } from '../features/confirm/ConfirmProvider';
import { inr } from '../lib/numbers';

/** Opens the kill-switch confirmation. The action itself only runs after the typed phrase. */
export function useKillSwitchDialog(): () => Promise<void> {
  const confirm = useConfirm();
  return useCallback(async () => {
    const { scanner } = appStore.getState();
    const risk = scanner.paper_portfolio?.risk;
    const open = scanner.paper_portfolio?.active_positions ?? [];
    if (risk?.kill_switch_active) {
      if (await confirm({ title: 'Re-enable new entries?', body: 'The kill switch is on. Releasing it lets the scanner open new positions again.', confirmLabel: 'Re-enable entries' })) {
        await actions.killSwitch(false);
      }
      return;
    }
    const ok = await confirm({
      title: 'Engage the kill switch?',
      danger: true,
      phrase: 'KILL',
      confirmLabel: 'Engage kill switch',
      body: (
        <div className="space-y-2">
          <p>This closes ALL open positions now and pauses new entries until you re-enable them.</p>
          <p>{open.length === 0 ? 'No positions are open.' : `${open.length} open position${open.length === 1 ? '' : 's'} will be closed: ${open.map((p) => p.strike_symbol).join(', ')}.`}</p>
        </div>
      ),
    });
    if (ok) await actions.killSwitch(true);
  }, [confirm]);
}

/** Always rendered in the chrome, never inside a dock panel, so it cannot be closed or hidden. */
export const KillSwitchButton: React.FC<{ compact?: boolean }> = ({ compact }) => {
  const risk = useApp((s) => s.scanner.paper_portfolio?.risk);
  const busy = useInFlight('killSwitch');
  const open = useKillSwitchDialog();
  const active = Boolean(risk?.kill_switch_active);

  // Ctrl+Shift+K opens the confirmation; it never executes anything.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'k') { e.preventDefault(); void open(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <button type="button" data-testid="kill-switch" disabled={busy} onClick={() => void open()}
      className={`desk-btn ${active ? 'accent' : 'danger fill'}`} title={active ? 'Kill switch is ON. Click to re-enable entries.' : 'Kill switch (Ctrl+Shift+K opens the confirmation)'}>
      {active ? 'Re-enable entries' : compact ? 'Kill' : 'Kill switch'}
    </button>
  );
};

export const LossCapMeter: React.FC = () => {
  const risk = useApp((s) => s.scanner.paper_portfolio?.risk);
  if (!risk) return <span className="desk-pill mute">Risk unavailable</span>;
  if (risk.kill_switch_active) return <span className="desk-pill down" role="status">KILL SWITCH ON</span>;
  if (risk.loss_cap_tripped) return <span className="desk-pill down" role="status" title={risk.loss_cap_reason ?? undefined}>Loss cap hit: entries off today</span>;
  if (!(risk.daily_loss_limit > 0)) return <span className="desk-pill warn" role="status">Loss cap off</span>;
  const used = Math.min(100, Math.max(0, (-risk.day_pnl / risk.daily_loss_limit) * 100));
  return (
    <span className="flex items-center gap-2" role="status">
      <span className="desk-num text-xs">Day {inr(risk.day_pnl, { sign: true })} / cap {'−'}{inr(risk.daily_loss_limit)}</span>
      <span role="meter" aria-label="Loss cap used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(used)} aria-valuetext={`${Math.round(used)} percent of the daily loss cap used`}
        className="inline-block align-middle" style={{ width: 56, height: 6, background: 'var(--alt)', border: '1px solid var(--line-strong)' }}>
        <span className="block h-full" style={{ width: `${used}%`, background: used >= 80 ? 'var(--down)' : used >= 50 ? 'var(--warn)' : 'var(--up)' }} />
      </span>
    </span>
  );
};
