import React, { useCallback } from 'react';
import { TradesScreen } from '../../components/TradesScreen';
import { fetchDashboardTradeChart, fetchDashboardTradeDetail } from '../../api/dashboard';
import { actions } from '../../data/actions';
import { useApp } from '../../data/appStore';
import { pollNow } from '../../data/pollers';
import { useSelection } from '../../data/selection';
import { PanelFrame } from '../PanelFrame';
import { useConfirmMessage } from '../hooks';
import type { PanelProps } from '../registry';

const TradesPanel: React.FC<PanelProps> = () => {
  const trades = useApp((s) => s.trades);
  const selection = useSelection();
  const confirmFn = useConfirmMessage({ title: 'Close position?', confirmLabel: 'Close position', danger: true });
  const closePaper = useCallback(async (sourceId: string) => {
    const r = await actions.closePosition(sourceId);
    if (!r.ok) throw new Error(r.message);
  }, []);
  return (
    <PanelFrame title="Trades" sources={['trades']}>
      <TradesScreen key={selection?.kind === 'trade' ? selection.id : 'none'} trades={trades}
        loadDetail={fetchDashboardTradeDetail} loadChart={fetchDashboardTradeChart}
        onClosePaper={closePaper} onRefresh={() => pollNow()} initialTradeId={selection?.kind === 'trade' ? selection.id : null}
        confirmFn={confirmFn} />
    </PanelFrame>
  );
};

export default TradesPanel;
