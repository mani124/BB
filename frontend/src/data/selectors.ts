import { isIndexSymbol } from '../components/instruments';
import type { Signal } from '../types';
import type { AppState } from './types';

export interface WatchFilters { setup: string; optionType: string; instrumentType: string; timeframe: string }

export const DEFAULT_FILTERS: WatchFilters = { setup: 'ALL', optionType: 'ALL', instrumentType: 'ALL', timeframe: 'ALL' };

export function filterSignals(signals: Signal[], f: WatchFilters): Signal[] {
  return signals.filter((sig) => {
    if (f.setup !== 'ALL') {
      const t = sig.setup_type ?? '';
      const match = t === f.setup || t.toLowerCase().includes(f.setup.toLowerCase()) || f.setup.toLowerCase().includes(t.toLowerCase());
      if (!match) return false;
    }
    if (f.optionType !== 'ALL' && sig.option_type !== f.optionType) return false;
    const isIndex = isIndexSymbol(sig.symbol);
    if (f.instrumentType === 'INDEX' && !isIndex) return false;
    if (f.instrumentType === 'STOCK' && isIndex) return false;
    if (f.timeframe !== 'ALL' && sig.timeframe !== f.timeframe) return false;
    return true;
  });
}

export const selectFilteredSignals = (state: AppState, filters: WatchFilters): Signal[] => filterSignals(state.scanner.signals, filters);

export const selectActiveSignalIds = (state: AppState): string[] => (state.scanner.paper_portfolio?.active_positions ?? []).map((p) => p.signal_id);
