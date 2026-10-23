import React from 'react';
import { useApiData } from '../../data/hooks/useApiData';
import type { RiskGroup, RiskReport } from '../../features/analytics/types';
import { CONCENTRATION_MAX, CONCENTRATION_MIN, cleanConcentration, concentration } from '../../features/risk/entryState';
import { inr, pct } from '../../lib/numbers';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';
import { usePanelParams } from '../hooks';
import { AsyncStrip, Bar, Computed } from '../kit';

const DEFAULTS = { concentrationPct: 50 };

const GroupTable: React.FC<{ title: string; rows: RiskGroup[] }> = ({ title, rows }) => {
  const total = rows.reduce((a, r) => a + r.notional, 0);
  const max = Math.max(0, ...rows.map((r) => r.notional));
  return (
    <section aria-label={title} className="min-w-[16rem] flex-1">
      <h4 className="px-2 py-1 text-xs font-semibold">{title}</h4>
      {rows.length === 0 ? <p className="px-2 pb-2 text-xs desk-muted">None open.</p> : (
        <table className="desk-table" aria-label={`Exposure ${title}`}>
          <thead><tr><th scope="col">Name</th><th scope="col" className="r">Open</th><th scope="col" className="r">Premium</th><th scope="col" className="r">Risk ₹</th><th scope="col" className="r">Share</th><th scope="col"><span className="sr-only">Bar</span></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.key}</td><td className="r desk-num">{r.count}</td><td className="r desk-num">{inr(r.notional)}</td><td className="r desk-num">{inr(r.risk_rupees)}</td>
                <td className="r desk-num">{total > 0 ? pct((r.notional / total) * 100, 0) : '—'}</td><td style={{ width: '20%' }}><Bar value={r.notional} max={max} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
};

const ExposurePanel: React.FC<PanelProps> = (props) => {
  const [params, update] = usePanelParams(props, DEFAULTS);
  const threshold = cleanConcentration(params.concentrationPct);
  const api = useApiData<RiskReport>('/api/analytics/risk?book=paper', { refreshMs: 15_000 });
  const rep = api.data;
  const groups: [string, RiskGroup[]][] = rep ? [['underlying', rep.by_underlying], ['side', rep.by_side], ['pool', rep.by_pool], ['setup', rep.by_setup]] : [];
  // One row always holds 100 %, which says nothing about concentration.
  const hits = groups.filter(([, g]) => g.length > 1).map(([name, g]) => ({ name, ...concentration(g) })).filter((h) => h.pct >= threshold);
  return (
    <PanelFrame title="Exposure" sources={[]} onRetry={api.reload}
      actions={(
        <label className="flex items-center gap-1 text-xs">Alert at
          <input type="number" className="desk-input" style={{ width: '4.5rem' }} min={CONCENTRATION_MIN} max={CONCENTRATION_MAX} value={threshold} aria-label="Concentration alert threshold percent"
            onChange={(e) => update({ concentrationPct: cleanConcentration(Number(e.target.value)) })} />%
        </label>
      )}>
      <AsyncStrip state={api} onRetry={api.reload} what="exposure" />
      {hits.length > 0 && (
        <div className="desk-alert text-xs" role="status">
          Concentrated: {hits.map((h) => `${h.key} is ${pct(h.pct, 0)} of premium by ${h.name}`).join('; ')}.
        </div>
      )}
      {rep && rep.open.length === 0 && <p className="p-6 text-center text-sm desk-muted">No open positions, no exposure.</p>}
      {rep && rep.open.length > 0 && (
        <div className="flex flex-wrap">
          <GroupTable title="By underlying" rows={rep.by_underlying} />
          <GroupTable title="By side" rows={rep.by_side} />
          <GroupTable title="By pool" rows={rep.by_pool} />
          <GroupTable title="By setup" rows={rep.by_setup} />
        </div>
      )}
      <Computed at={rep?.generated_at} />
    </PanelFrame>
  );
};

export default ExposurePanel;
