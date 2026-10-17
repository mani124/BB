import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IndexHeroRadar } from './IndexHeroRadar';

describe('IndexHeroRadar', () => {
  it('shows dashes, not invented VWAP/squeeze values, for an index with no data', () => {
    render(<IndexHeroRadar radar={{}} />);
    expect(screen.getAllByText('---')).toHaveLength(6);
    expect(screen.queryByLabelText(/VWAP/i)).not.toBeInTheDocument();
  });

  it('shows price, change and VWAP side for an index with data', () => {
    render(
      <IndexHeroRadar
        radar={{
          'NIFTY 50': {
            symbol: 'NIFTY 50', close: 24500, change_pct: -0.4, percent_b: 0.2, bandwidth: 1.1,
            is_squeeze: false, vwap_bias: 'BELOW_VWAP', rsi: 40, trend_state: 'RANGE',
          },
        }}
      />,
    );
    expect(screen.getByText('-0.40%')).toBeInTheDocument();
    expect(screen.getByLabelText('below VWAP')).toBeInTheDocument();
  });
});
