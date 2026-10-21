import React, { useState } from 'react';
import { Tabs } from './Tabs';

export interface BookKpi {
  label: string;
  value: React.ReactNode;
  tone?: 'up' | 'down';
  hint?: string;
}

export interface BookTab {
  id: string;
  label: string;
  count?: number;
  content: React.ReactNode;
}

interface Props {
  /** Unique per book; ties tabs to their panel for assistive tech. */
  idPrefix: string;
  title: string;
  titleId?: string;
  pills?: { text: string; tone?: 'up' | 'warn' | 'down' | 'mute' }[];
  updated?: string;
  actions?: React.ReactNode;
  /** One line that explains why the book is idle or broken; shown above the figures. */
  notice?: { tone: 'warn' | 'down' | 'mute'; text: React.ReactNode; testId?: string } | null;
  kpis: BookKpi[];
  tabs: BookTab[];
  testId?: string;
  kpiTestId?: string;
}

/**
 * The one layout every trading book uses: a status line, a row of figures, then tabbed tables.
 * Earnings differs only in what they put in these slots.
 */
export const BookFrame: React.FC<Props> = ({ idPrefix, title, titleId, pills = [], updated, actions, notice, kpis, tabs, testId, kpiTestId }) => {
  const [active, setActive] = useState(tabs[0].id);
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0" data-testid={testId}>
      <section className="desk-panel shrink-0" aria-labelledby={titleId}>
        <div className="desk-ph">
          <h2 id={titleId}>{title}</h2>
          {pills.map((p) => <span key={p.text} className={`desk-pill ${p.tone ?? ''}`}>{p.text}</span>)}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {updated && <span className="text-xs desk-muted">Updated {updated}</span>}
            {actions}
          </div>
        </div>
        {notice && (
          <div role={notice.tone === 'down' ? 'alert' : 'status'} data-testid={notice.testId}
            className={`px-3 py-1.5 text-sm ${notice.tone === 'down' ? 'desk-down' : notice.tone === 'warn' ? '' : 'desk-muted'}`}
            style={{ borderBottom: '1px solid var(--line)', background: notice.tone === 'warn' ? 'var(--warn-soft)' : notice.tone === 'down' ? 'var(--down-soft)' : 'var(--alt)' }}>
            {notice.text}
          </div>
        )}
        {kpis.length > 0 && <div className="desk-ticker desk-flow" style={{ border: 0, borderRadius: 0 }} aria-label={`${title} figures`} data-testid={kpiTestId}>
          {kpis.map((k) => (
            <div key={k.label} title={k.hint}>
              <div className="desk-label">{k.label}</div>
              <div className={`desk-num text-lg font-semibold ${k.tone === 'up' ? 'desk-up' : k.tone === 'down' ? 'desk-down' : ''}`}>{k.value}</div>
            </div>
          ))}
        </div>}
      </section>
      <Tabs<string> idPrefix={idPrefix} label={`${title} sections`} className="desk-subtabs shrink-0" tabClassName="desk-subtab" value={active} onChange={setActive}
        items={tabs.map((t) => ({ id: t.id, name: t.label, label: <>{t.label}{t.count != null && <span className="desk-pill desk-num ml-1">{t.count}</span>}</> }))} />
      <div id={`${idPrefix}-panel`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-${current.id}`} className="flex flex-col gap-3 lg:flex-1 lg:min-h-0 lg:overflow-y-auto pb-3">
        {current.content}
      </div>
    </div>
  );
};

/** A titled table block inside a book tab. */
export const BookSection: React.FC<{ title: string; label?: string; right?: React.ReactNode; children: React.ReactNode }> = ({ title, label, right, children }) => (
  <section className="desk-panel" aria-label={label ?? title}>
    <div className="desk-ph"><h3>{title}</h3>{right && <div className="ml-auto">{right}</div>}</div>
    {children}
  </section>
);
