import React, { useRef } from 'react';
import { useVirtualizer, type Virtualizer } from '@tanstack/react-virtual';
import type { ColumnDef } from '../lib/useTable';
import type { useTable } from '../lib/useTable';

type Table<T> = ReturnType<typeof useTable<T>>;

export const ROW_HEIGHT = 28;
const FALLBACK_HEIGHT = 400;

/** Observe the scroll box; a box with no layout (tests, hidden tabs) falls back to a fixed height so rows still render. */
function observeRect(instance: Virtualizer<HTMLDivElement, Element>, cb: (rect: { width: number; height: number }) => void): (() => void) | void {
  const el = instance.scrollElement;
  if (!el) return;
  const read = () => {
    const r = el.getBoundingClientRect();
    cb({ width: r.width, height: r.height || el.clientHeight || FALLBACK_HEIGHT });
  };
  read();
  if (typeof ResizeObserver === 'undefined') return;
  const ro = new ResizeObserver(read);
  ro.observe(el);
  return () => ro.disconnect();
}

export interface DataTableProps<T> {
  table: Table<T>;
  label: string;
  rowKey: (row: T, index: number) => string;
  renderCell: (row: T, col: ColumnDef<T>) => React.ReactNode;
  numeric?: ReadonlySet<string>;
  isSelected?: (row: T) => boolean;
  onRowClick?: (row: T, index: number) => void;
  /** Extra trailing column, e.g. a Close button. */
  trailing?: { header: string; render: (row: T) => React.ReactNode };
  /** Content shown under a row (expanded detail). */
  renderDetail?: (row: T) => React.ReactNode;
  maxHeight?: number | string;
}

/** Sortable, keyboard-operable table. Rows are windowed once there are more than WINDOW_THRESHOLD of them. */
export function DataTable<T>({ table, label, rowKey, renderCell, numeric, isSelected, onRowClick, trailing, renderDetail, maxHeight }: DataTableProps<T>): React.ReactElement {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rows = table.visibleRows;
  const windowed = table.windowed;
  const virtual = useVirtualizer({
    count: windowed ? rows.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
    observeElementRect: observeRect,
  });
  React.useEffect(() => { if (windowed) virtual.scrollToIndex(table.activeIndex); }, [table.activeIndex, windowed]); // eslint-disable-line react-hooks/exhaustive-deps

  let from = 0;
  let to = rows.length;
  let padTop = 0;
  let padBottom = 0;
  if (windowed) {
    const items = virtual.getVirtualItems();
    if (items.length > 0) {
      from = items[0].index;
      to = items[items.length - 1].index + 1;
      padTop = items[0].start;
      padBottom = Math.max(0, virtual.getTotalSize() - items[items.length - 1].end);
    } else { to = Math.min(rows.length, 40); }
  }
  const colSpan = table.columns.length + (trailing ? 1 : 0);
  const sortLabel = (key: string) => (table.sort?.key === key ? (table.sort.dir === 'asc' ? ' ▲' : ' ▼') : '');
  const ariaSort = (key: string) => (table.sort?.key === key ? (table.sort.dir === 'asc' ? 'ascending' as const : 'descending' as const) : undefined);
  const visible = rows.slice(from, to);
  return (
    <div ref={scrollRef} className="overflow-auto" style={{ maxHeight }} tabIndex={0} role="group" onKeyDown={table.onKeyDown}
      aria-label={`${label} table, use arrow keys to move between rows and Enter to select`}>
      <table className="desk-table" aria-label={label} aria-rowcount={rows.length + 1}>
        <thead><tr>
          {table.columns.map((c) => (
            <th key={c.key} scope="col" className={numeric?.has(c.key) ? 'r' : undefined} aria-sort={ariaSort(c.key)}>
              {c.sortable === false ? c.label : <button type="button" className="font-semibold" onClick={() => table.setSort(c.key)}>{c.label}{sortLabel(c.key)}</button>}
            </th>
          ))}
          {trailing && <th scope="col"><span className="sr-only">{trailing.header}</span></th>}
        </tr></thead>
        <tbody>
          {padTop > 0 && <tr aria-hidden style={{ height: padTop }}><td colSpan={colSpan} style={{ padding: 0, border: 0 }} /></tr>}
          {visible.map((row, k) => {
            const i = from + k;
            const sel = isSelected?.(row);
            return (
              <React.Fragment key={rowKey(row, i)}>
                <tr aria-rowindex={i + 2} data-active={i === table.activeIndex || undefined} aria-selected={isSelected ? Boolean(sel) : undefined}
                  className={`${onRowClick ? 'cursor-pointer' : ''} ${sel ? 'desk-selected' : ''}`}
                  style={i === table.activeIndex ? { outline: '1px dashed var(--accent)', outlineOffset: -1 } : undefined}
                  onClick={onRowClick ? () => { table.setActiveIndex(i); onRowClick(row, i); } : undefined}>
                  {table.columns.map((c) => <td key={c.key} className={numeric?.has(c.key) ? 'r desk-num' : undefined}>{renderCell(row, c)}</td>)}
                  {trailing && <td className="r">{trailing.render(row)}</td>}
                </tr>
                {renderDetail?.(row)}
              </React.Fragment>
            );
          })}
          {padBottom > 0 && <tr aria-hidden style={{ height: padBottom }}><td colSpan={colSpan} style={{ padding: 0, border: 0 }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

/** Column chooser fieldset shared by the table panels. */
export function ColumnChooser<T>({ table }: { table: Table<T> }): React.ReactElement {
  return (
    <fieldset className="px-2 py-1 flex flex-wrap gap-3 text-xs" style={{ borderBottom: '1px solid var(--line)' }}>
      <legend className="sr-only">Visible columns</legend>
      {table.allColumns.map((c) => (
        <label key={c.key} className="flex items-center gap-1"><input type="checkbox" checked={!table.hiddenKeys.has(c.key)} onChange={() => table.toggleColumn(c.key)} />{c.label}</label>
      ))}
    </fieldset>
  );
}

export function ColumnsButton({ open, onToggle }: { open: boolean; onToggle: () => void }): React.ReactElement {
  return <button type="button" className="desk-btn" aria-expanded={open} onClick={onToggle}>Columns</button>;
}
