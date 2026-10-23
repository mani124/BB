import React from 'react';
import { SessionScreen } from '../../components/SessionScreen';
import { fetchDashboardSession } from '../../api/dashboard';
import { select } from '../../data/selection';
import { istToday } from '../../lib/time';
import { PanelFrame } from '../PanelFrame';
import { usePanelCommands } from '../PanelCommands';
import type { PanelProps } from '../registry';

const SessionPanel: React.FC<PanelProps> = () => {
  const commands = usePanelCommands();
  return (
    <PanelFrame title="Session" sources={['trades']}>
      <SessionScreen initialDay={istToday()} loadSession={fetchDashboardSession}
        onOpenTrade={(id) => { select({ kind: 'trade', id }); commands.openPanel('trades'); }}
        onOpenReview={() => commands.openPanel('journal')} />
    </PanelFrame>
  );
};

export default SessionPanel;
