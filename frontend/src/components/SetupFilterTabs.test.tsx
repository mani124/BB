import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SetupFilterTabs } from './SetupFilterTabs';

describe('SetupFilterTabs', () => {
  it('renders all 8 strategy setup filter buttons and All Setups', () => {
    const handleSelectSetup = vi.fn();

    render(
      <SetupFilterTabs
        selectedSetup="ALL"
        onSelectSetup={handleSelectSetup}
        selectedOptionType="ALL"
        onSelectOptionType={() => {}}
        selectedInstrumentType="ALL"
        onSelectInstrumentType={() => {}}
        selectedTimeframe="ALL"
        onSelectTimeframe={() => {}}
        totalSignals={0}
      />
    );

    // Verify all 8 setups are rendered
    expect(screen.getByText(/All Setups/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 1: Squeeze Breakout/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 2: Walking Bands/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 3: W\/M Reversal/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 4: 9:30 AM ORB/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 5: Option BB Scalp/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 6: Pin Bar Snapback/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 7: 2.5σ Inside Bar/i)).toBeInTheDocument();
    expect(screen.getByText(/Setup 8: Divergence Fade/i)).toBeInTheDocument();

    // Fire click on Setup 6
    fireEvent.click(screen.getByText(/Setup 6: Pin Bar Snapback/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 6: Pin Bar Exhaustion Snapback');

    // Fire click on Setup 7
    fireEvent.click(screen.getByText(/Setup 7: 2.5σ Inside Bar/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 7: 2.5σ Puncture & Inside Bar');

    // Fire click on Setup 8
    fireEvent.click(screen.getByText(/Setup 8: Divergence Fade/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 8: Climax Swing Divergence Fade');
  });
});
