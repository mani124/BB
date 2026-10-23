import React from 'react';
import { SetupStatsPanel } from '../../components/SetupStatsPanel';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const SetupStatsPanelWrapper: React.FC<PanelProps> = () => (
  <PanelFrame title="Setup statistics" sources={['analytics']}><SetupStatsPanel /></PanelFrame>
);

export default SetupStatsPanelWrapper;
