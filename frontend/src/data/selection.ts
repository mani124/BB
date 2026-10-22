import { useEffect, useRef } from 'react';
import type { PaperPosition, Signal } from '../types';
import type { DashboardCandidate, DashboardTrade } from '../types/dashboard';
import { appStore, useApp } from './appStore';
import type { AppState, Selection } from './types';

export type { Selection };

export function select(sel: Selection): void {
  appStore.setState({ selection: sel, selectionDismissed: false });
}

/** Empty the Focus panel and keep it empty (no default selection) until something is chosen. */
export function clearSelection(): void {
  appStore.setState({ selection: null, selectionDismissed: true });
}

export function setFilter(filter: AppState['filter']): void {
  appStore.setState({ filter });
}

/** With nothing chosen, the first open position, else the newest signal. */
export function defaultSelection(state: AppState): Selection {
  const pos = state.scanner.paper_portfolio?.active_positions?.[0];
  if (pos) return { kind: 'position', id: pos.id };
  const sig = state.scanner.signals[0];
  return sig ? { kind: 'signal', id: sig.id } : null;
}

export function effectiveSelection(state: AppState): Selection {
  if (state.selection) return state.selection;
  return state.selectionDismissed ? null : defaultSelection(state);
}

export interface Resolved {
  signal?: Signal;
  position?: PaperPosition;
  candidate?: DashboardCandidate;
  trade?: DashboardTrade;
}

/** Looks the selection up by id in the current data, so a refreshed snapshot never leaves a stale copy on screen. */
export function resolveSelection(state: AppState, sel: Selection = effectiveSelection(state)): Resolved {
  if (!sel) return {};
  switch (sel.kind) {
    case 'signal': return { signal: state.scanner.signals.find((s) => s.id === sel.id) };
    case 'position': return { position: state.scanner.paper_portfolio?.active_positions?.find((p) => p.id === sel.id) };
    case 'candidate': return { candidate: state.watch?.candidates.find((c) => c.id === sel.id) };
    case 'trade': return { trade: state.trades.find((t) => t.id === sel.id) };
  }
}

const sameSel = (a: Selection, b: Selection) => a?.kind === b?.kind && a?.id === b?.id;

/** The selection a panel should show. A pinned panel keeps the selection it had when pinned and ignores later changes. */
export function useSelection(opts: { pinned?: boolean; pinnedTo?: Selection } = {}): Selection {
  const live = useApp(effectiveSelection, sameSel);
  const frozen = useRef<Selection | undefined>(undefined);
  if (opts.pinned) {
    if (frozen.current === undefined) frozen.current = opts.pinnedTo !== undefined ? opts.pinnedTo : live;
  } else {
    frozen.current = undefined;
  }
  useEffect(() => { if (!opts.pinned) frozen.current = undefined; }, [opts.pinned]);
  return opts.pinned ? (frozen.current ?? null) : live;
}
