import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { Header } from './Header';
import { ThemeProvider } from '../context/ThemeContext';
import { DhanAuthProvider } from '../context/DhanAuthContext';

describe('Header Theme Toggle', () => {
  it('renders theme toggle button and switches theme on click', () => {
    render(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="demo"
            scanCycleCount={1}
            lastScanTime="12:00:00"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    const themeToggleBtn = screen.getByRole('button', { name: /toggle theme/i });
    expect(themeToggleBtn).toBeInTheDocument();

    // Default theme is light
    expect(document.documentElement.classList.contains('light')).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    // Click toggle button
    fireEvent.click(themeToggleBtn);

    // Theme should now be dark
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });
});
