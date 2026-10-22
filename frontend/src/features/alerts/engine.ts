import { appStore } from '../../data/appStore';
import type { Alert } from '../../data/types';
import { evaluateRules } from './rules';
import { installAlertSink, pushAlert, restoreAlerts } from './alertsStore';

export interface EngineOptions {
  /** Called once for every new critical alert (screen-reader announcement, browser notification). */
  onCritical?: (a: Alert) => void;
}

/** Starts the alerts engine: restores saved alerts, installs the sink and evaluates the rules on every store change. */
export function startAlertsEngine(opts: EngineOptions = {}): () => void {
  restoreAlerts();
  const removeSink = installAlertSink();
  let prev = appStore.getState();
  const unsub = appStore.subscribe(() => {
    const next = appStore.getState();
    const before = prev;
    prev = next;
    if (before === next) return;
    // Changes to the alert list itself never raise alerts (and must not loop).
    if (before.alerts !== next.alerts && before.scanner === next.scanner && before.health === next.health && before.live === next.live && before.stream === next.stream && before.ui === next.ui && before.closedTrades === next.closedTrades) return;
    for (const input of evaluateRules(before, next)) {
      const a = pushAlert(input);
      if (a && a.severity === 'critical') opts.onCritical?.(a);
    }
    prev = appStore.getState();
  });
  return () => { unsub(); removeSink(); };
}
