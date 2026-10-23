import React from 'react';
import { RULES } from '../../features/alerts/rules';
import { ackAlert, ackAll, clearAcked, useAlerts } from '../../features/alerts/alertsStore';
import { appStore, useApp } from '../../data/appStore';
import { formatIst } from '../../lib/time';
import { PanelFrame } from '../PanelFrame';
import type { PanelProps } from '../registry';

const TONE = { info: 'mute', warning: 'warn', critical: 'down' } as const;

const AlertsPanel: React.FC<PanelProps> = () => {
  const alerts = useAlerts();
  const notify = useApp((s) => s.ui.notifications);
  const unacked = alerts.filter((a) => !a.acked).length;
  const setNotify = async (on: boolean) => {
    if (on && typeof Notification !== 'undefined' && Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch { /* the browser refused */ }
    }
    appStore.setState((s) => ({ ui: { ...s.ui, notifications: on } }));
  };
  return (
    <PanelFrame title="Alerts" sources={[]}
      actions={<><button type="button" className="desk-btn" disabled={unacked === 0} onClick={ackAll}>Acknowledge all</button><button type="button" className="desk-btn" disabled={alerts.every((a) => !a.acked)} onClick={clearAcked}>Clear acknowledged</button></>}>
      <p className="px-2 py-1 text-xs flex items-center gap-3">
        <span>{unacked} unacknowledged</span>
        <label className="flex items-center gap-1"><input type="checkbox" checked={notify} onChange={(e) => void setNotify(e.target.checked)} /> Browser notifications for critical alerts</label>
      </p>
      {alerts.length === 0 ? <p className="p-6 text-center text-sm desk-muted">No alerts.</p> : (
        <ul aria-label="Alerts, newest first">
          {alerts.map((a) => (
            <li key={a.id} className="flex items-start gap-2 px-2 py-1 text-xs" data-severity={a.severity} data-acked={a.acked || undefined} style={{ borderBottom: '1px solid var(--line)', opacity: a.acked ? 0.6 : 1 }}>
              <span className={`desk-pill ${TONE[a.severity]}`}>{a.severity}</span>
              <span className="desk-muted desk-num shrink-0">{formatIst(a.ts)}</span>
              <span className="desk-muted shrink-0">{a.source}</span>
              <span className="min-w-0 flex-1">{a.message}</span>
              {a.acked ? <span className="desk-muted">Acknowledged</span> : <button type="button" className="desk-btn" onClick={() => ackAlert(a.id)} aria-label={`Acknowledge: ${a.message}`}>Acknowledge</button>}
            </li>
          ))}
        </ul>
      )}
      <section aria-label="Alert rules" className="mt-2">
        <h4 className="px-2 py-1 text-xs font-semibold">What raises an alert</h4>
        <ul className="px-4 pb-2 text-xs list-disc">{RULES.map((r) => <li key={r.id}>{r.description}</li>)}</ul>
      </section>
    </PanelFrame>
  );
};

export default AlertsPanel;
