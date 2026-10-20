import React, { useState } from 'react';
import { Tabs } from './Tabs';
import { Setup16Screen } from './Setup16Screen';
import { CxScreen } from './CxScreen';
import { EarningsPanel } from './EarningsPanel';
import type { DashboardSource } from '../types/dashboard';

export type BookId = 'setup16' | 'cx' | 'earnings';

const BOOKS: { id: BookId; label: string }[] = [
  { id: 'setup16', label: 'Setup 16' },
  { id: 'cx', label: 'Commodities & FX' },
  { id: 'earnings', label: 'Earnings' },
];

interface Props {
  initialBook?: BookId;
  /** Source health from the watch feed, shown next to each book name when it needs attention. */
  sources?: DashboardSource[];
}

/** The side books (Setup 16, Commodities & FX, Earnings): same frame, one switch. */
export const BooksScreen: React.FC<Props> = ({ initialBook = 'setup16', sources = [] }) => {
  const [book, setBook] = useState<BookId>(initialBook);
  const health = (id: BookId) => sources.find((s) => s.book === id);
  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0">
      <h1 className="sr-only">Books</h1>
      <Tabs<BookId>
        idPrefix="books"
        label="Books"
        className="desk-subtabs shrink-0 px-2 desk-panel"
        tabClassName="desk-subtab"
        value={book}
        onChange={setBook}
        items={BOOKS.map((b) => {
          const h = health(b.id);
          const needsAttention = h && (h.state === 'error' || h.state === 'stale');
          return { id: b.id, name: b.label, label: <>{b.label}{needsAttention && <span className={`desk-pill ${h.state === 'error' ? 'down' : 'warn'} ml-2`} title={h.message || undefined}>{h.state}</span>}</> };
        })}
      />
      <div id="books-panel" role="tabpanel" aria-labelledby={`books-tab-${book}`} className="flex flex-col lg:flex-1 lg:min-h-0">
        {book === 'setup16' ? <Setup16Screen /> : book === 'cx' ? <CxScreen /> : <EarningsPanel />}
      </div>
    </div>
  );
};
