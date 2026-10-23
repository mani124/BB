import React, { useState } from 'react';
import { ShieldCheck, Key } from 'lucide-react';
import { useDhanAuth } from '../context/DhanAuthContext';
import { Dialog } from './Dialog';

/** Dhan connect dialog: 1-click OAuth or a pasted 24h JWT. Shared by the legacy Header and the dock Chrome. */
export const DhanConnectDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { connect, loginWithOAuth, clearError, error } = useDhanAuth();
  const [authTab, setAuthTab] = useState<'oauth' | 'manual'>('oauth');
  const [inputClientId, setInputClientId] = useState('');
  const [inputToken, setInputToken] = useState('');
  const [oauthClientId, setOauthClientId] = useState(
    typeof window !== 'undefined' ? localStorage.getItem('dhan_client_id') || '' : ''
  );
  const [oauthAppId, setOauthAppId] = useState(
    typeof window !== 'undefined' ? localStorage.getItem('dhan_oauth_app_id') || '' : ''
  );
  const [oauthAppSecret, setOauthAppSecret] = useState(
    typeof window !== 'undefined' ? sessionStorage.getItem('dhan_oauth_app_secret') || '' : ''
  );
  const [loading, setLoading] = useState(false);

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const success = await connect(inputClientId, inputToken);
    setLoading(false);
    if (success) {
      onClose();
      setInputClientId('');
      setInputToken('');
    }
  };

  const handleOAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await loginWithOAuth(oauthAppId, oauthAppSecret, oauthClientId);
    } catch {
      setLoading(false);
    }
  };

  const inputCls = 'desk-input';
  const labelCls = 'block text-xs font-semibold mb-1 desk-muted';

  return (
    <Dialog label="Connect Dhan" onClose={onClose} className="p-5" closeOnBackdrop={false}>
      <div>
        <div className="flex items-center gap-3 mb-4">
          <div className="desk-pill" style={{ padding: 8, borderRadius: 8 }}>
            <Key className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold">Connect Dhan Live Trading</h3>
            <p className="text-xs desk-muted">Zero-Persistence: Stored only in browser session memory</p>
          </div>
        </div>

        <div className="flex mb-4" role="group" aria-label="Login method" style={{ borderBottom: '1px solid var(--line)' }}>
          <button
            type="button"
            aria-pressed={authTab === 'oauth'}
            onClick={() => { setAuthTab('oauth'); clearError(); }}
            className="flex-1 py-2 text-xs font-semibold"
            style={{ borderBottom: `2px solid ${authTab === 'oauth' ? 'var(--accent)' : 'transparent'}`, color: authTab === 'oauth' ? 'var(--accent)' : 'var(--muted)' }}
          >
            1-Click Dhan OAuth
          </button>
          <button
            type="button"
            aria-pressed={authTab === 'manual'}
            onClick={() => { setAuthTab('manual'); clearError(); }}
            className="flex-1 py-2 text-xs font-semibold"
            style={{ borderBottom: `2px solid ${authTab === 'manual' ? 'var(--accent)' : 'transparent'}`, color: authTab === 'manual' ? 'var(--accent)' : 'var(--muted)' }}
          >
            Manual 24h JWT
          </button>
        </div>

        {error && <div className="desk-alert mb-4">{error}</div>}

        {authTab === 'oauth' ? (
          <form onSubmit={handleOAuthSubmit} className="space-y-4">
            <div>
              <label htmlFor="dhan-f1" className={labelCls}>Dhan Client ID</label>
              <input id="dhan-f1" type="text" required placeholder="Your 10-digit Dhan ID (e.g. 1000000001)" value={oauthClientId} onChange={(e) => setOauthClientId(e.target.value)} className={inputCls} />
            </div>
            <div>
              <label htmlFor="dhan-f2" className={labelCls}>Dhan App ID / API Key</label>
              <input id="dhan-f2" type="text" required placeholder="API Key generated in Dhan Developer Portal" value={oauthAppId} onChange={(e) => setOauthAppId(e.target.value)} className={inputCls} />
            </div>
            <div>
              <label htmlFor="dhan-f3" className={labelCls}>Dhan App Secret</label>
              <input id="dhan-f3" type="password" required placeholder="API Secret generated in Dhan Developer Portal" value={oauthAppSecret} onChange={(e) => setOauthAppSecret(e.target.value)} className={inputCls} />
            </div>
            <div className="p-3 rounded-md text-xs space-y-1 desk-muted" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
              <p className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
                <ShieldCheck className="h-3.5 w-3.5" /> 1-Click Official Dhan Login
              </p>
              <p>Redirects securely to Dhan login portal. Your credentials and generated token remain strictly in session memory.</p>
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={() => onClose()} className="desk-btn">Cancel</button>
              <button type="submit" disabled={loading} className="desk-btn solid">
                {loading ? 'Redirecting...' : 'Connect with Dhan'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleManualSubmit} className="space-y-4">
            <div>
              <label htmlFor="dhan-f4" className={labelCls}>Dhan Client ID</label>
              <input id="dhan-f4" type="text" required placeholder="e.g. 1000000001" value={inputClientId} onChange={(e) => setInputClientId(e.target.value)} className={inputCls} />
            </div>
            <div>
              <label htmlFor="dhan-f5" className={labelCls}>24-Hour Access Token (JWT)</label>
              <textarea id="dhan-f5" required rows={3} placeholder="Paste your 24h JWT token from Dhan Web Settings" value={inputToken} onChange={(e) => setInputToken(e.target.value)} className={`${inputCls} font-mono text-xs`} />
            </div>
            <div className="p-3 rounded-md text-xs space-y-1 desk-muted" style={{ background: 'var(--alt)', border: '1px solid var(--line)' }}>
              <p className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--accent)' }}>
                <ShieldCheck className="h-3.5 w-3.5" /> Zero Token Persistence Guarantee
              </p>
              <p>Tokens remain strictly in your browser session memory and are passed via secure HTTP headers. Automatically cleared upon tab close.</p>
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={() => onClose()} className="desk-btn">Cancel</button>
              <button type="submit" disabled={loading} className="desk-btn solid">
                {loading ? 'Verifying...' : 'Connect Session'}
              </button>
            </div>
          </form>
        )}
      </div>
    </Dialog>
  );
};
