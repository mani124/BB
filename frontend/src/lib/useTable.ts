import { useCallback, useMemo, useState } from 'react';
import { downloadCsv, toCsv } from './csv';

export interface ColumnDef<T> {
  key: string;
  label: string;
  /** Value used for sorting and CSV; defaults to row[key]. */
  get?: (row: T) => unknown;
  sortable?: boolean;
  defaultHidden?: boolean;
}

export interface SortState { key: string; dir: 'asc' | 'desc' }

export const WINDOW_THRESHOLD = 150;

interface Persisted { sort?: SortState | null; hidden?: string[] }

const storageName = (k: string) => `bb_table:${k}`;

function load(key: string): Persisted {
  try {
    const raw = localStorage.getItem(storageName(key));
    return raw ? (JSON.parse(raw) as Persisted) : {};
  } catch {
    return {};
  }
}

function save(key: string, value: Persisted): void {
  try { localStorage.setItem(storageName(key), JSON.stringify(value)); } catch { /* storage unavailable */ }
}

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export interface UseTableOptions<T> {
  columns: ColumnDef<T>[];
  storageKey: string;
  initialSort?: SortState;
  onActivate?: (row: T) => void;
  csvName?: string;
}

export function useTable<T>(rows: T[], opts: UseTableOptions<T>) {
  const { columns, storageKey, initialSort, onActivate } = opts;
  const [persisted, setPersisted] = useState<Persisted>(() => {
    const p = load(storageKey);
    return { sort: p.sort ?? initialSort ?? null, hidden: p.hidden ?? columns.filter((c) => c.defaultHidden).map((c) => c.key) };
  });
  const [activeIndex, setActiveIndex] = useState(0);

  const update = useCallback((next: Persisted) => { setPersisted(next); save(storageKey, next); }, [storageKey]);

  const getValue = useCallback((c: ColumnDef<T>, row: T) => (c.get ? c.get(row) : (row as Record<string, unknown>)[c.key]), []);

  const sort = persisted.sort ?? null;
  const setSort = useCallback((key: string) => {
    const cur = persisted.sort;
    const next: SortState = cur && cur.key === key ? { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' };
    update({ ...persisted, sort: next });
  }, [persisted, update]);

  const hidden = useMemo(() => new Set(persisted.hidden ?? []), [persisted.hidden]);
  const visibleColumns = useMemo(() => columns.filter((c) => !hidden.has(c.key)), [columns, hidden]);
  const toggleColumn = useCallback((key: string) => {
    const set = new Set(persisted.hidden ?? []);
    if (set.has(key)) set.delete(key); else set.add(key);
    update({ ...persisted, hidden: [...set] });
  }, [persisted, update]);

  const visibleRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const sign = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => sign * compare(getValue(col, a), getValue(col, b)));
  }, [rows, sort, columns, getValue]);

  const last = Math.max(0, visibleRows.length - 1);
  const clamped = Math.min(activeIndex, last);

  const onKeyDown = useCallback((e: { key: string; preventDefault(): void }) => {
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); setActiveIndex(Math.min(clamped + 1, last)); break;
      case 'ArrowUp': e.preventDefault(); setActiveIndex(Math.max(clamped - 1, 0)); break;
      case 'Home': e.preventDefault(); setActiveIndex(0); break;
      case 'End': e.preventDefault(); setActiveIndex(last); break;
      case 'Enter': if (visibleRows[clamped] !== undefined) { e.preventDefault(); onActivate?.(visibleRows[clamped]); } break;
      default: break;
    }
  }, [clamped, last, visibleRows, onActivate]);

  /** CSV of exactly the visible columns, in the current sort order. */
  const csv = useCallback((): string => {
    const cols = visibleColumns.map((c) => ({ key: c.key, label: c.label }));
    const data = visibleRows.map((r) => Object.fromEntries(visibleColumns.map((c) => [c.key, getValue(c, r)])));
    return toCsv(data, cols);
  }, [visibleColumns, visibleRows, getValue]);

  const exportCsv = useCallback(() => downloadCsv(opts.csvName ?? `${storageKey}.csv`, csv()), [csv, opts.csvName, storageKey]);

  return {
    visibleRows, sort, setSort, columns: visibleColumns, allColumns: columns, hiddenKeys: hidden, toggleColumn,
    exportCsv, csv, activeIndex: clamped, setActiveIndex, onKeyDown, windowed: visibleRows.length > WINDOW_THRESHOLD,
  };
}
