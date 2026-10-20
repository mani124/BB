import React from 'react';
import type { DashboardSessionEvent } from '../types/dashboard';

interface Props { events: DashboardSessionEvent[]; selectedId: string | null; onSelect: (id: string) => void }

export const SessionTimeline: React.FC<Props> = ({ events, selectedId, onSelect }) => (
  <section className="desk-panel overflow-hidden" aria-label="Session timeline">
    <h2 className="font-semibold p-4 border-b" style={{ borderColor: 'var(--line)' }}>Timeline</h2>
    {events.length === 0 && <p className="p-5 text-sm desk-muted">No recorded session events for this day. Older activity may lack telemetry.</p>}
    <div className="divide-y" style={{ borderColor: 'var(--line)' }}>
      {events.map((event) => <button key={event.id} type="button" onClick={() => onSelect(event.id)}
        aria-pressed={selectedId === event.id} aria-label={`${event.title} ${event.at}`}
        className="w-full text-left p-3 flex items-start gap-3 hover:bg-[var(--alt)]"
        style={{ background: selectedId === event.id ? 'var(--accent-soft)' : undefined }}>
        <time className="desk-num text-xs desk-muted shrink-0 w-16" dateTime={event.at}>{new Date(event.at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })}</time>
        <span className="min-w-0"><strong className="block text-sm">{event.title}</strong>
          <span className="desk-muted text-xs">{event.book || 'System'} · {event.reason || event.type}</span></span>
      </button>)}
    </div>
  </section>
);
