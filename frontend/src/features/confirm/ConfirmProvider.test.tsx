import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ConfirmProvider, useConfirm, type ConfirmOptions } from './ConfirmProvider';
import { axeCheck } from '../../test/axe';

function Harness({ options, onResult }: { options: ConfirmOptions; onResult: (v: boolean) => void }) {
  const confirm = useConfirm();
  return <button onClick={async () => onResult(await confirm(options))}>open</button>;
}
const setup = (options: ConfirmOptions) => {
  const results: boolean[] = [];
  render(<ConfirmProvider><Harness options={options} onResult={(v) => results.push(v)} /></ConfirmProvider>);
  fireEvent.click(screen.getByText('open'));
  return results;
};

describe('ConfirmProvider', () => {
  it('Escape cancels', async () => {
    const results = setup({ title: 'Close it?', body: 'x', confirmLabel: 'Close' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await act(async () => { fireEvent.keyDown(document, { key: 'Escape' }); });
    expect(results).toEqual([false]);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('confirm resolves true', async () => {
    const results = setup({ title: 'Close it?', body: 'x', confirmLabel: 'Close' });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Close' })); });
    expect(results).toEqual([true]);
  });

  it('gates the confirm button on the exact typed phrase', async () => {
    const results = setup({ title: 'Kill', body: 'x', confirmLabel: 'Engage', danger: true, phrase: 'KILL' });
    const btn = screen.getByRole('button', { name: 'Engage' });
    expect(btn).toBeDisabled();
    const input = screen.getByLabelText('Type KILL to confirm');
    fireEvent.change(input, { target: { value: 'kill' } });
    expect(btn).toBeDisabled();
    fireEvent.change(input, { target: { value: 'KILL' } });
    expect(btn).toBeEnabled();
    await act(async () => { fireEvent.click(btn); });
    expect(results).toEqual([true]);
  });

  it('danger dialogs focus Cancel first and trap Tab', () => {
    setup({ title: 'Kill', body: 'x', confirmLabel: 'Engage', danger: true, phrase: 'KILL' });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }));
    const engage = screen.getByRole('button', { name: 'Engage' });
    const input = screen.getByLabelText('Type KILL to confirm');
    fireEvent.change(input, { target: { value: 'KILL' } });
    engage.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(input);
  });

  it('refuses when there is no provider', async () => {
    const results: boolean[] = [];
    render(<Harness options={{ title: 't', body: 'b', confirmLabel: 'ok' }} onResult={(v) => results.push(v)} />);
    await act(async () => { fireEvent.click(screen.getByText('open')); });
    expect(results).toEqual([false]);
  });

  it('has no axe violations', async () => {
    setup({ title: 'Kill', body: 'Closes 2 positions', confirmLabel: 'Engage', danger: true, phrase: 'KILL' });
    expect(await axeCheck(document.body)).toEqual([]);
  });
});
