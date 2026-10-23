import React from 'react';
import { PositionsPane } from '../../components/PositionsPane';
import { actions } from '../../data/actions';
import { useApp } from '../../data/appStore';
import { liveTrades } from '../../components/format';
import { select, useSelection } from '../../data/selection';
import { PanelFrame } from '../PanelFrame';
import { useConfirmedClose } from '../hooks';
import type { PanelProps } from '../registry';

const PositionsPanel: React.FC<PanelProps> = () => {
  const portfolio = useApp((s) => s.scanner.paper_portfolio);
  const closed = useApp((s) => s.closedTrades);
  const selection = useSelection();
  const close = useConfirmedClose();
  return (
    <PanelFrame title="Open positions" sources={['portfolio', 'closedTrades']}>
      <PositionsPane portfolio={portfolio} closedTrades={liveTrades(closed)} selectedId={selection?.kind === 'position' ? selection.id : null}
        onSelect={(p) => select({ kind: 'position', id: p.id })} onClosePosition={(id) => { void close(id); }}
        onToggleAutoTrade={(enabled) => { void actions.toggleAutoTrade(enabled); }} />
    </PanelFrame>
  );
};

export default PositionsPanel;
