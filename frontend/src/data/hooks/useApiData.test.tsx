import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useApiData } from './useApiData';
import { actions } from '../actions';

const jsonRes = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

describe('useApiData', () => {
  let calls: string[];
  beforeEach(() => {
    calls = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => { calls.push(String(url)); return jsonRes(String(url).includes('/api/paper/') ? { ok: true } : [{ n: calls.length }]); }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('loads once and exposes the data', async () => {
    const { result } = renderHook(() => useApiData<{ n: number }[]>('/api/x', { refreshMs: 0 }));
    await waitFor(() => expect(result.current.data).toEqual([{ n: 1 }]));
  });

  it('refetches after a finished action only when watchActions is set', async () => {
    const watching = renderHook(() => useApiData('/api/watched', { refreshMs: 0, watchActions: true }));
    const quiet = renderHook(() => useApiData('/api/quiet', { refreshMs: 0 }));
    await waitFor(() => expect(watching.result.current.data).not.toBeNull());
    await waitFor(() => expect(quiet.result.current.data).not.toBeNull());
    await act(async () => { await actions.scanNow(); });
    await waitFor(() => expect(calls.filter((c) => c.includes('/api/watched')).length).toBe(2));
    expect(calls.filter((c) => c.includes('/api/quiet')).length).toBe(1);
  });
});
