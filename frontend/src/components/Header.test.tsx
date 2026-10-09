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

  it('renders WS LIVE badge when feedStatus is WS_LIVE', () => {
    render(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="live"
            feedStatus="WS_LIVE"
            scanCycleCount={5}
            lastScanTime="12:00:00"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    expect(screen.getByText(/WS LIVE/i)).toBeInTheDocument();
  });

  it('renders HTTP Polling badge when in live mode but feedStatus is not WS_LIVE', () => {
    render(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="live"
            feedStatus="LIVE"
            scanCycleCount={5}
            lastScanTime="12:00:00"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    expect(screen.getByText(/HTTP Polling/i)).toBeInTheDocument();
  });

  it('displays countdown tooltip with remaining session hours', () => {
    render(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="live"
            feedStatus="WS_LIVE"
            scanCycleCount={5}
            lastScanTime="12:00:00"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
            tokenExpiryCountdown="23h 45m"
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    const countdownEl = screen.getByTitle(/remaining session hours/i);
    expect(countdownEl).toBeInTheDocument();
    expect(screen.getByText(/Token:\s*23h\s*45m/i)).toBeInTheDocument();
  });

  it('renders 1-Click Dhan OAuth Login tab in connect modal', () => {
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

    // Open connect modal
    const connectBtn = screen.getByRole('button', { name: /dhan/i });
    fireEvent.click(connectBtn);

    // Modal should show 1-Click Dhan OAuth tab and Connect with Dhan button
    expect(screen.getByText(/1-Click Dhan OAuth/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Connect with Dhan/i })).toBeInTheDocument();
  });
});

