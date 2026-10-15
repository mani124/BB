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
}) => (
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
