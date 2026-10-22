import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dialog } from '../../components/Dialog';
import { rankCommands, type Command, type CommandContext } from './commandRegistry';

/** Accessible combobox dialog: type to filter, arrows to move, Enter to run, Escape to close (focus returns to the opener). */
export const CommandPalette: React.FC<{ commands: Command[]; ctx: CommandContext; onClose: () => void }> = ({ commands, ctx, onClose }) => {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const results = useMemo(() => rankCommands(query, commands), [query, commands]);
  const listRef = useRef<HTMLUListElement>(null);
  const clamped = Math.min(active, Math.max(0, results.length - 1));
  const optionId = (i: number) => `palette-opt-${i}`;

  useEffect(() => { setActive(0); }, [query]);
  useEffect(() => { listRef.current?.querySelector<HTMLElement>(`#${optionId(clamped)}`)?.scrollIntoView?.({ block: 'nearest' }); }, [clamped]);

  const run = (c: Command) => {
    onClose();
    // Let the palette unmount (and return focus) before a command opens its own dialog.
    setTimeout(() => { void c.run(ctx); }, 0);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(results.length ? (clamped + 1) % results.length : 0); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(results.length ? (clamped - 1 + results.length) % results.length : 0); }
    else if (e.key === 'Home') { e.preventDefault(); setActive(0); }
    else if (e.key === 'End') { e.preventDefault(); setActive(Math.max(0, results.length - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (results[clamped]) run(results[clamped]); }
  };

  return (
    <Dialog label="Command palette" onClose={onClose} className="p-0" style={{ alignSelf: 'flex-start', marginTop: '10vh' }}>
      <div style={{ width: 'min(560px, 92vw)' }} data-testid="command-palette">
        <label htmlFor="palette-input" className="sr-only">Type a command</label>
        <input id="palette-input" className="desk-input w-full" style={{ borderRadius: 0, padding: '10px 12px' }} placeholder="Type a command, panel or symbol" autoComplete="off" spellCheck={false}
          role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list" aria-activedescendant={results.length ? optionId(clamped) : undefined}
          value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKeyDown} />
        <ul id="palette-list" ref={listRef} role="listbox" aria-label="Commands" className="desk-scroll" style={{ maxHeight: '50vh', overflowY: 'auto' }} tabIndex={-1}>
          {results.map((c, i) => (
            <li key={c.id} id={optionId(i)} role="option" aria-selected={i === clamped} data-danger={c.danger || undefined}
              className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer" style={{ background: i === clamped ? 'var(--accent-soft)' : undefined }}
              onMouseMove={() => setActive(i)} onClick={() => run(c)}>
              <span className="min-w-0 flex-1 truncate">{c.danger && <span className="desk-pill down mr-2">Danger</span>}{c.title}</span>
              <span className="desk-muted text-xs">{c.group}</span>
              {c.hint && <kbd className="desk-num text-xs desk-muted">{c.hint}</kbd>}
            </li>
          ))}
        </ul>
        {results.length === 0 && <p className="px-3 py-4 text-sm desk-muted" role="status">No command matches “{query}”.</p>}
        <p className="px-3 py-1 text-xs desk-muted" style={{ borderTop: '1px solid var(--line)' }}>↑ ↓ to move, Enter to run, Esc to close. Dangerous commands only open a confirmation.</p>
      </div>
    </Dialog>
  );
};
