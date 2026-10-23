import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ShortcutHelp } from './ShortcutHelp';
import { SHORTCUTS } from '../shortcuts';
import { axeCheck } from '../../test/axe';

describe('ShortcutHelp', () => {
  it('lists every shortcut', () => {
    render(<ShortcutHelp onClose={() => {}} />);
    for (const s of SHORTCUTS) expect(screen.getByText(s.keys)).toBeTruthy();
  });
  it('closes with the button and passes axe', async () => {
    const onClose = vi.fn();
    render(<ShortcutHelp onClose={onClose} />);
    expect(await axeCheck(document.body)).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });
});
