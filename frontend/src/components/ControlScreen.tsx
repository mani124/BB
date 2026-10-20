import React from 'react';
import type { PaperPortfolio, RiskStatus } from '../types';
import { RiskControls } from './RiskControls';

export type ControlView = 'legacy-review' | 'setup16' | 'cx' | 'earnings' | 'settings';

interface Props {
  portfolio?: PaperPortfolio;
  risk?: RiskStatus | null;
  onPause: (enabled: boolean) => void;
  onKillSwitch: (engage: boolean) => void;
  onOpenView: (view: ControlView) => void;
  onScanNow: () => void;
  onOpenAccessKey: () => void;
  settings?: React.ReactNode;
}

const views: { id: ControlView; title: string; detail: string }[] = [
  { id: 'legacy-review', title: 'Review and journal', detail: 'Today, trade history, setups, costs and analytics' },
  { id: 'setup16', title: 'Setup 16', detail: 'Contract stages, mode and strategy detail' },
  { id: 'cx', title: 'Commodities & FX', detail: 'Candidates, positions and book controls' },
  { id: 'earnings', title: 'Earnings calendar and IV', detail: 'Candidates, positions, calendar and IV import' },
  { id: 'settings', title: 'Runtime settings and audit', detail: 'Limits, routing, alerts and recent setting changes' },
];

export const ControlScreen: React.FC<Props> = ({ portfolio, risk, onPause, onKillSwitch, onOpenView, onScanNow, onOpenAccessKey, settings }) => (
  <div className="flex flex-col gap-2 lg:overflow-y-auto min-w-0 pb-4">
    <header><h1 className="text-xl font-semibold">Control</h1>
      <p className="desk-muted text-sm">Entry permissions, emergency action and all book settings.</p></header>
    <div className="grid lg:grid-cols-2 gap-3">
      <section className="desk-panel p-3">
        <p className="desk-label">Paper scanner · automatic entries</p>
        <h2 style={{ fontFamily: 'var(--sans)' }} className={`desk-hero md mt-1 ${portfolio ? (portfolio.auto_trade_enabled ? 'desk-up' : 'desk-down') : 'desk-muted'}`}>{portfolio ? (portfolio.auto_trade_enabled ? 'Entries allowed' : 'Entries paused') : 'Entry state unavailable'}</h2>
        <p className="desk-muted text-xs mt-1">Pausing stops new automatic entries in the paper scanner, including Setup 16. It does not close open positions. Commodities, FX and earnings have separate controls below.</p>
        <button type="button" className="desk-btn solid mt-3" disabled={!portfolio}
          onClick={() => onPause(!portfolio?.auto_trade_enabled)}>
          {portfolio?.auto_trade_enabled ? 'Pause paper entries' : 'Resume paper entries'}
        </button>
      </section>
      <section className="desk-panel p-3">
        <p className="desk-label">Emergency action</p>
        <h2 style={{ fontFamily: 'var(--sans)' }} className="desk-hero md mt-1">Kill switch</h2>
        <p className="desk-muted text-xs mt-1">Engaging the kill switch closes all applicable open positions now and blocks new entries. Review the confirmation before using it.</p>
        <div className="mt-3"><RiskControls risk={risk ?? undefined} onKillSwitch={onKillSwitch} /></div>
      </section>
    </div>
    <section className="desk-panel p-3">
      <h2 className="font-semibold">Detailed workspaces</h2>
      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2 mt-3">{views.map((view) => <button key={view.id} type="button"
        onClick={() => onOpenView(view.id)} aria-label={view.title}
        className="desk-control-link text-left rounded-md px-3 py-2">
        <strong className="block text-base">{view.title} <span aria-hidden="true">↗</span></strong>
        <span className="desk-muted text-sm block mt-1">{view.detail}</span>
      </button>)}</div>
    </section>
    <section className="desk-panel p-3 flex flex-wrap items-center gap-2">
      <div className="mr-auto"><h2 className="font-semibold">Manual tools and access</h2><p className="desk-muted text-sm">A manual scan checks current candidates; the dashboard key controls access to protected actions.</p></div>
      <button type="button" className="desk-btn" onClick={onScanNow}>Scan now</button>
      <button type="button" className="desk-btn" onClick={onOpenAccessKey}>Dashboard key</button>
    </section>
    {settings && (
      <section aria-label="Runtime settings" className="min-w-0">
        <h2 className="font-semibold mb-1">Runtime settings</h2>
        {settings}
      </section>
    )}
  </div>
);
