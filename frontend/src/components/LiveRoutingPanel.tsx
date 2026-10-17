import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Dialog } from './Dialog';
import type { LiveOrderRow, LiveStatus } from '../types';

const PHRASE = 'ENABLE LIVE TRADING';

async function call(path: string, body?: unknown): Promise<{ ok: boolean; data: any }> {
  const res = await apiFetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, data };
}

/** Mode, broker login and the two-step switch to live. Limits live in the Settings table below. */
export const LiveRoutingPanel: React.FC<{ initial?: LiveStatus; initialOrders?: LiveOrderRow[] }> = ({ initial, initialOrders }) => {
  const [st, setSt] = useState<LiveStatus | null>(initial ?? null);
  const [orders, setOrders] = useState<LiveOrderRow[]>(initialOrders ?? []);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [totp, setTotp] = useState('');
  const [arm, setArm] = useState<{ code: string } | null>(null);
  const [typedCode, setTypedCode] = useState('');
  const [typedPhrase, setTypedPhrase] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([apiFetch('/api/live/status'), apiFetch('/api/live/orders?limit=30')]);
      if (s.ok) setSt(await s.json());
      if (o.ok) { const od = await o.json(); setOrders(Array.isArray(od) ? od : []); }
    } catch { /* the panel keeps its last view */ }
  }, []);

  useEffect(() => {
    if (initial) return undefined;
    void load();
    const t = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(t);
  }, [initial, load]);

  const run = async (path: string, body?: unknown) => {
    setBusy(true); setErr(null);
    try {
      const r = await call(path, body);
      if (!r.ok) throw new Error(typeof r.data.detail === 'string' ? r.data.detail : 'Request failed');
      await load();
      return r.data;
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Request failed');
      return null;
    } finally { setBusy(false); }
  };

  if (!st) return <div className="desk-panel p-4 text-xs desk-muted">Loading live routing…</div>;

  const modeLabel = { off: 'Off', dry_run: 'Dry run (nothing is sent)', live: 'LIVE' }[st.mode];
  const startArm = async () => {
    const d = await run('/api/live/arm');
    if (d) { setArm({ code: d.code }); setTypedCode(''); setTypedPhrase(''); }
  };
  const enable = async () => {
    const d = await run('/api/live/enable', { code: typedCode.trim(), phrase: typedPhrase.trim() });
    if (d) setArm(null);
  };

  return (
    <section className="desk-panel" aria-label="Live broker routing" data-testid="live-routing">
      <div className="desk-ph">
        <h3>Live broker routing</h3>
        <span className={`desk-pill ${st.mode === 'live' ? 'down' : st.mode === 'dry_run' ? 'warn' : ''}`} role="status">{modeLabel}</span>
        {st.halted && <span className="desk-pill down">Halted: {st.halted}</span>}
      </div>
      {err && <div className="desk-alert m-3" role="alert">{err}</div>}
      <div className="p-3 flex flex-col gap-3 text-xs">
        <div className="desk-muted">
          Broker {st.broker} · session {st.broker_session ? 'connected' : 'not connected'} · entries today {st.entries_today} · orders today {st.orders_today} · routed P&amp;L today ₹{Math.round(st.realized_today).toLocaleString('en-IN')}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="desk-btn" disabled={busy || st.mode === 'off'} onClick={() => run('/api/live/mode', { mode: 'off' })}>Turn off</button>
          <button type="button" className="desk-btn" disabled={busy || st.mode === 'dry_run'} onClick={() => run('/api/live/mode', { mode: 'dry_run' })}>Dry run</button>
          <button type="button" className="desk-btn danger" disabled={busy || st.mode === 'live'} onClick={startArm}>Go live…</button>
          {st.halted && <button type="button" className="desk-btn" disabled={busy} onClick={() => run('/api/live/resume')}>Resume after check</button>}
          <button type="button" className="desk-btn" disabled={busy} onClick={() => run('/api/live/reconcile')}>Reconcile now</button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input className="desk-input desk-num" style={{ width: '9rem' }} inputMode="numeric" maxLength={6} placeholder="6-digit TOTP" aria-label="Broker TOTP" value={totp} onChange={(e) => setTotp(e.target.value)} />
          <button type="button" className="desk-btn" disabled={busy || totp.length !== 6} onClick={async () => { if (await run('/api/live/broker/login', { totp })) setTotp(''); }}>Log in to broker</button>
          <button type="button" className="desk-btn" disabled={busy || !st.broker_session} onClick={() => run('/api/live/broker/logout')}>Log out</button>
          <span className="desk-muted">The session key lives in server memory only and expires daily.</span>
        </div>

        {st.mode !== 'live' && st.preconditions.length > 0 && (
          <div className="desk-muted">Before going live: {st.preconditions.join('; ')}.</div>
        )}

        {st.positions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="desk-table">
              <thead><tr><th scope="col">Position</th><th scope="col">Setup</th><th scope="col">Mode</th><th scope="col">State</th><th scope="col" className="r">Held</th></tr></thead>
              <tbody>
                {st.positions.slice(0, 10).map((p) => (
                  <tr key={p.position_id}><td>{p.strike_symbol}</td><td>{p.setup}</td><td>{p.mode}</td><td>{p.state}{p.last_error ? ` · ${p.last_error}` : ''}</td><td className="r desk-num">{p.held}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="desk-table">
            <caption className="text-left desk-muted pb-1">Recent orders (dry-run rows show what would have been sent)</caption>
            <thead><tr><th scope="col">Time</th><th scope="col">Side</th><th scope="col">Mode</th><th scope="col">Contract</th><th scope="col" className="r">Qty</th><th scope="col" className="r">Price</th><th scope="col">Status</th><th scope="col">Note</th></tr></thead>
            <tbody>
              {orders.length === 0 && <tr><td colSpan={8} className="desk-muted">No orders yet.</td></tr>}
              {orders.map((o) => (
                <tr key={o.id}>
                  <td className="desk-num">{o.ts}</td><td>{o.side}</td><td>{o.mode}</td><td>{o.trading_symbol ?? ''}</td>
                  <td className="r desk-num">{o.filled_qty}/{o.qty}</td><td className="r desk-num">{o.price ? o.price.toFixed(2) : o.order_type ?? ''}</td>
                  <td>{o.status}</td><td style={{ whiteSpace: 'normal' }}>{o.message ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {arm && (
        <Dialog label="Enable live trading" onClose={() => setArm(null)} closeOnBackdrop={false}>
          <div className="p-4 flex flex-col gap-3 text-sm" style={{ maxWidth: 420 }}>
            <h3 className="font-semibold">Enable LIVE trading</h3>
            <p>Real orders will be sent to {st.broker} for the allowed setups, within the limits below. Exits always go through.</p>
            <p>Your one-time code is <strong className="desk-num" data-testid="arm-code">{arm.code}</strong> (valid 2 minutes). Type it, and the phrase <code>{PHRASE}</code>, to confirm.</p>
            <input className="desk-input desk-num" aria-label="One-time code" inputMode="numeric" value={typedCode} onChange={(e) => setTypedCode(e.target.value)} />
            <input className="desk-input" aria-label="Confirmation phrase" value={typedPhrase} onChange={(e) => setTypedPhrase(e.target.value)} placeholder={PHRASE} />
            {err && <div className="desk-alert" role="alert">{err}</div>}
            <div className="flex gap-2 justify-end">
              <button type="button" className="desk-btn" onClick={() => setArm(null)}>Cancel</button>
              <button type="button" className="desk-btn danger" disabled={busy || typedCode.trim().length !== 6 || typedPhrase.trim() !== PHRASE} onClick={enable}>Enable live</button>
            </div>
          </div>
        </Dialog>
      )}
    </section>
  );
};
