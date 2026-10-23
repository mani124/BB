import React, { createContext, useContext, useState } from 'react';
import { AlertTriangle, Clock, MoreHorizontal, RefreshCw } from 'lucide-react';
import { sliceStale, STALE_AFTER_MS, useApp, useNow } from '../data/appStore';
import { pollNow } from '../data/pollers';
import type { SliceName } from '../data/types';
import { formatIst } from '../lib/time';

export interface PanelMenuItem { id: string; label: string; run: () => void; disabled?: boolean }

/** Provided by the shell around every panel: Float, Pop out, Move, Maximise, Close... */
export const PanelMenuContext = createContext<PanelMenuItem[] | null>(null);

export interface PanelFrameProps {
  title: string;
  sources: SliceName[];
  actions?: React.ReactNode;
  exportCsv?: () => void;
  onRetry?: () => void;
  children: React.ReactNode;
}

const TITLE_ID_PREFIX = 'panel-title-';
let counter = 0;

export const PanelFrame: React.FC<PanelFrameProps> = ({ title, sources, actions, exportCsv, onRetry, children }) => {
  const [uid] = useState(() => `${TITLE_ID_PREFIX}${++counter}`);
  const metas = useApp((s) => sources.map((n) => s.meta[n]), (a, b) => a.length === b.length && a.every((m, i) => m === b[i]));
  const streamState = useApp((s) => s.stream.state);
  const now = useNow();
  const menu = useContext(PanelMenuContext);
  const [open, setOpen] = useState(false);

  const asOfValues = metas.map((m) => m.asOf).filter((v): v is number => v !== null);
  const asOf = asOfValues.length ? Math.min(...asOfValues) : null;
  const staleSources = sources.filter((n, i) => sliceStale(metas[i], n, now));
  const staleAge = staleSources.length && asOf !== null ? Math.round((now - asOf) / 1000) : 0;
  const stale = staleSources.length > 0;
  const errored = metas.find((m) => m.status === 'error');
  const frozen = streamState === 'stale' || streamState === 'reconnecting';
  const hasThreshold = sources.some((n) => STALE_AFTER_MS[n] !== null);

  return (
    <section role="region" aria-labelledby={uid} className="flex flex-col min-h-0 h-full bg-panel text-fg" data-frozen={frozen ? 'true' : undefined}>
      <div className="flex items-center gap-2 px-2 shrink-0 border-b border-line" style={{ minHeight: 24 }}>
        <h3 id={uid} className="text-xs font-semibold truncate">{title}</h3>
        <span className="ml-auto flex items-center gap-2 text-xs desk-muted">
          {asOf !== null ? (
            <span data-testid="panel-asof">As of {formatIst(asOf)} IST</span>
          ) : hasThreshold || sources.length > 0 ? (
            <span data-testid="panel-asof">No data yet</span>
          ) : null}
          {stale && (
            <span className="desk-pill warn" role="status" data-testid="panel-stale">
              <Clock className="h-3 w-3" aria-hidden /> Stale {staleAge} s
            </span>
          )}
          {frozen && <span className="desk-pill warn nomark" data-testid="panel-frozen">Frozen</span>}
          {actions}
          {exportCsv && <button type="button" className="desk-btn" onClick={exportCsv}>Export CSV</button>}
          {menu && (
            <span className="relative">
              <button type="button" className="desk-btn" aria-haspopup="menu" aria-expanded={open} aria-label={`${title} panel menu`} onClick={() => setOpen((v) => !v)}
                onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}>
                <MoreHorizontal className="h-4 w-4" aria-hidden />
              </button>
              {open && (
                <div role="menu" aria-label={`${title} panel actions`} className="absolute right-0 z-20 mt-1 min-w-[10rem] border border-line-strong bg-panel shadow-md"
                  onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}>
                  {menu.map((item) => (
                    <button key={item.id} type="button" role="menuitem" className="block w-full text-left px-2 py-1 text-xs hover:bg-alt disabled:opacity-50" disabled={item.disabled}
                      onClick={() => { setOpen(false); item.run(); }}>{item.label}</button>
                  ))}
                </div>
              )}
            </span>
          )}
        </span>
      </div>
      {errored && (
        <div className="desk-alert flex items-center gap-2 text-xs" role="alert" data-testid="panel-error">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          <span className="min-w-0 truncate">Could not refresh: {errored.error ?? 'request failed'}. Showing the last good data.</span>
          <button type="button" className="desk-btn ml-auto" onClick={onRetry ?? pollNow}><RefreshCw className="h-3 w-3" aria-hidden /> Retry</button>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto" role="group" aria-label={`${title} content`} tabIndex={0} data-frozen-content={frozen ? 'true' : undefined}>{children}</div>
    </section>
  );
};
