import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, renderHook, waitFor, render, screen, fireEvent, within } from '@testing-library/react';
import { PRESETS } from './presets';
import type { LayoutSpec } from './layoutModel';

vi.mock('./layoutApi', async () => {
  const actual = await vi.importActual<typeof import('./layoutApi')>('./layoutApi');
  return {
    ...actual,
    loadLayouts: vi.fn(async () => ({ layouts: {}, invalid: [], dropped: {}, serverOk: true })),
    saveLayout: vi.fn(),
    deleteLayout: vi.fn(async () => {}),
    listSnapshots: vi.fn(async () => [{ id: 7, taken_at: '2026-10-22T10:00:00' }]),
    restoreSnapshot: vi.fn(async () => ({ ...PRESETS.Earnings, name: 'Trading' })),
  };
});
import * as api from './layoutApi';
import { useLayouts } from './useLayouts';
import { WorkspaceSwitcher } from '../../shell/WorkspaceSwitcher';
import { ConfirmProvider } from '../confirm/ConfirmProvider';
import { appStore, resetAppStore } from '../../data/appStore';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetAppStore();
  window.history.replaceState({}, '', '/');
});

const setup = async () => {
  const hook = renderHook(() => useLayouts());
  await waitFor(() => expect(hook.result.current.ready).toBe(true));
  return hook;
};

describe('useLayouts', () => {
  it('starts on Trading with the preset and remembers the last workspace', async () => {
    const { result } = await setup();
    expect(result.current.current).toBe('Trading');
    expect(result.current.spec.name).toBe('Trading');
    act(() => result.current.switchTo('Risk'));
    expect(result.current.current).toBe('Risk');
    expect(localStorage.getItem('bb_workspace')).toBe('Risk');
    expect(appStore.getState().ui.workspace).toBe('Risk');
  });

  it('honours ?workspace=', async () => {
    window.history.replaceState({}, '', '/?workspace=Review');
    const { result } = await setup();
    expect(result.current.current).toBe('Review');
  });

  it('save as makes a custom layout based on the preset and switches to it', async () => {
    const { result } = await setup();
    let err: string | null = 'x';
    act(() => { err = result.current.saveAs('My view'); });
    expect(err).toBeNull();
    expect(result.current.current).toBe('My view');
    expect(result.current.customs).toEqual(['My view']);
    expect(result.current.spec.based_on).toBe('Trading');
    expect(api.saveLayout).toHaveBeenCalled();
  });

  it('refuses empty, duplicate and built-in names', async () => {
    const { result } = await setup();
    expect(result.current.saveAs('  ')).toMatch(/Enter a name/);
    expect(result.current.saveAs('Risk')).toMatch(/built-in/);
    act(() => { result.current.saveAs('Mine'); });
    act(() => result.current.switchTo('Trading'));
    expect(result.current.saveAs('Mine')).toMatch(/already exists/);
  });

  it('reset of a workspace saves the default over it (the server cannot delete built-ins) and rebuilds the dock', async () => {
    const { result } = await setup();
    const rev = result.current.revision;
    act(() => result.current.onChange({ ...PRESETS.Trading, based_on: 'changed' }));
    expect(result.current.spec.based_on).toBe('changed');
    act(() => result.current.reset());
    expect(api.deleteLayout).not.toHaveBeenCalledWith('Trading');
    expect(api.saveLayout).toHaveBeenLastCalledWith(expect.objectContaining({ name: 'Trading' }));
    expect(result.current.spec.based_on).toBeUndefined();
    expect(result.current.revision).toBeGreaterThan(rev);
  });

  it('rename and delete work only on custom layouts', async () => {
    const { result } = await setup();
    expect(result.current.rename('Other')).toMatch(/Built-in/);
    act(() => { result.current.saveAs('Mine'); });
    act(() => { expect(result.current.rename('Renamed')).toBeNull(); });
    expect(result.current.customs).toEqual(['Renamed']);
    act(() => result.current.remove());
    expect(result.current.customs).toEqual([]);
    expect(result.current.current).toBe('Trading');
    act(() => result.current.remove());
    expect(api.deleteLayout).toHaveBeenLastCalledWith('Renamed');
  });

  it('import of invalid JSON shows an error and saves nothing', async () => {
    const { result } = await setup();
    let r: ReturnType<typeof result.current.importJson> | undefined;
    act(() => { r = result.current.importJson('{nope'); });
    expect(r!.ok).toBe(false);
    expect(api.saveLayout).not.toHaveBeenCalled();
  });

  it('import of valid JSON saves and switches', async () => {
    const { result } = await setup();
    const json = JSON.stringify({ ...PRESETS.Earnings, name: 'Imported' });
    act(() => { result.current.importJson(json); });
    expect(result.current.current).toBe('Imported');
    expect(api.saveLayout).toHaveBeenCalled();
  });

  it('restoring a snapshot swaps the layout and bumps the revision', async () => {
    const { result } = await setup();
    const rev = result.current.revision;
    let ok = false;
    await act(async () => { ok = await result.current.restore(7); });
    expect(ok).toBe(true);
    expect(result.current.revision).toBeGreaterThan(rev);
  });

  it('offers "update to default" when the saved preset version is older', async () => {
    vi.mocked(api.loadLayouts).mockResolvedValueOnce({ layouts: { 'workspace:Trading': { ...PRESETS.Trading, preset_version: 0 } as LayoutSpec }, invalid: [], dropped: {}, serverOk: true });
    const { result } = await setup();
    expect(result.current.presetOutdated).toBe(true);
    act(() => result.current.updateToDefault());
    expect(result.current.spec.preset_version).toBe(PRESETS.Trading.preset_version);
  });
});

describe('WorkspaceSwitcher', () => {
  const Harness: React.FC = () => {
    const layouts = useLayouts();
    if (!layouts.ready) return null;
    return <ConfirmProvider><WorkspaceSwitcher layouts={layouts} /><span data-testid="cur">{layouts.current}</span></ConfirmProvider>;
  };

  it('lists the seven workspaces and switches on click', async () => {
    render(<Harness />);
    const nav = await screen.findByRole('navigation', { name: 'Workspaces' });
    for (const n of ['Trading', 'Risk', 'Performance', 'Execution', 'Review', 'Operations', 'Earnings']) expect(within(nav).getByRole('button', { name: n })).toBeTruthy();
    fireEvent.click(within(nav).getByRole('button', { name: 'Review' }));
    expect(screen.getByTestId('cur').textContent).toBe('Review');
  });

  it('reset workspace asks for confirmation first', async () => {
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: /Layout/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset workspace' }));
    const dlg = await screen.findByRole('dialog');
    expect(api.saveLayout).not.toHaveBeenCalled();
    fireEvent.click(within(dlg).getByRole('button', { name: 'Reset workspace' }));
    await waitFor(() => expect(api.saveLayout).toHaveBeenCalledWith(expect.objectContaining({ name: 'Trading' })));
    expect(api.deleteLayout).not.toHaveBeenCalled();
  });

  it('save layout as validates the name inline', async () => {
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: /Layout/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Save layout as/ }));
    const dlg = await screen.findByRole('dialog');
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    expect((await within(dlg).findByRole('alert')).textContent).toMatch(/Enter a name/);
    fireEvent.change(within(dlg).getByLabelText('Layout name'), { target: { value: 'Scalping' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByTestId('cur').textContent).toBe('Scalping'));
  });

  it('import dialog rejects invalid JSON with an error', async () => {
    render(<Harness />);
    fireEvent.click(await screen.findByRole('button', { name: /Layout/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Import layout/ }));
    const dlg = await screen.findByRole('dialog');
    fireEvent.change(within(dlg).getByLabelText('Layout JSON'), { target: { value: '{bad' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Import' }));
    expect((await within(dlg).findByRole('alert')).textContent).toMatch(/Not a valid layout/);
  });
});
