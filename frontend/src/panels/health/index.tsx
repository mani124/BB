import React, { useState } from 'react';
import { useApp, useNow } from '../../data/appStore';
import { useApiData } from '../../data/hooks/useApiData';
import { useOptionalDhanAuth } from '../../context/DhanAuthContext';
import { buildTiles, diagnostics, type Tile } from '../../features/health/tiles';
import { pushToast } from '../../data/toasts';
import { formatIst } from '../../lib/time';
import { PanelFrame } from '../PanelFrame';
import { usePanelCommands } from '../PanelCommands';
import type { PanelProps } from '../registry';

const TONE: Record<Tile['state'], string> = { ok: 'up', warn: 'warn', down: 'down', unknown: 'mute' };

const HealthPanel: React.FC<PanelProps> = () => {
  const state = useApp((s) => ({ stream: s.stream, scanner: s.scanner, health: s.health, live: s.live, meta: s.meta }), (a, b) => a.stream === b.stream && a.scanner === b.scanner && a.health === b.health && a.live === b.live && a.meta === b.meta);
  const now = useNow(5000);
  const auth = useOptionalDhanAuth();
  const build = useApiData<{ version?: string }>('/api/health', { refreshMs: 300_000 });
  const { openPanel } = usePanelCommands();
  const [copied, setCopied] = useState(false);
  const tiles = buildTiles({ now, state, token: { loggedIn: Boolean(auth?.isLoggedIn), expiry: auth?.tokenExpiry ?? null }, version: build.data?.version });
  const copy = async () => {
    const text = diagnostics(tiles, { generatedAt: new Date(now).toISOString() });
    try { await navigator.clipboard.writeText(text); setCopied(true); pushToast(true, 'Diagnostics copied.'); } catch { pushToast(false, 'Could not copy diagnostics.'); }
  };
  return (
    <PanelFrame title="System health" sources={['health']} actions={<button type="button" className="desk-btn" onClick={() => void copy()}>{copied ? 'Copied' : 'Copy diagnostics'}</button>}>
      <ul className="grid gap-2 p-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(11rem, 1fr))' }} aria-label="Health tiles">
        {tiles.map((t) => (
          <li key={t.id} className="border border-line p-2 text-xs" data-tile={t.id} data-state={t.state}>
            <div className="flex items-center justify-between gap-1"><span className="font-semibold">{t.label}</span><span className={`desk-pill ${TONE[t.state]}`}>{t.word}</span></div>
            <p className="desk-muted mt-1">{t.detail}</p>
            <p className="desk-muted mt-1">{t.asOf ? `As of ${formatIst(t.asOf)} IST` : 'As of: n/a'}</p>
            {t.owner && <button type="button" className="desk-btn mt-1" onClick={() => openPanel(t.owner!)}>Open {t.owner}</button>}
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
};

export default HealthPanel;
