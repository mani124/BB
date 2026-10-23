import { useCallback, useMemo } from 'react';
import { createElement } from 'react';
import { actions } from '../data/actions';
import { appStore } from '../data/appStore';
import { useConfirm } from '../features/confirm/ConfirmProvider';
import { formatCurrency } from '../components/format';
import type { PanelProps } from './registry';

/** Close a position only after the shared confirm dialog shows its symbol, P&L and net-if-closed. */
export function useConfirmedClose(): (id: string) => Promise<void> {
  const confirm = useConfirm();
  return useCallback(async (id: string) => {
    const pos = appStore.getState().scanner.paper_portfolio?.active_positions?.find((p) => p.id === id);
    const ok = await confirm({
      title: pos ? `Close ${pos.strike_symbol}?` : 'Close position?',
      confirmLabel: 'Close position',
      danger: true,
      body: pos
        ? createElement('div', { className: 'space-y-1' },
            createElement('p', null, `${pos.strike_symbol} ${pos.option_type}, ${pos.quantity} qty.`),
            createElement('p', null, `Open P&L ${formatCurrency(pos.pnl_rupees, true)}. Net if closed ${pos.est_net_pnl === undefined ? 'not available' : formatCurrency(pos.est_net_pnl, true)}.`))
        : 'Close this position at the current price.',
    });
    if (ok) await actions.closePosition(id);
  }, [confirm]);
}

/** Typed access to a panel's saved params with defaults; updates are merged and persisted into the layout. */
export function usePanelParams<T extends Record<string, unknown>>(props: Pick<PanelProps, 'params' | 'setParams'>, defaults: T): [T, (patch: Partial<T>) => void] {
  const value = useMemo(() => ({ ...defaults, ...props.params }) as T, [props.params, defaults]);
  const update = useCallback((patch: Partial<T>) => props.setParams({ ...value, ...patch }), [props, value]);
  return [value, update];
}

export const pickEnum = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T => (allowed.includes(v as T) ? (v as T) : fallback);

/** Adapter for legacy components that ask `confirmFn(message)`: shows the shared accessible dialog. */
export function useConfirmMessage(opts: { title: string; confirmLabel: string; danger?: boolean }): (message: string) => Promise<boolean> {
  const confirm = useConfirm();
  const { title, confirmLabel, danger } = opts;
  return useCallback((message: string) => confirm({ title, confirmLabel, danger, body: message }), [confirm, title, confirmLabel, danger]);
}
