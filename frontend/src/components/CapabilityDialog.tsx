import React from 'react';
import { AlertCircle, X, KeyRound, Lock, CheckCircle2 } from 'lucide-react';
import { Dialog } from './Dialog';

export const CapabilityDialog: React.FC<{
  value: string;
  onChange: (v: string) => void;
  error: string | null;
  success: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
}> = ({ value, onChange, error, success, onSubmit, onClose }) => (
  <Dialog label="Dashboard key" onClose={onClose} className="p-5" closeOnBackdrop={false}>
    <div className="flex items-center justify-between pb-3 mb-4" style={{ borderBottom: '1px solid var(--line)' }}>
      <div className="flex items-center gap-3">
        <KeyRound className="w-5 h-5" style={{ color: 'var(--accent)' }} aria-hidden="true" />
        <div>
          <h3 className="text-base font-semibold">Dashboard key</h3>
          <p className="text-xs desk-muted">Needed to trade, reset and stream live data</p>
        </div>
      </div>
      <button type="button" onClick={onClose} title="Close" aria-label="Close" className="desk-btn">
        <X className="w-4 h-4" />
      </button>
    </div>

    {error && (
      <div className="desk-alert mb-4 flex items-center gap-2" role="alert">
        <AlertCircle className="w-4 h-4 shrink-0" />
        <span>{error}</span>
      </div>
    )}
    {success && (
      <div className="desk-pill up mb-4 flex items-center gap-2" role="status" style={{ borderRadius: 8, padding: '8px 12px' }}>
        <CheckCircle2 className="w-4 h-4 shrink-0" />
        <span>Key accepted. Session started.</span>
      </div>
    )}

    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label htmlFor="capability-input" className="block text-xs font-semibold mb-1.5 desk-muted">
          Access key
        </label>
        <input
          id="capability-input"
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter your dashboard key"
          className="desk-input font-mono"
          required
        />
      </div>
      <div className="flex items-center justify-end gap-3">
        <button type="button" onClick={onClose} className="desk-btn">Cancel</button>
        <button type="submit" className="desk-btn solid">
          <Lock className="w-3.5 h-3.5" />
          Authorize session
        </button>
      </div>
    </form>
  </Dialog>
);
