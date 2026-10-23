import { describe, it, expect } from 'vitest';
import { SHORTCUTS, hasConflicts, matchShortcut } from './shortcuts';
import { DOCK_COMMAND_ENTRIES, NOOP_COMMANDS } from './commands/dockCommands';

const ev = (key: string, mods: Partial<{ ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }> = {}, target: unknown = document.body) =>
  ({ key, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods, target }) as never;

describe('shortcuts', () => {
  it('has no conflicting combos', () => { expect(hasConflicts()).toEqual([]); });
  it('detects a conflict when one is introduced', () => {
    expect(hasConflicts([...SHORTCUTS, { id: 'dup', keys: 'Alt+M', description: 'x' }])).toHaveLength(1);
  });
  it('contains the spec list plus palette, kill switch and help', () => {
    const ids = SHORTCUTS.map((s) => s.id);
    for (const id of ['palette', 'killSwitch', 'help', 'focusNextGroup', 'focusPrevGroup', 'nextTab', 'prevTab', 'movePanelNext', 'movePanelPrev', 'maximise', 'closePanel']) expect(ids).toContain(id);
  });
  it('matches the documented combos', () => {
    expect(matchShortcut(ev('k', { ctrlKey: true }))).toBe('palette');
    expect(matchShortcut(ev('K', { ctrlKey: true, shiftKey: true }))).toBe('killSwitch');
    expect(matchShortcut(ev(']', { altKey: true }))).toBe('focusNextGroup');
    expect(matchShortcut(ev('[', { altKey: true }))).toBe('focusPrevGroup');
    expect(matchShortcut(ev('}', { altKey: true, shiftKey: true }))).toBe('movePanelNext');
    expect(matchShortcut(ev('{', { altKey: true, shiftKey: true }))).toBe('movePanelPrev');
    expect(matchShortcut(ev('ArrowRight', { ctrlKey: true, altKey: true }))).toBe('nextTab');
    expect(matchShortcut(ev('m', { altKey: true }))).toBe('maximise');
    expect(matchShortcut(ev('w', { altKey: true }))).toBe('closePanel');
    expect(matchShortcut(ev('?', { shiftKey: true }))).toBe('help');
  });
  it('does not mistake Ctrl+Shift+K for the palette', () => {
    expect(matchShortcut(ev('K', { ctrlKey: true, shiftKey: true }))).not.toBe('palette');
  });
  it('ignores typing in inputs except palette and kill switch', () => {
    const input = document.createElement('input');
    expect(matchShortcut(ev('?', { shiftKey: true }, input))).toBeNull();
    expect(matchShortcut(ev('w', { altKey: true }, input))).toBeNull();
    expect(matchShortcut(ev('k', { ctrlKey: true }, input))).toBe('palette');
    const ta = document.createElement('textarea');
    expect(matchShortcut(ev('m', { altKey: true }, ta))).toBeNull();
  });
  it('ignores events with the meta key', () => { expect(matchShortcut(ev('k', { ctrlKey: true, metaKey: true }))).toBeNull(); });
});

describe('dock commands', () => {
  it('every DockCommands method has a palette entry', () => {
    const methods = Object.keys(NOOP_COMMANDS).filter((k) => k !== 'openPanel');
    const called = new Set<string>();
    const spy = Object.fromEntries(Object.keys(NOOP_COMMANDS).map((k) => [k, () => called.add(k)])) as never;
    for (const e of DOCK_COMMAND_ENTRIES) e.run(spy);
    for (const m of methods) expect(called.has(m), m).toBe(true);
  });
  it('every shortcut tied to a command exists in SHORTCUTS', () => {
    const ids = new Set(SHORTCUTS.map((s) => s.id));
    for (const e of DOCK_COMMAND_ENTRIES) if (e.shortcut) expect(ids.has(e.shortcut), e.id).toBe(true);
  });
  it('every dock shortcut maps to a command entry', () => {
    const dockShortcuts = SHORTCUTS.filter((s) => !['palette', 'killSwitch', 'help'].includes(s.id));
    const mapped = new Set(DOCK_COMMAND_ENTRIES.map((e) => e.shortcut));
    for (const s of dockShortcuts) expect(mapped.has(s.id), s.id).toBe(true);
  });
});
