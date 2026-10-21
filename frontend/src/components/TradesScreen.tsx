import React, { useEffect, useState } from 'react';
import type { DashboardBook, DashboardChart, DashboardTrade, DashboardTradeDetail } from '../types/dashboard';
import { TradeQueue } from './TradeQueue';
import { TradeDetail } from './TradeDetail';

interface Props {
  trades: DashboardTrade[];
  loadDetail: (trade: DashboardTrade) => Promise<DashboardTradeDetail>;
  loadChart: (trade: DashboardTrade) => Promise<DashboardChart>;
  onClosePaper: (sourceId: string) => Promise<void>;
  onRefresh: () => void | Promise<void>;
  initialTradeId?: string | null;
}

export const TradesScreen: React.FC<Props> = ({ trades, loadDetail, loadChart, onClosePaper, onRefresh, initialTradeId }) => {
  const [query, setQuery] = useState('');
  const [book, setBook] = useState<'all' | DashboardBook>('all');
  const [status, setStatus] = useState<'all' | 'OPEN' | 'CLOSED'>('all');
  const [day, setDay] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(initialTradeId ?? null);
  const [phoneDetailOpen, setPhoneDetailOpen] = useState(Boolean(initialTradeId));
  const [detail, setDetail] = useState<DashboardTradeDetail | null>(null);
  const [chart, setChart] = useState<DashboardChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [closing, setClosing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const filtered = trades.filter((trade) => {
    const search = `${trade.instrument} ${trade.setup} ${trade.display_book}`.toLowerCase();
    return (book === 'all' || trade.book === book)
      && (status === 'all' || (status === 'OPEN' ? trade.status === 'OPEN' || trade.status === 'TARGET_1' : trade.status !== 'OPEN' && trade.status !== 'TARGET_1'))
      && (!day || trade.opened_at?.slice(0, 10) === day)
      && search.includes(query.trim().toLowerCase());
  });
  const selected = filtered.find((trade) => trade.id === selectedId) ?? filtered[0] ?? null;

  useEffect(() => {
    let alive = true;
    setDetail(null);
    setChart(null);
    setActionError(null);
    if (!selected) return;
    setLoading(true);
    Promise.all([loadDetail(selected), loadChart(selected)])
      .then(([nextDetail, nextChart]) => { if (alive) { setDetail(nextDetail); setChart(nextChart); } })
      .catch((error: unknown) => { if (alive) setActionError(error instanceof Error ? error.message : 'Trade detail failed'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [selected?.id, loadDetail, loadChart]);

  const closeSelected = async () => {
    if (!selected || selected.book !== 'paper') return;
    if (!window.confirm(`Close ${selected.instrument} in ${selected.display_book}? This exits the position now.`)) return;
    setClosing(true);
    setActionError(null);
    try {
      await onClosePaper(selected.source_id);
      await onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Close failed');
    } finally {
      setClosing(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 lg:flex-1 lg:min-h-0">
      <h1 className="sr-only">Trades</h1>
      <div className="desk-panel p-3 flex flex-wrap items-end gap-3" role="search" aria-label="Trade filters">
        <input className="desk-input" style={{ flex: '1 1 14rem', width: 'auto' }} aria-label="Search trades" placeholder="Search instrument or setup" value={query} onChange={(event) => setQuery(event.target.value)} />
        <label className="text-xs desk-muted flex flex-col gap-1">Trade book <select className="desk-input" style={{ width: 'auto' }} value={book} onChange={(event) => setBook(event.target.value as typeof book)}>
          <option value="all">All books</option><option value="paper">Main scanner</option><option value="cx">Commodities & FX</option><option value="earnings">Earnings</option>
        </select></label>
        <label className="text-xs desk-muted flex flex-col gap-1">Trade status <select className="desk-input" style={{ width: 'auto' }} value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
          <option value="all">All</option><option value="OPEN">Open</option><option value="CLOSED">Closed</option>
        </select></label>
        <label className="text-xs desk-muted flex flex-col gap-1">Entry date <input className="desk-input" style={{ width: 'auto' }} type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>
        <span className="desk-muted text-sm ml-auto pb-2 desk-num">{filtered.length} {filtered.length === 1 ? 'trade' : 'trades'}</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(440px,1fr)_minmax(0,1.3fr)] gap-3 lg:min-h-0 lg:flex-1">
        <section className={`desk-panel overflow-hidden lg:overflow-y-auto ${phoneDetailOpen ? 'hidden lg:block' : ''}`} aria-label="Trade queue">
          <TradeQueue trades={filtered} selectedId={selected?.id ?? null} onSelect={(id) => { setSelectedId(id); setPhoneDetailOpen(true); }} />
        </section>
        <div className={`lg:overflow-y-auto lg:pr-1 ${phoneDetailOpen ? '' : 'hidden lg:block'}`}>
          <button type="button" className="desk-btn mb-3 lg:hidden" aria-label="Back to trades" onClick={() => setPhoneDetailOpen(false)}>← Back to trades</button>
          {selected ? <TradeDetail trade={selected} detail={detail} chart={chart} loading={loading} onClose={closeSelected} closing={closing} actionError={actionError} />
            : <section className="desk-panel p-5 desk-muted">Select a trade or adjust the filters.</section>}
        </div>
      </div>
    </div>
  );
};
