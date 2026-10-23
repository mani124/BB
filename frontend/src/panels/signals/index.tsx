import React, { useMemo } from 'react';
import { SignalsPane, type SignalsView } from '../../components/SignalsPane';
import { useApp } from '../../data/appStore';
import { DEFAULT_FILTERS, filterSignals, type WatchFilters } from '../../data/selectors';
import { select, useSelection } from '../../data/selection';
import { PanelFrame } from '../PanelFrame';
import { usePanelParams } from '../hooks';
import type { PanelProps } from '../registry';

export interface SignalsParams extends Record<string, unknown> { filters: WatchFilters; view: SignalsView }

export const DEFAULT_SIGNALS_PARAMS: SignalsParams = {
  filters: DEFAULT_FILTERS,
  view: { mode: 'signals', sortBy: 'newest', bookFilter: 'all', statusFilter: 'all' },
};

const SignalsPanel: React.FC<PanelProps> = (props) => {
  const [params, update] = usePanelParams<SignalsParams>(props, DEFAULT_SIGNALS_PARAMS);
  const scanner = useApp((s) => s.scanner);
  const loaded = useApp((s) => s.meta.scanner.status !== 'idle');
  const watch = useApp((s) => s.watch);
  const selection = useSelection();
  const filters = { ...DEFAULT_FILTERS, ...params.filters };
  const signals = useMemo(() => filterSignals(scanner.signals, filters), [scanner.signals, filters.setup, filters.optionType, filters.instrumentType, filters.timeframe]); // eslint-disable-line react-hooks/exhaustive-deps
  const activeIds = useMemo(() => new Set((scanner.paper_portfolio?.active_positions ?? []).map((p) => p.signal_id)), [scanner.paper_portfolio?.active_positions]);

  return (
    <PanelFrame title="Signals and watch" sources={['scanner', 'watch']}>
      <SignalsPane state={scanner} signals={signals} loaded={loaded} activeSignalIds={activeIds} wsConnected={Boolean(scanner.ws_connected)}
        selectedSignalId={selection?.kind === 'signal' ? selection.id : null} onSelectSignal={(s) => select({ kind: 'signal', id: s.id })}
        filters={filters} onFilters={(f) => update({ filters: { ...filters, ...f } })}
        dashboardWatch={watch} selectedCandidateId={selection?.kind === 'candidate' ? selection.id : null} onSelectCandidate={(id) => select({ kind: 'candidate', id })}
        view={params.view} onViewChange={(v) => update({ view: { ...params.view, ...v } })} />
    </PanelFrame>
  );
};

export default SignalsPanel;
