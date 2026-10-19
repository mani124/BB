import React, { useEffect, useState } from 'react';
import type { DashboardSession, DashboardSessionEvent } from '../types/dashboard';
import { SessionTimeline } from './SessionTimeline';
import { SessionInsights } from './SessionInsights';

interface Props {
  initialDay: string;
  loadSession: (day: string) => Promise<DashboardSession>;
  onOpenTrade: (id: string) => void;
  onOpenReview?: () => void;
}

const money = (value: number) => `₹${value.toLocaleString('en-IN')}`;

export const SessionScreen: React.FC<Props> = ({ initialDay, loadSession, onOpenTrade, onOpenReview }) => {
  const [day, setDay] = useState(initialDay);
  const [data, setData] = useState<DashboardSession | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    loadSession(day).then((result) => { if (alive) { setData(result); setSelectedId(result.events[0]?.id ?? null); } })
      .catch((err: unknown) => { if (alive) setError(err instanceof Error ? err.message : 'Session unavailable'); });
    return () => { alive = false; };
  }, [day, loadSession]);
  const selected: DashboardSessionEvent | undefined = data?.events.find((event) => event.id === selectedId);
  return <div className="flex flex-col gap-3 lg:flex-1 lg:min-h-0">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold">Session</h1><p className="desk-muted text-sm">What the system recorded, in India time. Select an event to inspect its evidence.</p></div>
      <label className="text-xs desk-muted">Session date <input aria-label="Session date" type="date" className="desk-input ml-2" value={day} onChange={(event) => setDay(event.target.value)} /></label>
    </header>
    {error && <p role="alert" className="desk-alert p-3">{error}</p>}
    {!data && !error && <p className="desk-muted">Loading recorded session…</p>}
    {data && <>
      <div className="grid sm:grid-cols-3 gap-2">{data.by_book.map((book) => <section key={book.book} className="desk-panel p-3">
        <h2 className="font-semibold text-sm">{book.display_book}</h2>
        <p className="desk-muted text-xs mt-1">{book.entries} entries · {book.exits} exits</p>
        {book.open_positions != null && <p className="desk-muted text-xs">{book.open_positions} open now</p>}
        <p className="desk-num text-sm mt-2">{book.realized_net == null ? (book.exits ? 'Exit net not recorded' : 'No realized exits') : `Realized ${money(book.realized_net)}`}</p>
        {book.estimated_net != null && <p className="desk-num desk-muted text-xs">Current estimate {money(book.estimated_net)}</p>}
      </section>)}</div>
      <div className="grid lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.4fr)] gap-3 lg:min-h-0 lg:flex-1">
        <div className="lg:overflow-y-auto"><SessionTimeline events={data.events} selectedId={selectedId} onSelect={setSelectedId} /></div>
        <div className="flex flex-col gap-3 lg:overflow-y-auto lg:pr-1">
          {selected && <section className="desk-panel p-4" aria-label="Selected session event">
            <p className="desk-label">{selected.type} · {selected.book || 'System'}</p>
            <h2 className="font-semibold text-lg mt-1">{selected.title}</h2>
            <p className="desk-muted text-sm mt-1">{new Date(selected.at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })} IST</p>
            {selected.reason && <p className="text-sm mt-3">{selected.reason}</p>}
            {Object.keys(selected.metrics).length > 0 && <dl className="grid sm:grid-cols-2 gap-2 mt-3 text-sm">{Object.entries(selected.metrics).map(([key, value]) =>
              <div key={key} className="flex justify-between gap-2"><dt className="desk-muted">{key.replaceAll('_', ' ')}</dt><dd className="desk-num">{String(value)}</dd></div>)}</dl>}
            {selected.evidence_state === 'unavailable' && <p className="desk-muted text-sm mt-3">No saved decision for this older trade. The recorded position and timing are still shown.</p>}
            {selected.trade_id && <button type="button" className="desk-btn mt-3" onClick={() => onOpenTrade(selected.trade_id!)}>View trade and chart</button>}
          </section>}
          <SessionInsights observations={data.observations} onSelectEvent={setSelectedId} />
          {onOpenReview && <button type="button" className="desk-btn self-start" onClick={onOpenReview}>Open detailed review and journal</button>}
        </div>
      </div>
    </>}
  </div>;
};
