import React from 'react';
import { SETUP_MODE_OPTIONS, INDEX_MODE_OPTIONS, SETUP_SWITCH_ROWS } from '../../components/PaperPortfolioView';
import { actions, useInFlight } from '../../data/actions';
import { useApp } from '../../data/appStore';
import { openCapabilityDialog } from '../../data/auth';
import { useConfirm } from '../../features/confirm/ConfirmProvider';
import { KillSwitchButton } from '../../shell/KillSwitch';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const ControlsPanel: React.FC<PanelProps> = () => {
  const portfolio = useApp((s) => s.scanner.paper_portfolio);
  const confirm = useConfirm();
  const resetBusy = useInFlight('resetPortfolio');
  const scanBusy = useInFlight('scanNow');
  const auto = Boolean(portfolio?.auto_trade_enabled);

  const reset = async () => {
    const ok = await confirm({
      title: 'Reset the paper portfolio?',
      confirmLabel: 'Reset portfolio',
      danger: true,
      body: 'Open positions are closed and the day\'s trades are archived (not deleted). This cannot be undone from the dashboard.',
    });
    if (ok) await actions.resetPortfolio();
  };

  return (
    <PanelFrame title="Controls" sources={['portfolio']}>
      <div className="desk-scroll flex flex-col gap-3 p-3 text-sm" tabIndex={0} aria-label="Controls">
        <section aria-label="Entries" className="flex flex-wrap items-center gap-2">
          <span className="desk-label">Automatic entries</span>
          <button type="button" className={`desk-btn ${auto ? 'solid' : ''}`} aria-pressed={auto} disabled={!portfolio}
            onClick={() => { void actions.toggleAutoTrade(!auto); }}>
            Auto-enter: {auto ? 'ON' : 'OFF'}
          </button>
          <KillSwitchButton />
          <button type="button" className="desk-btn" disabled={scanBusy} onClick={() => { void actions.scanNow(); }}>Scan now</button>
          <button type="button" className="desk-btn" onClick={() => openCapabilityDialog()}>Dashboard key</button>
          <button type="button" className="desk-btn danger" disabled={resetBusy || !portfolio} onClick={() => { void reset(); }}>Reset portfolio</button>
        </section>
        <section aria-label="Setup modes">
          <h4 className="desk-label mb-1">Setup modes</h4>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-2">
            {SETUP_SWITCH_ROWS.map((row) => {
              const current = portfolio?.setup_modes?.[row.key] ?? 'all';
              return (
                <div key={row.key} className="flex items-center justify-between gap-3 text-xs">
                  <span>{row.label}</span>
                  <div className="desk-seg" role="group" aria-label={`${row.label} mode`}>
                    {(row.perIndex ? INDEX_MODE_OPTIONS : SETUP_MODE_OPTIONS).map((opt) => (
                      <button key={opt.mode} type="button" title={opt.title} aria-pressed={current === opt.mode} disabled={!portfolio}
                        onClick={() => { void actions.setSetupMode(row.key, opt.mode); }}>{opt.label}</button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </PanelFrame>
  );
};

export default ControlsPanel;
