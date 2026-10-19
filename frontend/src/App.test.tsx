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

describe('dashboard navigation', () => {
  it('opens Watch and keeps all former book and review screens reachable', () => {
    vi.stubGlobal('EventSource', FakeEventSource);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }));
    render(<App />);
    expect(screen.getByRole('tab', { name: 'Watch' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Control' }));
    for (const label of ['Review and journal', 'Setup 16', 'Commodities & FX', 'Earnings calendar and IV', 'Runtime settings and audit']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Review and journal' }));
    expect(screen.getByRole('button', { name: /Back to control/i })).toBeInTheDocument();
  });
});
