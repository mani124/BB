import React from 'react';
import { EarningsPanel } from '../../components/EarningsPanel';
import { PanelFrame } from '../PanelFrame';
import { useConfirmMessage } from '../hooks';
import type { PanelProps } from '../registry';

const EarningsPanelWrapper: React.FC<PanelProps> = () => {
  const confirmFn = useConfirmMessage({ title: 'Square off earnings book?', confirmLabel: 'Square off', danger: true });
  return <PanelFrame title="Earnings" sources={[]}><EarningsPanel confirmFn={confirmFn} /></PanelFrame>;
};

export default EarningsPanelWrapper;
