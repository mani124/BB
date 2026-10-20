import React from 'react';
import { connectionState, type ConnectionInput } from '../lib/connectionState';

/** The single connection pill: Live, Delayed, Stale, Disconnected, Demo data or Market closed. */
export const ConnectionStatus: React.FC<ConnectionInput> = (props) => {
  const state = connectionState(props);
  return (
    <span role="status" aria-live="polite" className={`desk-pill ${state.tone}`} title={state.detail}>
      <span className="desk-dot" />
      {state.label}
    </span>
  );
};

/** Shown over the data when prices may be out of date, so a frozen screen is never mistaken for a quiet market. */
export const ConnectionBanner: React.FC<ConnectionInput> = (props) => {
  const state = connectionState(props);
  if (!state.degraded) return null;
  return (
    <div role="alert" className={`desk-alert ${state.tone === 'warn' ? 'warn' : ''}`}>
      <strong>{state.label}.</strong> {state.detail}
    </div>
  );
};
