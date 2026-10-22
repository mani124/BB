import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useTable, type ColumnDef } from './useTable';

interface Row { id: string; n: number; name: string }
const columns: ColumnDef<Row>[] = [
  { key: 'id', label: 'Id' }, { key: 'n', label: 'N', sortable: true }, { key: 'name', label: 'Name', defaultHidden: true },
];
const rows: Row[] = [{ id: 'a', n: 3, name: 'x' }, { id: 'b', n: 1, name: 'y' }, { id: 'c', n: 2, name: 'z' }];

beforeEach(() => localStorage.clear());

describe('useTable', () => {
  it('sorts and toggles direction', () => {
    const { result } = renderHook(() => useTable(rows, { columns, storageKey: 't1' }));
    expect(result.current.visibleRows.map((r) => r.id)).toEqual(['a', 'b', 'c']);
    act(() => result.current.setSort('n'));
    expect(result.current.visibleRows.map((r) => r.id)).toEqual(['b', 'c', 'a']);
    act(() => result.current.setSort('n'));
    expect(result.current.visibleRows.map((r) => r.id)).toEqual(['a', 'c', 'b']);
  });

  it('hides default-hidden columns and persists column choice', () => {
    const first = renderHook(() => useTable(rows, { columns, storageKey: 't2' }));
    expect(first.result.current.columns.map((c) => c.key)).toEqual(['id', 'n']);
    act(() => first.result.current.toggleColumn('name'));
    act(() => first.result.current.toggleColumn('n'));
    const second = renderHook(() => useTable(rows, { columns, storageKey: 't2' }));
    expect(second.result.current.columns.map((c) => c.key)).toEqual(['id', 'name']);
  });

  it('works when storage throws', () => {
    const spy = vi.spyOn(localStorage, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    const set = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    const { result } = renderHook(() => useTable(rows, { columns, storageKey: 't3' }));
    expect(() => act(() => result.current.setSort('n'))).not.toThrow();
    expect(result.current.visibleRows[0].id).toBe('b');
    spy.mockRestore(); set.mockRestore();
  });

  it('keyboard: arrows, Home, End and Enter', () => {
    const onActivate = vi.fn();
    const { result } = renderHook(() => useTable(rows, { columns, storageKey: 't4', onActivate }));
    const key = (k: string) => act(() => result.current.onKeyDown({ key: k, preventDefault() {} }));
    key('ArrowDown'); key('ArrowDown'); key('ArrowDown');
    expect(result.current.activeIndex).toBe(2);
    key('Home');
    expect(result.current.activeIndex).toBe(0);
    key('End');
    expect(result.current.activeIndex).toBe(2);
    key('Enter');
    expect(onActivate).toHaveBeenCalledWith(rows[2]);
  });

  it('csv contains exactly the visible columns in sort order', () => {
    const { result } = renderHook(() => useTable(rows, { columns, storageKey: 't5', initialSort: { key: 'n', dir: 'desc' } }));
    expect(result.current.csv()).toBe('Id,N\r\na,3\r\nc,2\r\nb,1');
  });

  it('flags windowing above 150 rows', () => {
    const many = Array.from({ length: 151 }, (_, i) => ({ id: String(i), n: i, name: '' }));
    const { result } = renderHook(() => useTable(many, { columns, storageKey: 't6' }));
    expect(result.current.windowed).toBe(true);
    const { result: small } = renderHook(() => useTable(rows, { columns, storageKey: 't7' }));
    expect(small.current.windowed).toBe(false);
  });
});
