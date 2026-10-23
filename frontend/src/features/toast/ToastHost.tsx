import React from 'react';
import { X } from 'lucide-react';
import { dismissToast, useToasts } from '../../data/toasts';

/** Non-blocking action outcomes. Announced politely; failures are alerts. */
export const ToastHost: React.FC = () => {
  const toasts = useToasts();
  return (
    <div className="fixed bottom-8 right-3 z-50 flex flex-col gap-2" style={{ maxWidth: 'min(28rem, calc(100vw - 1.5rem))' }} data-testid="toast-host">
      {toasts.map((t) => (
        <div key={t.id} role={t.ok ? 'status' : 'alert'} className={`desk-panel flex items-start gap-2 px-3 py-2 text-xs shadow-md ${t.ok ? '' : 'desk-alert'}`}
          style={{ borderLeft: `3px solid ${t.ok ? 'var(--up)' : 'var(--down)'}` }}>
          <span className="min-w-0 flex-1">{t.ok ? 'Done: ' : 'Failed: '}{t.message}</span>
          <button type="button" aria-label="Dismiss" onClick={() => dismissToast(t.id)}><X className="h-3.5 w-3.5" aria-hidden /></button>
        </div>
      ))}
    </div>
  );
};
