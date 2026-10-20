import React, { useMemo, useState } from 'react';
import type { ScannerState, Signal } from '../types';
import type { DashboardCandidate, DashboardWatch, WatchBook } from '../types/dashboard';
import { SETUP_FILTERS } from './SetupFilterTabs';
import { setupCode } from './setupCode';

export interface WatchFilters { setup: string; optionType: string; instrumentType: string; timeframe: string }

const bookName: Record<DashboardCandidate['book'], string> = { paper: 'Main', setup16: 'Setup 16', cx: 'Commodities & FX', earnings: 'Earnings' };
const clock = (ts?: string) => (ts?.match(/(\d{2}:\d{2})/)?.[1] ?? '--:--');
const actionable = (stage: string) => ['READY', 'CONFIRMED', 'SIGNAL'].includes(stage);

const Seg: React.FC<{ label: string; value: string; options: [string, string][]; onChange: (v: string) => void }> = ({ label, value, options, onChange }) => (
  <div className="desk-seg" role="group" aria-label={label}>
    {options.map(([key, text]) => <button key={key} type="button" aria-pressed={value === key} onClick={() => onChange(key)}>{text}</button>)}
  </div>
);

interface Props {
  state: ScannerState;
  signals: Signal[];
  loaded: boolean;
  activeSignalIds: Set<string>;
  selectedSignalId: string | null;
  onSelectSignal: (signal: Signal) => void;
  filters: WatchFilters;
  onFilters: (next: Partial<WatchFilters>) => void;
  dashboardWatch: DashboardWatch | null;
  selectedCandidateId: string | null;
  onSelectCandidate: (id: string) => void;
  wsConnected: boolean;
}

/** Left column: what the scanners found (signals) or are still watching (candidates). One list, one selection. */
export const SignalsPane: React.FC<Props> = ({
  state, signals, loaded, activeSignalIds, selectedSignalId, onSelectSignal, filters, onFilters, dashboardWatch, selectedCandidateId, onSelectCandidate, wsConnected,
}) => {
  const [mode, setMode] = useState<'signals' | 'watching'>('signals');
  const [sortBy, setSortBy] = useState<'newest' | 'symbol' | 'setup'>('newest');
  const [bookFilter, setBookFilter] = useState<'all' | WatchBook>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'actionable' | 'waiting'>('all');

  const sorted = useMemo(() => [...signals].sort((x, y) => {
    const confirmation = Number(y.is_confirmed !== false) - Number(x.is_confirmed !== false);
    if (confirmation) return confirmation;
    if (sortBy === 'symbol') return x.symbol.localeCompare(y.symbol);
    if (sortBy === 'setup') return x.setup_type.localeCompare(y.setup_type);
    return y.timestamp.localeCompare(x.timestamp);
  }), [signals, sortBy]);

  const candidates = useMemo(() => (dashboardWatch?.candidates ?? [])
    .filter((c) => bookFilter === 'all' || c.book === bookFilter)
    .filter((c) => statusFilter === 'all' || (statusFilter === 'actionable') === actionable(c.stage))
    .sort((a, b) => Number(!actionable(a.stage)) - Number(!actionable(b.stage)) || (b.observed_at || '').localeCompare(a.observed_at || '')),
  [dashboardWatch, bookFilter, statusFilter]);

  const showing = dashboardWatch ? mode : 'signals';
  const bias = state.market_bias;

  return (
    <div className="flex flex-col min-h-0 h-full" aria-label="Signals and scanner watch">
      <div className="desk-ph">
        <h2 id="signals-title">{showing === 'signals' ? 'Active Strategy Signals' : 'What the scanners are watching'}</h2>
        <span className="desk-pill desk-num ml-auto" title={wsConnected ? 'Real-time ticks, confirm on candle close' : 'Confirm on candle close'}>{showing === 'signals' ? signals.length : candidates.length}</span>
      </div>
      {dashboardWatch && (
        <div className="desk-seg mx-2 my-1.5 self-start" role="group" aria-label="Scanner view">
          <button type="button" aria-pressed={showing === 'signals'} onClick={() => setMode('signals')}>Signals</button>
          <button type="button" aria-pressed={showing === 'watching'} onClick={() => setMode('watching')}>Watching <span className="desk-num">{dashboardWatch.candidates.length}</span></button>
        </div>
      )}
      {showing === 'signals' ? (
        <>
          <div className="px-2 pb-2 flex flex-col gap-1.5" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="flex gap-1.5">
              <select className="desk-input flex-1 min-w-0" value={filters.setup} onChange={(e) => onFilters({ setup: e.target.value })} aria-label="Setup filter">
                {SETUP_FILTERS.map(({ key, label, title }) => <option key={key} value={key} title={title}>{label}</option>)}
              </select>
              <select className="desk-input" style={{ width: 'auto' }} value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)} aria-label="Sort signals">
                <option value="newest">Newest</option><option value="symbol">Symbol</option><option value="setup">Setup</option>
              </select>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Seg label="Side" value={filters.optionType} onChange={(v) => onFilters({ optionType: v })} options={[['ALL', 'Both'], ['CE', 'CE'], ['PE', 'PE']]} />
              <Seg label="Universe" value={filters.instrumentType} onChange={(v) => onFilters({ instrumentType: v })} options={[['ALL', 'All'], ['INDEX', 'Idx'], ['STOCK', 'Stk']]} />
              <Seg label="Timeframe" value={filters.timeframe} onChange={(v) => onFilters({ timeframe: v })} options={[['ALL', 'All'], ['5m', '5m'], ['15m', '15m']]} />
            </div>
            <p className="text-xs desk-muted flex flex-wrap items-center gap-1.5">
              <span>Bias</span>
              <span className={`desk-pill nomark ${bias === 'BULLISH' ? 'up' : bias === 'BEARISH' ? 'down' : ''}`}
                title={bias === 'BULLISH' ? 'PE stock options blocked' : bias === 'BEARISH' ? 'CE stock options blocked' : undefined}>
                {state.active_mode === 'closed' ? 'MARKET CLOSED' : bias || 'NEUTRAL'}
              </span>
              {state.top_bullish?.map((s) => <span key={s} className="desk-pill up nomark desk-num" title="Top bullish (CE)">▲ {s}</span>)}
              {state.top_bearish?.map((s) => <span key={s} className="desk-pill down nomark desk-num" title="Top bearish (PE)">▼ {s}</span>)}
            </p>
          </div>
          <div className="desk-scroll flex-1" tabIndex={0} aria-label="Signals list">
            {!loaded ? (
              <div className="p-3 flex flex-col gap-2" role="status" aria-label="Loading signals">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="desk-skel h-10" />)}</div>
            ) : sorted.length === 0 ? (
              <div className="p-6 text-center">
                <p className="font-semibold mb-1">No active signals match these filters</p>
                <p className="text-xs desk-muted">The scanner cycles every ~8 seconds. Signals appear here as soon as a candle trigger fires.</p>
              </div>
            ) : sorted.map((sig) => {
              const rec = sig.strike_recommendation;
              const unconfirmed = sig.is_confirmed === false;
              return (
                <button key={sig.id} type="button" className="desk-row" aria-pressed={selectedSignalId === sig.id}
                  aria-label={`Inspect ${rec.strike_symbol} ${sig.option_type}`} onClick={() => onSelectSignal(sig)} style={{ borderBottom: '1px solid var(--line)' }}>
                  <span className="min-w-0">
                    <span className="block truncate"><span className="desk-sym">{rec.strike_symbol}</span>{' '}<span className={`desk-side ${sig.option_type === 'CE' ? 'ce' : 'pe'}`}>{sig.option_type}</span></span>
                    <span className="desk-sub">{setupCode(sig.setup_type)} · {sig.timeframe}{unconfirmed ? ' · awaiting candle close' : ''}</span>
                  </span>
                  <span className="text-right shrink-0">
                    <span className="desk-num block">{rec.estimated_option_entry}</span>
                    <span className="desk-sub">{activeSignalIds.has(sig.id) ? 'In portfolio' : clock(sig.timestamp)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <>
          <div className="px-2 pb-2 flex gap-1.5" style={{ borderBottom: '1px solid var(--line)' }}>
            <select className="desk-input flex-1 min-w-0" value={bookFilter} onChange={(e) => setBookFilter(e.target.value as typeof bookFilter)} aria-label="Book filter">
              <option value="all">All books</option><option value="paper">Main scanner</option><option value="setup16">Setup 16</option>
              <option value="cx">Commodities & FX</option><option value="earnings">Earnings</option>
            </select>
            <select className="desk-input flex-1 min-w-0" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)} aria-label="Status filter">
              <option value="all">All states</option><option value="actionable">Ready / signaled</option><option value="waiting">Waiting / blocked</option>
            </select>
          </div>
          <div className="desk-scroll flex-1" tabIndex={0} aria-label="Watched candidates">
            {candidates.length === 0 && <p className="p-4 desk-muted text-sm">No candidates match this filter.</p>}
            {candidates.map((c) => {
              const selected = (selectedCandidateId ?? '') === c.id;
              return (
                <button key={c.id} type="button" className="desk-row" aria-pressed={selected} onClick={() => onSelectCandidate(c.id)}
                  aria-label={`${c.instrument} ${bookName[c.book]} ${c.stage} ${c.is_preview ? 'preview' : 'recorded'}`} style={{ borderBottom: '1px solid var(--line)' }}>
                  <span className="min-w-0">
                    <span className="desk-sym block truncate">{c.instrument}</span>
                    <span className="desk-sub">{bookName[c.book]} · {c.setup || 'Scanner'}</span>
                  </span>
                  <span className="text-right shrink-0">
                    <span className={`desk-pill ${actionable(c.stage) ? 'up' : 'warn'}`}>{c.stage.replace(/_/g, ' ')}</span>
                    <span className="desk-sub">{c.is_preview ? 'Preview' : 'Recorded'}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};
