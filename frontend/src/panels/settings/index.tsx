import React, { createElement } from 'react';
import { SettingsPanel } from '../../components/SettingsPanel';
import { useConfirm } from '../../features/confirm/ConfirmProvider';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const SettingsPanelWrapper: React.FC<PanelProps> = () => {
  const confirm = useConfirm();
  const confirmRiskChanges = (changes: { label: string; from: string; to: string }[]) => confirm({
    title: 'Change risk settings?',
    confirmLabel: 'Save changes',
    danger: true,
    body: createElement('ul', { className: 'space-y-1' }, changes.map((c) => createElement('li', { key: c.label }, `${c.label}: ${c.from} → ${c.to}`))),
  });
  return <PanelFrame title="Settings" sources={[]}><SettingsPanel confirmRiskChanges={confirmRiskChanges} /></PanelFrame>;
};

export default SettingsPanelWrapper;
