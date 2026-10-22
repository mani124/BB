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
    expect(screen.getByText(/All setups/i)).toBeInTheDocument();
    expect(screen.getByText(/S1 Squeeze/i)).toBeInTheDocument();
    expect(screen.getByText(/S2 Walking Bands/i)).toBeInTheDocument();
    expect(screen.getByText(/S3 W\/M Reversal/i)).toBeInTheDocument();
    expect(screen.getByText(/S4 9:30 ORB/i)).toBeInTheDocument();
    expect(screen.queryByText(/S5 Option BB Scalp/i)).not.toBeInTheDocument();   // Setup 5 was removed
    expect(screen.getByText(/S6 Pin Bar/i)).toBeInTheDocument();
    expect(screen.getByText(/S7 Inside Bar/i)).toBeInTheDocument();
    expect(screen.getByText(/S8 Divergence Fade/i)).toBeInTheDocument();

    // Fire click on Setup 6
    fireEvent.click(screen.getByText(/S6 Pin Bar/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 6: Pin Bar Exhaustion Snapback');

    // Fire click on Setup 7
    fireEvent.click(screen.getByText(/S7 Inside Bar/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 7: 2.5σ Puncture & Inside Bar');

    // Fire click on Setup 8
    fireEvent.click(screen.getByText(/S8 Divergence Fade/i));
    expect(handleSelectSetup).toHaveBeenCalledWith('Setup 8: Climax Swing Divergence Fade');
  });
});
