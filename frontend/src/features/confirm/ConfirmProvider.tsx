import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useDialog } from '../../components/useDialog';

export interface ConfirmOptions {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  /** Typed exactly (case-sensitive) before the confirm button enables. */
  phrase?: string;
}

type Confirm = (o: ConfirmOptions) => Promise<boolean>;

// Outside a provider every confirmation is refused: a money action never runs without the dialog.
const ConfirmContext = createContext<Confirm>(async () => false);

export function useConfirm(): Confirm {
  return useContext(ConfirmContext);
}

interface Pending { options: ConfirmOptions; resolve: (v: boolean) => void }

const ConfirmDialog: React.FC<{ pending: Pending; onDone: (v: boolean) => void }> = ({ pending, onDone }) => {
  const { options } = pending;
  const [typed, setTyped] = useState('');
  const ref = useDialog<HTMLDivElement>(() => onDone(false));
  const cancelRef = useRef<HTMLButtonElement>(null);
  // Declared after useDialog so it runs after the dialog's own focus move: danger dialogs open on Cancel.
  useEffect(() => { if (options.danger) cancelRef.current?.focus(); }, [options.danger]);
  const ready = !options.phrase || typed === options.phrase;
  const titleId = 'confirm-title';
  return (
    <div className="desk-overlay">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="desk-modal" onClick={(e) => e.stopPropagation()}>
        <div className="p-4 flex flex-col gap-3 text-sm" style={{ maxWidth: 440 }}>
          <h3 id={titleId} className="font-semibold">{options.title}</h3>
          <div>{options.body}</div>
          {options.phrase && (
            <label className="flex flex-col gap-1 text-xs">
              <span>Type <code>{options.phrase}</code> to confirm</span>
              <input className="desk-input" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} aria-label={`Type ${options.phrase} to confirm`} />
            </label>
          )}
          <div className="flex gap-2 justify-end">
            <button type="button" ref={cancelRef} className="desk-btn" onClick={() => onDone(false)}>Cancel</button>
            <button type="button" className={`desk-btn ${options.danger ? 'danger' : 'accent'}`} disabled={!ready} onClick={() => onDone(true)}>{options.confirmLabel}</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export const ConfirmProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [pending, setPending] = useState<Pending | null>(null);
  const queue = useRef<Pending[]>([]);

  const next = useCallback(() => { setPending(queue.current.shift() ?? null); }, []);
  const confirm = useCallback<Confirm>((options) => new Promise<boolean>((resolve) => {
    const item = { options, resolve };
    setPending((cur) => {
      if (cur) { queue.current.push(item); return cur; }
      return item;
    });
  }), []);

  const done = (v: boolean) => {
    pending?.resolve(v);
    next();
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && <ConfirmDialog key={pending.options.title + queue.current.length} pending={pending} onDone={done} />}
    </ConfirmContext.Provider>
  );
};
