import React from 'react';
import { PositionChartModal } from '../../components/PositionChartModal';
import { useApp } from '../../data/appStore';
import { clearSelection, resolveSelection, useSelection } from '../../data/selection';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

/** Chart of the selected position (or the first open one), filling the panel. */
const ChartPanel: React.FC<PanelProps> = () => {
  const state = useApp((s) => s);
  const selection = useSelection();
  const { position } = resolveSelection(state, selection);
  return (
    <PanelFrame title="Chart" sources={['scanner', 'portfolio']}>
      {position
        ? <PositionChartModal key={position.id} position={position} inline onClose={() => clearSelection()} />
        : <p className="p-4 text-sm desk-muted">Select an open position to see its chart.</p>}
    </PanelFrame>
  );
};

export default ChartPanel;
