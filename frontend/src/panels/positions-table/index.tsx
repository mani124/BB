import React, { useState } from 'react';
import { useApp } from '../../data/appStore';
import { select, useSelection } from '../../data/selection';
import { formatCurrency, pnlClass } from '../../components/format';
import { setupCode } from '../../components/setupCode';
import { istToday } from '../../lib/time';
import { useTable, type ColumnDef } from '../../lib/useTable';
import type { PaperPosition } from '../../types';
import { PanelFrame } from '../PanelFrame';
import { ColumnChooser, ColumnsButton, DataTable } from '../DataTable';
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
      actions={<ColumnsButton open={chooser} onToggle={() => setChooser((v) => !v)} />}>
      {chooser && <ColumnChooser table={table} />}
      {!portfolio ? <div className="p-4 text-sm desk-muted" role="status">Loading portfolio…</div>
        : positions.length === 0 ? <div className="p-6 text-center text-sm desk-muted">No open paper positions.</div>
        : (
          <DataTable table={table} label="Open positions" numeric={numeric} rowKey={(p) => p.id} renderCell={(p, c) => cell(p, c.key)}
            isSelected={(p) => selection?.kind === 'position' && selection.id === p.id} onRowClick={(p) => select({ kind: 'position', id: p.id })}
            trailing={{ header: 'Actions', render: (p) => <button type="button" className="desk-btn sm danger" aria-label={`Close ${p.strike_symbol} from table`} onClick={(e) => { e.stopPropagation(); void close(p.id); }}>Close</button> }} />
        )}
    </PanelFrame>
  );
};

export default PositionsTablePanel;
