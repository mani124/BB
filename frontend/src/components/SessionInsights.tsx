import React from 'react';
import type { DashboardSession } from '../types/dashboard';

interface Props { observations: DashboardSession['observations']; onSelectEvent: (id: string) => void }

export const SessionInsights: React.FC<Props> = ({ observations, onSelectEvent }) => (
  <section className="desk-panel p-4" aria-label="Session observations">
    <h2 className="font-semibold">What stands out</h2>
    {observations.length === 0 ? <p className="desk-muted text-sm mt-2">No repeated recorded pattern to highlight for this day.</p> :
      <ul className="mt-2 space-y-3">{observations.map((item) => <li key={item.id}>
        <strong>{item.title}</strong><p className="desk-muted text-sm">{item.detail}</p>
        <div className="flex flex-wrap gap-1 mt-1">{item.event_ids.map((id) => <button key={id} type="button" className="desk-btn sm"
          onClick={() => onSelectEvent(id)}>View {id}</button>)}</div>
      </li>)}</ul>}
  </section>
);
