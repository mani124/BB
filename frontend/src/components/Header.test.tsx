import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { Header } from './Header';
import { ThemeProvider } from '../context/ThemeContext';
import { DhanAuthProvider } from '../context/DhanAuthContext';

describe('Header Theme Toggle', () => {
  it('offers four primary jobs with Watch first', () => {
    render(
      <ThemeProvider><DhanAuthProvider><Header activeMode="demo" scanCycleCount={0} lastScanTime="" isScanning={false}
        scanProgress={0} onScanNow={vi.fn()} activeTab="watch" onTabChange={vi.fn()} /></DhanAuthProvider></ThemeProvider>
    );
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent?.trim());
    expect(tabs).toEqual(['Watch', 'Trades', 'Session', 'Control']);
  });

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

    const themeToggleBtn = screen.getAllByRole('button', { name: /toggle theme/i })[0];
    expect(themeToggleBtn).toBeInTheDocument();

    // Default theme is light
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    // Click toggle button
    fireEvent.click(themeToggleBtn);

    // Theme should now be dark
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('renders Live badge when feedStatus is WS_LIVE', () => {
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

    expect(screen.getAllByText(/^Live$/).length).toBeGreaterThan(0);
  });

  it('renders Delayed badge when in live mode but feedStatus is not WS_LIVE', () => {
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

    expect(screen.getAllByText(/^Delayed$/).length).toBeGreaterThan(0);
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
    const connectBtn = screen.getAllByRole('button', { name: /connect dhan/i })[0];
    fireEvent.click(connectBtn);

    // Modal should show 1-Click Dhan OAuth tab and Connect with Dhan button
    expect(screen.getByText(/1-Click Dhan OAuth/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Connect with Dhan/i })).toBeInTheDocument();
  });

  it('renders Delayed badge when wsConnected is false in live mode', () => {
    const { rerender } = render(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="live"
            feedStatus="WS_LIVE"
            wsConnected={true}
            scanCycleCount={5}
            lastScanTime="12:00:00"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    expect(screen.getAllByText(/^Live$/).length).toBeGreaterThan(0);

    // Re-render with WebSocket disconnected / HTTP fallback
    rerender(
      <ThemeProvider>
        <DhanAuthProvider>
          <Header
            activeMode="live"
            feedStatus="LIVE"
            wsConnected={false}
            scanCycleCount={6}
            lastScanTime="12:00:08"
            isScanning={false}
            scanProgress={100}
            onScanNow={vi.fn()}
          />
        </DhanAuthProvider>
      </ThemeProvider>
    );

    expect(screen.queryByText(/^Live$/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Delayed$/).length).toBeGreaterThan(0);
  });
});


