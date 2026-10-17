import React, { useState } from 'react';
import { PaperPortfolio, PaperPosition, SetupMode } from '../types';
import { PaperPortfolioView } from './PaperPortfolioView';
import { JournalPanel } from './JournalPanel';
import { TelemetryPanel } from './TelemetryPanel';

export type ReviewTab = 'today' | 'trades' | 'setups' | 'costs' | 'analytics';

const TABS: { id: ReviewTab; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'trades', label: 'Trades' },
  { id: 'setups', label: 'Setups' },
  { id: 'costs', label: 'Costs' },
  { id: 'analytics', label: 'Analytics' },
];

interface ReviewScreenProps {
  portfolio?: PaperPortfolio;
  closedTrades: PaperPosition[];
  onClosePosition: (id: string) => void;
  onToggleAutoTrade: (enabled: boolean) => void;
  onChangeLots: (lots: number) => void;
  onChangeSetupMode: (setup: string, mode: SetupMode) => void;
  onResetPortfolio: () => void;
}

/** After-the-close layout: one sub-tab at a time, scrolling inside the tab body instead of the page. */
export const ReviewScreen: React.FC<ReviewScreenProps> = ({ portfolio, closedTrades, ...handlers }) => {
  const [tab, setTab] = useState<ReviewTab>('today');
  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0">
      <nav className="desk-subtabs" aria-label="Review sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" className="desk-subtab" aria-current={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3">
        {tab === 'analytics' ? (
          <TelemetryPanel />
        ) : (
          <div className="flex flex-col gap-3">
            <PaperPortfolioView
              portfolio={portfolio && { ...portfolio, closed_trades: closedTrades }}
              view={tab}
              hideStrip
              {...handlers}
            />
            {tab === 'today' && <JournalPanel />}
          </div>
        )}
      </div>
    </div>
  );
};
