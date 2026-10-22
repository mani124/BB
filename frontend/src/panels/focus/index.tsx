import React from 'react';
import { Pin, PinOff } from 'lucide-react';
import { FocusPane } from '../../components/FocusPane';
import { actions } from '../../data/actions';
import { useApp } from '../../data/appStore';
import { clearSelection, resolveSelection, select, useSelection, type Selection } from '../../data/selection';
import { PanelFrame } from '../PanelFrame';
import { usePanelCommands } from '../PanelCommands';
import { useConfirmedClose, usePanelParams } from '../hooks';
import type { PanelProps } from '../registry';

export interface FocusParams extends Record<string, unknown> { pinned: boolean; subject: Selection }
const DEFAULTS: FocusParams = { pinned: false, subject: null };

const FocusPanel: React.FC<PanelProps> = (props) => {
  const [params, update] = usePanelParams<FocusParams>(props, DEFAULTS);
  const selection = useSelection({ pinned: params.pinned, pinnedTo: params.subject ?? undefined });
  const state = useApp((s) => s);
  const { signal, position, candidate } = resolveSelection(state, selection);
  const trades = useApp((s) => s.trades);
  const activeIds = new Set((state.scanner.paper_portfolio?.active_positions ?? []).map((p) => p.signal_id));
  const closeConfirmed = useConfirmedClose();
  const commands = usePanelCommands();

  const pin = (
    <button type="button" className="desk-btn" aria-pressed={params.pinned} onClick={() => update({ pinned: !params.pinned, subject: params.pinned ? null : selection })}
      title={params.pinned ? 'Follow the selection again' : 'Keep showing this item'}>
      {params.pinned ? <PinOff className="h-3.5 w-3.5" aria-hidden /> : <Pin className="h-3.5 w-3.5" aria-hidden />}
      {params.pinned ? 'Unpin' : 'Pin'}
    </button>
  );

  return (
    <PanelFrame title="Focus" sources={['scanner', 'portfolio', 'watch']} actions={pin}>
      <FocusPane signal={signal ?? null} position={position ?? null} candidate={candidate ?? null} trades={trades}
        isBought={signal ? activeIds.has(signal.id) : false}
        onPaperBuy={(s) => { void actions.paperBuy(s); }}
        onClosePosition={(id) => { void closeConfirmed(id); }}
        onOpenTrade={(id) => { select({ kind: 'trade', id }); commands.openPanel('trades'); }}
        onClear={() => { if (params.pinned) update({ pinned: false, subject: null }); clearSelection(); }} />
    </PanelFrame>
  );
};

export default FocusPanel;
