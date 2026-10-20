import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import App from './App';

class FakeEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  addEventListener() {}
  close() {}
}

describe('terminal workspace', () => {
  it('opens on the terminal and keeps every former screen reachable from the blotter', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }));
    render(<App />);
    expect(screen.getByRole('tab', { name: 'Positions' })).toHaveAttribute('aria-selected', 'true');
    for (const name of ['Signals', 'Trades', 'Session', 'Review', 'Setup 16', 'Commodities & FX', 'Earnings', 'Settings', 'Control']) {
      expect(screen.getByRole('tab', { name })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('tab', { name: 'Control' }));
    expect(screen.getByRole('tab', { name: 'Control' })).toHaveAttribute('aria-selected', 'true');
    for (const label of ['Review and journal', 'Setup 16', 'Commodities & FX', 'Earnings calendar and IV', 'Runtime settings and audit']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Review and journal' }));
    expect(screen.getByRole('tab', { name: 'Review' })).toHaveAttribute('aria-selected', 'true');
  });
});
