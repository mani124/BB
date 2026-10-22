import React from 'react';
import { useApp } from '../../data/appStore';
import { formatIst, istToday } from '../../lib/time';
import { points } from '../../lib/numbers';
import { useTable, type ColumnDef } from '../../lib/useTable';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

type Order = Record<string, unknown>;
export const ORDER_COLUMNS: ColumnDef<Order>[] = [
  { key: 'ts', label: 'Time (IST)', sortable: true }, { key: 'mode', label: 'Mode', sortable: true }, { key: 'side', label: 'Side', sortable: true },
  { key: 'trading_symbol', label: 'Instrument', sortable: true }, { key: 'qty', label: 'Qty', sortable: true }, { key: 'order_type', label: 'Type', sortable: true },
  { key: 'price', label: 'Price', sortable: true }, { key: 'status', label: 'Status', sortable: true }, { key: 'filled_qty', label: 'Filled', sortable: true },
  { key: 'avg_price', label: 'Avg price', sortable: true }, { key: 'message', label: 'Message' },
];

export const statusTone = (status: unknown): 'up' | 'down' | 'warn' | 'mute' => {
  const s = String(status ?? '').toUpperCase();
  if (['TRADED', 'FILLED', 'COMPLETE', 'COMPLETED'].includes(s)) return 'up';
  if (['REJECTED', 'FAILED', 'CANCELLED', 'CANCELED', 'EXPIRED', 'ERROR'].includes(s)) return 'down';
  if (['BLOCKED', 'PENDING', 'OPEN', 'PARTIAL', 'TRANSIT', 'PLACED'].includes(s)) return 'warn';
  return 'mute';
};

const OrdersPanel: React.FC<PanelProps> = () => {
  const orders = useApp((s) => s.live.orders) as Order[];
  const mode = useApp((s) => (s.live.status as { mode?: string } | null)?.mode);
  const table = useTable(orders, { columns: ORDER_COLUMNS, storageKey: 'orders', csvName: `orders_${istToday()}.csv`, initialSort: { key: 'ts', dir: 'desc' } });
  const cell = (o: Order, key: string): React.ReactNode => {
    switch (key) {
      case 'ts': return o.ts ? formatIst(String(o.ts), 'datetime') : '';
      case 'status': return <span className={`desk-pill ${statusTone(o.status)}`}>{String(o.status ?? '')}</span>;
      case 'price': case 'avg_price': return typeof o[key] === 'number' ? points(o[key] as number, 2) : '';
      default: return String(o[key] ?? '');
    }
  };
  return (
    <PanelFrame title="Orders and fills" sources={['live']} exportCsv={table.exportCsv}>
      {orders.length === 0 ? (
        <p className="p-6 text-center text-sm desk-muted">{mode && mode !== 'off' ? 'No orders yet.' : 'Live routing is off, so there are no routed orders.'}</p>
      ) : (
        <div className="overflow-x-auto" tabIndex={0} onKeyDown={table.onKeyDown} aria-label="Orders table">
          <table className="desk-table" aria-label="Orders">
            <thead><tr>{table.columns.map((c) => (
              <th key={c.key} scope="col" aria-sort={table.sort?.key === c.key ? (table.sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                <button type="button" className="font-semibold" onClick={() => table.setSort(c.key)}>{c.label}{table.sort?.key === c.key ? (table.sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</button>
              </th>))}</tr></thead>
            <tbody>{table.visibleRows.map((o, i) => <tr key={String(o.id ?? i)}>{table.columns.map((c) => <td key={c.key}>{cell(o, c.key)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </PanelFrame>
  );
};

export default OrdersPanel;
