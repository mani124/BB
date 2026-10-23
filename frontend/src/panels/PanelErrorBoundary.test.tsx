import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PanelErrorBoundary } from './PanelErrorBoundary';
import { alertsHook } from '../data/alertsHook';

let explode = true;
const Bomb: React.FC = () => { if (explode) throw new Error('boom'); return <p>fine</p>; };

describe('PanelErrorBoundary', () => {
  it('shows the reason, raises a warning and recovers on Try again', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const seen: string[] = [];
    const off = alertsHook.setSink((a) => seen.push(a.message));
    render(<PanelErrorBoundary panel="risk"><Bomb /></PanelErrorBoundary>);
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
    expect(seen).toEqual(['Panel risk failed to show: boom']);
    explode = false;
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByText('fine')).toBeTruthy();
    off(); spy.mockRestore();
  });
});
