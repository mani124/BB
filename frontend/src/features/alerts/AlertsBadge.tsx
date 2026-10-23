import React from 'react';
import { Bell } from 'lucide-react';
import { useAlerts } from './alertsStore';

/** Chrome button: bell with the count of unacknowledged critical alerts; opens the alerts panel. */
export const AlertsBadge: React.FC<{ onOpen: () => void }> = ({ onOpen }) => {
  const alerts = useAlerts();
  const crit = alerts.filter((a) => !a.acked && a.severity === 'critical').length;
  const unacked = alerts.filter((a) => !a.acked).length;
  return (
    <button type="button" className="desk-btn" onClick={onOpen} aria-label={`Alerts: ${unacked} unacknowledged, ${crit} critical`} title="Open alerts" data-testid="alerts-badge">
      <Bell className="h-3.5 w-3.5" aria-hidden />
      {crit > 0 ? <span className="desk-pill down nomark desk-num ml-1" data-testid="alerts-critical-count">{crit}</span> : unacked > 0 ? <span className="desk-num ml-1">{unacked}</span> : null}
    </button>
  );
};
