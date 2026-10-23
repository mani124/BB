import React from 'react';
import { alertsHook } from '../data/alertsHook';

interface Props { panel: string; children: React.ReactNode }
interface State { error: Error | null }

/** One failing panel must never take down the dock: show the reason and a Retry, and raise a warning. */
export class PanelErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State { return { error }; }

  componentDidCatch(error: Error): void {
    alertsHook.push({ severity: 'warning', source: 'panel', message: `Panel ${this.props.panel} failed to show: ${error.message}`.slice(0, 200) });
  }

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="desk-alert m-2 text-xs" role="alert">
        <p className="font-semibold">This panel could not be shown.</p>
        <p className="desk-muted">{this.state.error.message}</p>
        <button type="button" className="desk-btn mt-1" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
