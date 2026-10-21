import React from 'react';

interface SetupFilterTabsProps {
  selectedSetup: string;
  onSelectSetup: (setup: string) => void;
  selectedOptionType: string;
  onSelectOptionType: (opt: string) => void;
  selectedInstrumentType: string;
  onSelectInstrumentType: (inst: string) => void;
  selectedTimeframe: string;
  onSelectTimeframe: (tf: string) => void;
  totalSignals: number;
  // Kept for compatibility with older callers; the desk layout only has the table view.
  /** Single-row layout (setup dropdown + segmented filters) for the Watch screen. */
  compact?: boolean;
  viewMode?: 'grid' | 'table';
  onSelectViewMode?: (mode: 'grid' | 'table') => void;
}

export const SETUP_FILTERS: { key: string; label: string; title: string }[] = [
  { key: 'ALL', label: 'All setups', title: 'All setups' },
  { key: 'Setup 1: BB Squeeze Breakout', label: 'S1 Squeeze', title: 'Setup 1: Squeeze Breakout' },
  { key: 'Setup 2: Walking the Bands (9 EMA)', label: 'S2 Walking Bands', title: 'Setup 2: Walking Bands (9 EMA)' },
  { key: 'Setup 3: W/M Reversal', label: 'S3 W/M Reversal', title: 'Setup 3: W/M Reversal' },
  { key: 'Setup 4: 9:30 AM Opening Range Breakout', label: 'S4 9:30 ORB', title: 'Setup 4: 9:30 AM ORB' },
  { key: 'Setup 5: Option Chart BB Scalp', label: 'S5 Option BB Scalp', title: 'Setup 5: Option BB Scalp' },
  { key: 'Setup 6: Pin Bar Exhaustion Snapback', label: 'S6 Pin Bar', title: 'Setup 6: Pin Bar Snapback' },
  { key: 'Setup 7: 2.5σ Puncture & Inside Bar', label: 'S7 Inside Bar', title: 'Setup 7: 2.5σ Inside Bar' },
  { key: 'Setup 8: Climax Swing Divergence Fade', label: 'S8 Divergence Fade', title: 'Setup 8: Divergence Fade' },
  { key: 'Setup 9: Relative Strength vs NIFTY (9 EMA Pullback)', label: 'S9 Rel. Strength', title: 'Setup 9: Relative Strength vs NIFTY' },
  { key: 'Setup 10: ATM Straddle Premium Squeeze', label: 'S10 Straddle Squeeze', title: 'Setup 10: ATM Straddle Premium Squeeze' },
  { key: 'Setup 12: ADX + EMA 20 Trend Cross', label: 'S12 ADX EMA Cross', title: 'Setup 12: ADX + EMA 20 Trend Cross' },
  { key: 'Setup 13: Option VWAP Reclaim', label: 'S13 Option VWAP', title: 'Setup 13: Option VWAP Reclaim' },
  { key: 'Setup 14: OI Wall Bounce', label: 'S14 OI Wall', title: 'Setup 14: OI Wall Bounce' },
  { key: 'Setup 20: T315 EMA 3/15 Cross', label: 'S20 T315 EMA Cross', title: 'Setup 20: T315 EMA 3/15 Cross (index)' },
  { key: 'Setup 21: T315-F 3m', label: 'S21 T315-F 3m', title: 'Setup 21: T315-F 3m (Nifty, Bank Nifty)' },
  { key: 'Setup 22: T315-F 5m', label: 'S22 T315-F 5m', title: 'Setup 22: T315-F 5m (Nifty, Bank Nifty)' },
  { key: 'Setup 23: T315-F 5m wide', label: 'S23 T315-F 5m wide', title: 'Setup 23: T315-F 5m wide (Nifty, Bank Nifty)' },
];

const Seg: React.FC<{
  label: string;
  options: { key: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}> = ({ label, options, value, onChange }) => (
  <div className="flex items-center gap-2">
    <span className="desk-label">{label}</span>
    <div className="desk-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)}>
          {o.label}
        </button>
      ))}
    </div>
  </div>
);

export const SetupFilterTabs: React.FC<SetupFilterTabsProps> = ({
  selectedSetup,
  onSelectSetup,
  selectedOptionType,
  onSelectOptionType,
  selectedInstrumentType,
  onSelectInstrumentType,
  selectedTimeframe,
  onSelectTimeframe,
  totalSignals,
  compact = false,
}) => compact ? (
  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3.5 py-2" style={{ borderBottom: '1px solid var(--line)' }}>
    <label className="flex items-center gap-2">
      <span className="desk-label">Setup</span>
      <select
        className="desk-input"
        style={{ width: 'auto', padding: '3px 8px' }}
        value={selectedSetup}
        onChange={(e) => onSelectSetup(e.target.value)}
        aria-label="Setup filter"
      >
        {SETUP_FILTERS.map(({ key, label, title }) => (
          <option key={key} value={key} title={title}>{label}</option>
        ))}
      </select>
    </label>
    <Seg label="Side" value={selectedOptionType} onChange={onSelectOptionType} options={[{ key: 'ALL', label: 'Both' }, { key: 'CE', label: 'CE' }, { key: 'PE', label: 'PE' }]} />
    <Seg label="Universe" value={selectedInstrumentType} onChange={onSelectInstrumentType} options={[{ key: 'ALL', label: 'All' }, { key: 'INDEX', label: 'Idx' }, { key: 'STOCK', label: 'Stk' }]} />
    <Seg label="TF" value={selectedTimeframe} onChange={onSelectTimeframe} options={[{ key: 'ALL', label: 'All' }, { key: '5m', label: '5m' }, { key: '15m', label: '15m' }]} />
  </div>
) : (
  <div className="desk-panel px-3.5 py-3 flex flex-col gap-3">
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Setups">
      {SETUP_FILTERS.map(({ key, label, title }) => (
        <button
          key={key}
          type="button"
          className="desk-chip"
          title={title}
          aria-pressed={selectedSetup === key}
          onClick={() => onSelectSetup(key)}
        >
          {label}
        </button>
      ))}
    </div>
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <Seg
        label="Direction"
        value={selectedOptionType}
        onChange={onSelectOptionType}
        options={[
          { key: 'ALL', label: 'Both' },
          { key: 'CE', label: 'CE' },
          { key: 'PE', label: 'PE' },
        ]}
      />
      <Seg
        label="Universe"
        value={selectedInstrumentType}
        onChange={onSelectInstrumentType}
        options={[
          { key: 'ALL', label: 'All' },
          { key: 'INDEX', label: 'Indices' },
          { key: 'STOCK', label: 'Stocks' },
        ]}
      />
      <Seg
        label="Timeframe"
        value={selectedTimeframe}
        onChange={onSelectTimeframe}
        options={[
          { key: 'ALL', label: 'All' },
          { key: '5m', label: '5m' },
          { key: '15m', label: '15m' },
        ]}
      />
      <span className="ml-auto text-xs desk-muted">
        Filtered signals: <b className="desk-num" style={{ color: 'var(--accent)' }}>{totalSignals}</b>
      </span>
    </div>
  </div>
);
