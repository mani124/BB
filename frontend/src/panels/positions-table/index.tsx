import React, { useState } from 'react';
import { useApp } from '../../data/appStore';
import { select, useSelection } from '../../data/selection';
import { formatCurrency, pnlClass } from '../../components/format';
import { setupCode } from '../../components/setupCode';
import { istToday } from '../../lib/time';
import { useTable, type ColumnDef } from '../../lib/useTable';
import type { PaperPosition } from '../../types';
import { PanelFrame } from '../PanelFrame';
import { useConfirmedClose } from '../hooks';
import type { PanelProps } from '../registry';

const target = (p: PaperPosition) => (p.status === 'TARGET_1' ? p.option_target_2 : p.option_target_1);

export const POSITION_COLUMNS: ColumnDef<PaperPosition>[] = [
  { key: 'strike_symbol', label: 'Instrument', sortable: true },
  { key: 'setup', label: 'Setup', get: (p) => setupCode(p.setup_type), sortable: true },
  { key: 'entry_time', label: 'In', sortable: true },
  { key: 'quantity', label: 'Qty', sortable: true },
  { key: 'option_entry', label: 'Entry', sortable: true },
  { key: 'current_option_price', label: 'LTP', sortable: true },
  { key: 'option_sl', label: 'SL', sortable: true },
  { key: 'target', label: 'Target', get: target, sortable: true },
  { key: 'booked', label: 'Booked', get: (p) => p.booked_pnl_rupees ?? 0, sortable: true },
  { key: 'pnl_rupees', label: 'P&L', sortable: true },
  { key: 'est_net_pnl', label: 'Net if closed', sortable: true },
];

const PositionsTablePanel: React.FC<PanelProps> = () => {
  const portfolio = useApp((s) => s.scanner.paper_portfolio);
  const positions = portfolio?.active_positions ?? [];
  const selection = useSelection();
  const close = useConfirmedClose();
  const [chooser, setChooser] = useState(false);
  const table = useTable(positions, {
    columns: POSITION_COLUMNS, storageKey: 'positions-table', csvName: `positions_${istToday()}.csv`,
    onActivate: (p) => select({ kind: 'position', id: p.id }),
  });
  const cell = (p: PaperPosition, key: string): React.ReactNode => {
    switch (key) {
      case 'strike_symbol': return <><span className="desk-sym">{p.strike_symbol}</span>{' '}<span className={`desk-side ${p.option_type === 'CE' ? 'ce' : 'pe'}`}>{p.option_type}</span>{p.status === 'TARGET_1' && <span className="desk-pill up ml-1">T1 hit</span>}</>;
      case 'setup': return <span className="desk-code">{setupCode(p.setup_type)}</span>;
      case 'option_entry': case 'current_option_price': return p[key].toFixed(1);
      case 'option_sl': return <span className="desk-down">{p.option_sl.toFixed(1)}</span>;
      case 'target': return <span className="desk-up">{target(p).toFixed(1)}</span>;
      case 'booked': return <span className={pnlClass(p.booked_pnl_rupees ?? 0)}>{formatCurrency(p.booked_pnl_rupees ?? 0, true)}</span>;
      case 'pnl_rupees': return <span className={`font-semibold ${pnlClass(p.pnl_rupees)}`}>{formatCurrency(p.pnl_rupees, true)}</span>;
      case 'est_net_pnl': return p.est_net_pnl === undefined ? <span className="desk-muted">n/a</span> : <span className={pnlClass(p.est_net_pnl)}>{formatCurrency(p.est_net_pnl, true)}</span>;
      default: return String((p as unknown as Record<string, unknown>)[key] ?? '');
    }
  };
  const numeric = new Set(['quantity', 'option_entry', 'current_option_price', 'option_sl', 'target', 'booked', 'pnl_rupees', 'est_net_pnl']);

  return (
    <PanelFrame title="Positions blotter" sources={['portfolio']} exportCsv={table.exportCsv}
      actions={<button type="button" className="desk-btn" aria-expanded={chooser} onClick={() => setChooser((v) => !v)}>Columns</button>}>
      {chooser && (
        <fieldset className="px-2 py-1 flex flex-wrap gap-3 text-xs" style={{ borderBottom: '1px solid var(--line)' }}>
          <legend className="sr-only">Visible columns</legend>
          {table.allColumns.map((c) => (
            <label key={c.key} className="flex items-center gap-1"><input type="checkbox" checked={!table.hiddenKeys.has(c.key)} onChange={() => table.toggleColumn(c.key)} />{c.label}</label>
          ))}
        </fieldset>
      )}
      {!portfolio ? <div className="p-4 text-sm desk-muted" role="status">Loading portfolio…</div>
        : positions.length === 0 ? <div className="p-6 text-center text-sm desk-muted">No open paper positions.</div>
        : (
          <div className="overflow-x-auto" tabIndex={0} onKeyDown={table.onKeyDown} aria-label="Open positions table, use arrow keys to move and Enter to select">
            <table className="desk-table" aria-label="Open positions">
              <thead><tr>
                {table.columns.map((c) => (
                  <th key={c.key} scope="col" className={numeric.has(c.key) ? 'r' : undefined} aria-sort={table.sort?.key === c.key ? (table.sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                    <button type="button" className="font-semibold" onClick={() => table.setSort(c.key)}>{c.label}{table.sort?.key === c.key ? (table.sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</button>
                  </th>
                ))}
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr></thead>
              <tbody>
                {table.visibleRows.map((p, i) => (
                  <tr key={p.id} data-active={i === table.activeIndex || undefined} aria-selected={selection?.kind === 'position' && selection.id === p.id}
                    className={`cursor-pointer ${selection?.kind === 'position' && selection.id === p.id ? 'desk-selected' : ''}`}
                    style={i === table.activeIndex ? { outline: '1px dashed var(--accent)', outlineOffset: -1 } : undefined}
                    onClick={() => { table.setActiveIndex(i); select({ kind: 'position', id: p.id }); }}>
                    {table.columns.map((c) => <td key={c.key} className={numeric.has(c.key) ? 'r desk-num' : undefined}>{cell(p, c.key)}</td>)}
                    <td className="r"><button type="button" className="desk-btn sm danger" aria-label={`Close ${p.strike_symbol} from table`} onClick={(e) => { e.stopPropagation(); void close(p.id); }}>Close</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </PanelFrame>
  );
};

export default PositionsTablePanel;
