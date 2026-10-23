import React from 'react';
import { LiveRoutingPanel } from '../../components/LiveRoutingPanel';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const LivePanel: React.FC<PanelProps> = () => (
  <PanelFrame title="Live routing" sources={['live']}><LiveRoutingPanel /></PanelFrame>
);

export default LivePanel;
