export interface Shortcut {
  id: string;
  /** Display string, also parsed by matchShortcut: modifiers joined by +, e.g. `Ctrl+Shift+K`, `Alt+]`. */
  keys: string;
  description: string;
}

/** Single source of truth for hotkeys: conflicts are tested here, the help dialog and the dock read from here. */
export const SHORTCUTS: Shortcut[] = [
  { id: 'palette', keys: 'Ctrl+K', description: 'Open the command palette' },
  { id: 'killSwitch', keys: 'Ctrl+Shift+K', description: 'Open the kill switch confirmation (never executes)' },
  { id: 'help', keys: '?', description: 'Show keyboard shortcuts' },
  { id: 'focusNextGroup', keys: 'Alt+]', description: 'Focus next group' },
  { id: 'focusPrevGroup', keys: 'Alt+[', description: 'Focus previous group' },
  { id: 'nextTab', keys: 'Ctrl+Alt+ArrowRight', description: 'Next tab in group' },
  { id: 'prevTab', keys: 'Ctrl+Alt+ArrowLeft', description: 'Previous tab in group' },
  { id: 'movePanelNext', keys: 'Alt+Shift+]', description: 'Move panel to next group' },
  { id: 'movePanelPrev', keys: 'Alt+Shift+[', description: 'Move panel to previous group' },
  { id: 'maximise', keys: 'Alt+M', description: 'Maximise or restore the group' },
  { id: 'closePanel', keys: 'Alt+W', description: 'Close the panel' },
];

const norm = (k: string) => (k.length === 1 ? k.toLowerCase() : k);

/** Parses `Ctrl+Alt+ArrowRight` into modifier flags and a key. */
function parse(keys: string) {
  const parts = keys === '+' ? ['+'] : keys.split('+');
  const key = parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1));
  return { key: norm(key), ctrl: mods.has('Ctrl'), alt: mods.has('Alt'), shift: mods.has('Shift') };
}

/** Combos that are the same key plus the same modifiers; `Shift` is part of the identity for non-letter keys. */
export function hasConflicts(list: Shortcut[] = SHORTCUTS): string[] {
  const seen = new Map<string, string>();
  const out: string[] = [];
  for (const s of list) {
    const p = parse(s.keys);
    const sig = `${p.ctrl}|${p.alt}|${p.shift}|${p.key}`;
    const prev = seen.get(sig);
    if (prev) out.push(`${prev} and ${s.id} both use ${s.keys}`);
    else seen.set(sig, s.id);
  }
  return out;
}

const isTyping = (t: EventTarget | null): boolean => {
  const el = t as HTMLElement | null;
  if (!el || typeof el.tagName !== 'string') return false;
  const tag = el.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable === true;
};

/**
 * Returns the id of the shortcut the event triggers, or null. Events from text fields are ignored, except the
 * command palette and kill-switch confirmation, which work everywhere.
 */
export function matchShortcut(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'altKey' | 'shiftKey' | 'metaKey' | 'target'>, list: Shortcut[] = SHORTCUTS): string | null {
  const typing = isTyping(e.target);
  const key = norm(e.key);
  // Shifted brackets arrive as { and }; treat them as the bracket with Shift held.
  const shiftedMap: Record<string, string> = { '{': '[', '}': ']' };
  const base = shiftedMap[e.key] ?? key;
  for (const s of list) {
    const p = parse(s.keys);
    const globalWhileTyping = s.id === 'palette' || s.id === 'killSwitch';
    if (typing && !globalWhileTyping) continue;
    if (e.metaKey) continue;
    const wantsShift = p.shift;
    // '?' is typed with Shift on most layouts; its shift state is not significant.
    const shiftOk = p.key === '?' ? true : e.shiftKey === wantsShift;
    if (base === p.key && e.ctrlKey === p.ctrl && e.altKey === p.alt && shiftOk) return s.id;
  }
  return null;
}
