import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { SettingsPanel } from './SettingsPanel';
import type { RuntimeSettingsPayload } from '../types';

const payload: RuntimeSettingsPayload = {
  groups: ['Risk limits (RMS)'],
  settings: [
    { key: 'max_lots_per_trade', label: 'Max lots per trade', group: 'Risk limits (RMS)', type: 'int', unit: 'lots', description: 'Ceiling', value: 0, default: 0, overridden: false, min: 0, max: null, choices: [], zero_disables: true },
    { key: 'daily_loss_limit', label: 'Daily loss limit', group: 'Risk limits (RMS)', type: 'float', unit: 'INR', description: 'Stops entries', value: 24000, default: 24000, overridden: true, min: 0, max: null, choices: [], zero_disables: true },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe('SettingsPanel', () => {
  it('shows an off badge for a disabled limit and a reset button only for overridden ones', () => {
    render(<SettingsPanel initial={payload} initialAudit={[]} />);
    expect(screen.getByText('off')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reset Daily loss limit' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reset Max lots per trade' })).toBeNull();
  });

  it('sends only the changed values when saving', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    render(<SettingsPanel initial={payload} initialAudit={[]} />);
    const save = screen.getByRole('button', { name: /Save/ });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Max lots per trade'), { target: { value: '5' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/settings');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ changes: { max_lots_per_trade: 5 } });
  });

  it('shows the server error when a value is rejected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Max lots per trade: must be at least 0' }), { status: 422 }));
    render(<SettingsPanel initial={payload} initialAudit={[]} />);
    fireEvent.change(screen.getByLabelText('Max lots per trade'), { target: { value: '-3' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('must be at least 0');
  });
});

describe('SettingsPanel navigation', () => {
  const multi: RuntimeSettingsPayload = {
    groups: ['Risk limits (RMS)', 'Alerts'],
    settings: [
      ...payload.settings,
      { key: 'tg_on', label: 'Telegram alerts', group: 'Alerts', type: 'bool', unit: '', description: 'Send messages', value: false, default: false, overridden: false, min: null, max: null, choices: [], zero_disables: false },
    ],
  };

  it('shows one group at a time and switches with the group list', () => {
    render(<SettingsPanel initial={multi} initialAudit={[]} />);
    expect(screen.queryByLabelText('Telegram alerts')).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Alerts' }));
    expect(screen.getByLabelText('Telegram alerts')).toBeInTheDocument();
    expect(screen.queryByLabelText('Max lots per trade')).toBeNull();
  });

  it('search finds settings across groups and flags unsaved ones on the group tab', () => {
    render(<SettingsPanel initial={multi} initialAudit={[]} />);
    fireEvent.change(screen.getByLabelText('Max lots per trade'), { target: { value: '3' } });
    expect(screen.getByRole('tab', { name: /Risk limits \(RMS\), 1 unsaved/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Find a setting'), { target: { value: 'telegram' } });
    expect(screen.getByLabelText('Telegram alerts')).toBeInTheDocument();
    expect(screen.queryByLabelText('Daily loss limit')).toBeNull();
  });
});
