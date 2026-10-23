import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { useTable, type ColumnDef } from '../lib/useTable';
import { ColumnChooser, DataTable } from './DataTable';

interface Row { id: string; n: number; name: string }
const COLS: ColumnDef<Row>[] = [{ key: 'id', label: 'Id', sortable: true }, { key: 'n', label: 'N', sortable: true }, { key: 'name', label: 'Name', defaultHidden: true }];
const make = (count: number): Row[] => Array.from({ length: count }, (_, i) => ({ id: `r${i}`, n: i, name: `name${i}` }));

const Harness: React.FC<{ rows: Row[]; onActivate?: (r: Row) => void; exposeCsv?: (f: () => string) => void }> = ({ rows, onActivate, exposeCsv }) => {
  const table = useTable(rows, { columns: COLS, storageKey: 'dt-test', onActivate });
  exposeCsv?.(table.csv);
  return <><ColumnChooser table={table} /><DataTable table={table} label="Test rows" rowKey={(r) => r.id} renderCell={(r, c) => String((r as unknown as Record<string, unknown>)[c.key])} onRowClick={onActivate} /></>;
};
const bodyRows = () => within(screen.getByRole('table', { name: 'Test rows' })).getAllByRole('row').filter((r) => r.getAttribute('aria-hidden') !== 'true').length - 1;

beforeEach(() => localStorage.clear());

describe('DataTable', () => {
  it('renders every row when under the window threshold', () => {
    render(<Harness rows={make(40)} />);
    expect(bodyRows()).toBe(40);
  });

  it('windows a 300 row fixture to at most 60 DOM rows and keeps the full row count for assistive tech', () => {
    render(<Harness rows={make(300)} />);
    expect(bodyRows()).toBeLessThanOrEqual(60);
    expect(bodyRows()).toBeGreaterThan(0);
    expect(screen.getByRole('table', { name: 'Test rows' }).getAttribute('aria-rowcount')).toBe('301');
  });

  it('moves with arrow keys and selects with Enter', () => {
    const onActivate = vi.fn();
    render(<Harness rows={make(10)} onActivate={onActivate} />);
    const scroller = screen.getByRole('group', { name: /Test rows table/ });
    fireEvent.keyDown(scroller, { key: 'ArrowDown' });
    fireEvent.keyDown(scroller, { key: 'ArrowDown' });
    fireEvent.keyDown(scroller, { key: 'Enter' });
    expect(onActivate).toHaveBeenCalledWith(expect.objectContaining({ id: 'r2' }));
  });

  it('remembers the column choice and exports exactly the visible columns', () => {
    let csv = () => '';
    const first = render(<Harness rows={make(3)} exposeCsv={(f) => { csv = f; }} />);
    expect(csv().split(/\r?\n/)[0]).toBe('Id,N');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Name' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'N' }));
    expect(csv().split(/\r?\n/)[0]).toBe('Id,Name');
    first.unmount();
    render(<Harness rows={make(3)} exposeCsv={(f) => { csv = f; }} />);
    expect(csv().split(/\r?\n/)[0]).toBe('Id,Name');
    expect(screen.queryByRole('columnheader', { name: 'N' })).toBeNull();
  });
});
