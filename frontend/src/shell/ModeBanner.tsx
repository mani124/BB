import React from 'react';
import { FlaskConical, Radio } from 'lucide-react';
import { useApp } from '../data/appStore';

export type TradingMode = 'paper' | 'dry_run' | 'live';

export function useTradingMode(): TradingMode {
  const mode = useApp((s) => s.live.status?.mode);
  return mode === 'live' ? 'live' : mode === 'dry_run' ? 'dry_run' : 'paper';
}

/** Always-visible mode strip. Hidden for plain paper trading (the chrome keeps a small PAPER pill). */
export const ModeBanner: React.FC = () => {
  const mode = useTradingMode();
  if (mode === 'paper') return null;
  const live = mode === 'live';
  return (
    <div role="status" data-testid="mode-banner" data-mode={mode}
      className="flex items-center justify-center gap-2 text-xs font-semibold"
      style={{ height: 24, background: live ? 'var(--mode-live)' : 'var(--mode-dry-fill)', color: live ? 'var(--mode-live-fg)' : 'var(--mode-dry)', borderBottom: '1px solid var(--line-strong)' }}>
      {live ? <Radio className="h-3.5 w-3.5 motion-safe:animate-pulse" aria-hidden /> : <FlaskConical className="h-3.5 w-3.5" aria-hidden />}
      <span>{live ? 'LIVE ARMED: real orders are sent to the broker' : 'LIVE DRY RUN: orders are recorded, nothing is sent'}</span>
    </div>
  );
};
