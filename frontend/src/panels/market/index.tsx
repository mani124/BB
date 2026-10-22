import React from 'react';
import { IndexHeroRadar } from '../../components/IndexHeroRadar';
import { useApp } from '../../data/appStore';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const MarketPanel: React.FC<PanelProps> = () => {
  const radar = useApp((s) => s.scanner.radar);
  return (
    <PanelFrame title="Market radar" sources={['scanner']}>
      <IndexHeroRadar radar={radar} />
    </PanelFrame>
  );
};

export default MarketPanel;
