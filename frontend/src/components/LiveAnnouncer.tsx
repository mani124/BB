import React from 'react';

/** Visually hidden polite live region: screen readers hear new signals and risk alerts. */
export const LiveAnnouncer: React.FC<{ message: string }> = ({ message }) => (
  <div className="sr-only" role="status" aria-live="polite" aria-atomic="true" data-testid="live-announcer">
    {message}
  </div>
);
