import React, { useCallback } from 'react';
import { TradesScreen } from '../../components/TradesScreen';
import { fetchDashboardTradeChart, fetchDashboardTradeDetail } from '../../api/dashboard';
import { actions } from '../../data/actions';
import { useApp } from '../../data/appStore';
import { pollNow } from '../../data/pollers';
import { setFilter, useSelection } from '../../data/selection';
import { tradeMatches } from '../../features/analytics/filter';
import { PanelFrame } from '../PanelFrame';
import { useConfirmMessage } from '../hooks';
import type { PanelProps } from '../registry';

const TradesPanel: React.FC<PanelProps> = () => {
  const allTrades = useApp((s) => s.trades);
  const filter = useApp((s) => s.filter);
  const trades = React.useMemo(() => allTrades.filter((t) => tradeMatches(t, filter)), [allTrades, filter]);
  const selection = useSelection();
  const confirmFn = useConfirmMessage({ title: 'Close position?', confirmLabel: 'Close position', danger: true });
  const closePaper = useCallback(async (sourceId: string) => {
    const r = await actions.closePosition(sourceId);
    if (!r.ok) throw new Error(r.message);
  }, []);
  return (
    <PanelFrame title="Trades" sources={['trades']}>
      {filter && (
        <p className="px-2 py-1 text-xs flex items-center gap-2" role="status" style={{ borderBottom: '1px solid var(--line)' }}>
          <span className="desk-pill">Filtered: {filter.group.replace('_', ' ')} = {filter.key}</span>
          <button type="button" className="desk-btn" onClick={() => setFilter(null)}>Clear filter</button>
        </p>
      )}
      <TradesScreen key={selection?.kind === 'trade' ? selection.id : 'none'} trades={trades}
        loadDetail={fetchDashboardTradeDetail} loadChart={fetchDashboardTradeChart}
        onClosePaper={closePaper} onRefresh={() => pollNow()} initialTradeId={selection?.kind === 'trade' ? selection.id : null}
        confirmFn={confirmFn} />
    </PanelFrame>
  );
};

export default TradesPanel;
