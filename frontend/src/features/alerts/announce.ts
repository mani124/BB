import { useEffect, useRef } from 'react';
import { useApp } from '../../data/appStore';

interface SignalLike { id: string; symbol: string; option_type: string; is_confirmed?: boolean }
interface RiskLike { kill_switch_active?: boolean; loss_cap_tripped?: boolean }

/** Text for newly confirmed signals; `seen` is updated in place. Returns '' when nothing is new. */
export function newSignalMessage(seen: Set<string>, signals: SignalLike[]): string {
  const fresh = signals.filter((x) => x.is_confirmed !== false && !seen.has(x.id));
  fresh.forEach((x) => seen.add(x.id));
  if (fresh.length === 0) return '';
  const f = fresh[0];
  return `New signal: ${f.symbol} ${f.option_type}${fresh.length > 1 ? ` and ${fresh.length - 1} more` : ''}`;
}

export function riskMessage(risk: RiskLike | null | undefined): string {
  if (risk?.kill_switch_active) return 'Kill switch is on. New entries are paused.';
  if (risk?.loss_cap_tripped) return 'Daily loss cap hit. New entries are off for today.';
  return '';
}

/** Feeds the polite live region: new signals (not the ones present at load) and risk-state changes. */
export function useAnnouncements(announce: (message: string) => void): void {
  const signals = useApp((s) => s.scanner.signals) as SignalLike[];
  const loaded = useApp((s) => s.scanner.last_scan_time !== undefined && s.scanner.last_scan_time !== null && s.scanner.last_scan_time !== '');
  const risk = useApp((s) => s.scanner.paper_portfolio?.risk) as RiskLike | undefined;
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    const confirmed = (signals ?? []).filter((x) => x.is_confirmed !== false);
    if (seen.current === null) {
      if (loaded) seen.current = new Set(confirmed.map((x) => x.id));
      return;
    }
    const msg = newSignalMessage(seen.current, signals ?? []);
    if (msg) announce(msg);
  }, [signals, loaded, announce]);
  useEffect(() => {
    const msg = riskMessage(risk);
    if (msg) announce(msg);
  }, [risk?.kill_switch_active, risk?.loss_cap_tripped, announce]); // eslint-disable-line react-hooks/exhaustive-deps
}
