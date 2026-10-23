import React from 'react';
import { TelemetryPanel } from '../../components/TelemetryPanel';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const TelemetryPanelWrapper: React.FC<PanelProps> = () => (
  <PanelFrame title="Telemetry" sources={['analytics']}><TelemetryPanel /></PanelFrame>
);

export default TelemetryPanelWrapper;
