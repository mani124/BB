import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, render, screen, fireEvent } from '@testing-library/react';
import { PanelFrame, PanelMenuContext } from './PanelFrame';
import { appStore, markError, markReady, resetAppStore } from '../data/appStore';
import { getPanel, validateRegistry, type PanelDefinition } from './registry';
import { axeCheck } from '../test/axe';

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-22T04:00:00Z')); resetAppStore(); });
afterEach(() => vi.useRealTimers());

const frame = (children: React.ReactNode = <span className="desk-num">42</span>) => render(<PanelFrame title="Trades" sources={['watch']}>{children}</PanelFrame>);

describe('PanelFrame', () => {
  it('shows the as-of time in IST', () => {
    markReady('watch');
    frame();
    expect(screen.getByTestId('panel-asof').textContent).toBe('As of 09:30:00 IST');
  });

  it('shows a stale badge with text and icon after the threshold', () => {
    markReady('watch');
    frame();
    expect(screen.queryByTestId('panel-stale')).toBeNull();
    act(() => { vi.advanceTimersByTime(61_000); });
    const badge = screen.getByTestId('panel-stale');
    expect(badge.textContent).toMatch(/Stale 61 s/);
    expect(badge.querySelector('svg')).not.toBeNull();
  });

  it('keeps children visible under an error strip with Retry', () => {
    markReady('watch');
    markError('watch', 'HTTP 500');
    frame();
    expect(screen.getByRole('alert').textContent).toContain('HTTP 500');
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();
  });

  it('marks the root frozen when the stream is stale', () => {
    appStore.setState({ stream: { state: 'stale', ageSec: 20 } });
    const { container } = frame();
    expect(container.querySelector('[data-frozen="true"]')).not.toBeNull();
    expect(screen.getByTestId('panel-frozen')).toBeInTheDocument();
  });

  it('renders the shell-provided menu', () => {
    const run = vi.fn();
    render(<PanelMenuContext.Provider value={[{ id: 'float', label: 'Float', run }]}><PanelFrame title="T" sources={[]}>x</PanelFrame></PanelMenuContext.Provider>);
    fireEvent.click(screen.getByRole('button', { name: 'T panel menu' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Float' }));
    expect(run).toHaveBeenCalled();
  });

  it('has no axe violations', async () => {
    vi.useRealTimers();
    markReady('watch');
    const { container } = render(<PanelMenuContext.Provider value={[{ id: 'f', label: 'Float', run: () => {} }]}><PanelFrame title="Trades" sources={['watch']}>body</PanelFrame></PanelMenuContext.Provider>);
    expect(await axeCheck(container)).toEqual([]);
  });
});

describe('registry', () => {
  const def = (id: string): PanelDefinition => ({ id, title: id, icon: 'x', component: () => null, category: 'trading', singleton: true, sources: [] });
  it('rejects duplicate ids', () => {
    expect(() => validateRegistry([def('a'), def('a')])).toThrow(/Duplicate/);
  });
  it('looks panels up by id', () => {
    expect(getPanel('b', [def('a'), def('b')])?.id).toBe('b');
    expect(getPanel('zzz', [def('a')])).toBeUndefined();
  });
});
