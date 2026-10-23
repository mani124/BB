import React from 'react';
import { CostPanel } from '../../components/CostPanel';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const CostsPanel: React.FC<PanelProps> = () => (
  <PanelFrame title="Costs" sources={['analytics']}><CostPanel /></PanelFrame>
);

export default CostsPanel;
