import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { CommandPalette } from './CommandPalette';
import type { Command, CommandContext } from './commandRegistry';
import { NOOP_COMMANDS } from './dockCommands';
import { axeCheck } from '../../test/axe';

const ctx = {} as CommandContext;
const make = (run = vi.fn()): Command[] => [
  { id: 'a', title: 'Open Risk overview', keywords: [], group: 'Panels', run },
  { id: 'b', title: 'Open Trades', keywords: [], group: 'Panels', run },
  { id: 'c', title: 'Kill switch…', keywords: [], group: 'Danger', danger: true, hint: 'Ctrl+Shift+K', run },
];
void NOOP_COMMANDS;

const Host: React.FC<{ commands: Command[] }> = ({ commands }) => {
  const [open, setOpen] = useState(false);
  return (<><button type="button" onClick={() => setOpen(true)}>opener</button>{open && <CommandPalette commands={commands} ctx={ctx} onClose={() => setOpen(false)} />}</>);
};

describe('CommandPalette', () => {
  it('is a labelled dialog with a combobox whose active option follows the arrows', () => {
    render(<CommandPalette commands={make()} ctx={ctx} onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeTruthy();
    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('aria-controls', 'palette-list');
    expect(input).toHaveAttribute('aria-activedescendant', 'palette-opt-0');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', 'palette-opt-1');
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input).toHaveAttribute('aria-activedescendant', 'palette-opt-2');
    fireEvent.keyDown(input, { key: 'Home' });
    expect(input).toHaveAttribute('aria-activedescendant', 'palette-opt-0');
  });
  it('filters as you type and says when nothing matches', () => {
    render(<CommandPalette commands={make()} ctx={ctx} onClose={() => {}} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'trades' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'qqqq' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByRole('status')).toHaveTextContent('No command matches');
    expect(screen.getByRole('combobox')).not.toHaveAttribute('aria-activedescendant');
  });
  it('Enter closes the palette and then runs the command', () => {
    vi.useFakeTimers();
    const run = vi.fn();
    const onClose = vi.fn();
    render(<CommandPalette commands={make(run)} ctx={ctx} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
    expect(onClose).toHaveBeenCalled();
    act(() => { vi.runAllTimers(); });
    expect(run).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
  it('clicking a result runs it', () => {
    vi.useFakeTimers();
    const run = vi.fn();
    render(<CommandPalette commands={make(run)} ctx={ctx} onClose={() => {}} />);
    fireEvent.click(screen.getAllByRole('option')[0]);
    act(() => { vi.runAllTimers(); });
    expect(run).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
  it('Escape closes it and focus returns to the opener', () => {
    render(<Host commands={make()} />);
    const opener = screen.getByRole('button', { name: 'opener' });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
  it('marks danger commands with a visible word and shows the shortcut hint', () => {
    render(<CommandPalette commands={make()} ctx={ctx} onClose={() => {}} />);
    const kill = screen.getAllByRole('option')[2];
    expect(kill).toHaveTextContent('Danger');
    expect(kill).toHaveTextContent('Ctrl+Shift+K');
  });
  it('has no serious accessibility violations', async () => {
    const { container } = render(<CommandPalette commands={make()} ctx={ctx} onClose={() => {}} />);
    expect(await axeCheck(container)).toEqual([]);
  });
});
