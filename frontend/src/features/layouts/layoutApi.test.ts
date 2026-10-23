import { describe, it, expect, beforeEach, afterEach, vi, type MockInstance } from 'vitest';
import * as client from '../../api/client';
import { PRESETS } from './presets';
import { deleteLayout, exportLayout, flushLayouts, resetLayoutApi, importLayout, layoutKey, loadLayouts, saveLayout } from './layoutApi';

const spec = (n = 'Earnings') => ({ ...PRESETS.Earnings, name: n });
let fetchSpy: MockInstance<typeof client.apiFetch>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-22T04:00:00Z'));
  localStorage.clear();
  resetLayoutApi();
  fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(new Response('{}', { status: 200 }));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('saveLayout', () => {
  it('collapses ten changes into one PUT and writes the cache first', async () => {
    for (let i = 0; i < 10; i += 1) saveLayout(spec());
    expect(JSON.parse(localStorage.getItem('bb_layouts')!)['workspace:Earnings']).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2000);
    const puts = fetchSpy.mock.calls.filter(([, i]) => (i as RequestInit)?.method === 'PUT');
    expect(puts).toHaveLength(1);
    expect(String(puts[0][0])).toBe('/api/ui/layouts/workspace%3AEarnings');
  });
  it('limits writes to one per second', async () => {
    saveLayout(spec());
    await vi.advanceTimersByTimeAsync(900);
    saveLayout(spec());
    await vi.advanceTimersByTimeAsync(10);
    expect(fetchSpy.mock.calls.filter(([, i]) => (i as RequestInit)?.method === 'PUT')).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1500);
    expect(fetchSpy.mock.calls.filter(([, i]) => (i as RequestInit)?.method === 'PUT')).toHaveLength(2);
  });
  it('does not throw when the server is down or storage fails', async () => {
    fetchSpy.mockRejectedValue(new Error('down'));
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('full'); });
    expect(() => saveLayout(spec())).not.toThrow();
    await expect(flushLayouts()).resolves.toBeUndefined();
  });
});

describe('loadLayouts', () => {
  it('uses the cache when the server is down', async () => {
    saveLayout(spec());
    fetchSpy.mockRejectedValue(new Error('down'));
    const r = await loadLayouts();
    expect(r.serverOk).toBe(false);
    expect(r.layouts['workspace:Earnings'].name).toBe('Earnings');
  });
  it('uses the cache when the server returns 500', async () => {
    saveLayout(spec());
    fetchSpy.mockResolvedValue(new Response('{}', { status: 500 }));
    expect((await loadLayouts()).layouts['workspace:Earnings']).toBeTruthy();
  });
  it('the newest updated_at wins', async () => {
    saveLayout(spec('Earnings'));
    const newer = { ...PRESETS.Earnings, name: 'Earnings', based_on: 'server' };
    fetchSpy.mockResolvedValue(new Response(JSON.stringify([{ name: 'workspace:Earnings', schema_version: 1, body: newer, updated_at: '2030-01-01T00:00:00Z' }]), { status: 200 }));
    expect((await loadLayouts()).layouts['workspace:Earnings'].based_on).toBe('server');
    const older = { ...newer, based_on: 'old' };
    fetchSpy.mockResolvedValue(new Response(JSON.stringify([{ name: 'workspace:Earnings', schema_version: 1, body: older, updated_at: '2001-01-01T00:00:00Z' }]), { status: 200 }));
    expect((await loadLayouts()).layouts['workspace:Earnings'].based_on).toBeUndefined();
  });
  it('flags corrupt entries as invalid instead of throwing', async () => {
    localStorage.setItem('bb_layouts', JSON.stringify({ 'workspace:Trading': { updated_at: 'x', spec: 'garbage' } }));
    fetchSpy.mockResolvedValue(new Response('boom', { status: 500 }));
    const r = await loadLayouts();
    expect(r.invalid).toEqual(['workspace:Trading']);
  });
  it('survives corrupted cache JSON and throwing storage', async () => {
    localStorage.setItem('bb_layouts', '{{{');
    expect((await loadLayouts()).layouts).toEqual({});
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    await expect(loadLayouts()).resolves.toBeTruthy();
  });
});

describe('delete, export and import', () => {
  it('deleteLayout clears cache and cancels a pending write', async () => {
    saveLayout(spec('My view'));
    await deleteLayout('My view');
    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchSpy.mock.calls.filter(([, i]) => (i as RequestInit)?.method === 'PUT')).toHaveLength(0);
    expect(fetchSpy.mock.calls.some(([, i]) => (i as RequestInit)?.method === 'DELETE')).toBe(true);
    expect(JSON.parse(localStorage.getItem('bb_layouts')!)['custom:My view']).toBeUndefined();
  });
  it('custom names are keyed separately from presets', () => {
    expect(layoutKey('Trading')).toBe('workspace:Trading');
    expect(layoutKey('Mine')).toBe('custom:Mine');
  });
  it('import of invalid JSON returns an error and saves nothing', () => {
    const r = importLayout('{nope');
    expect(r.ok).toBe(false);
    expect(localStorage.getItem('bb_layouts')).toBeNull();
  });
  it('export then import round-trips', () => {
    const r = importLayout(exportLayout(PRESETS.Earnings));
    expect(r.ok).toBe(true);
  });
});
