import { actions } from '../../data/actions';
import type { AppState } from '../../data/types';
import { formatCurrencyShort } from './format';
import type { DockCommands } from './dockCommands';
import { DOCK_COMMAND_ENTRIES } from './dockCommands';
import { SHORTCUTS } from '../shortcuts';
import type { PanelCategory } from '../../panels/registry';

type Confirm = (o: { title: string; body: React.ReactNode; confirmLabel: string; danger?: boolean; phrase?: string }) => Promise<boolean>;

export interface CommandContext {
  dock: DockCommands;
  switchWorkspace(name: string): void;
  /** Opens the layout dialogs that live in the workspace switcher. */
  layoutAction(action: 'saveAs' | 'reset'): void;
  confirm: Confirm;
  openKillSwitch(): Promise<void>;
  showHelp(): void;
  toggleTheme(): void;
  setDensity(d: 'compact' | 'comfortable'): void;
  refreshData(): void;
  select(sel: { kind: 'signal' | 'position'; id: string }): void;
}

export interface Command {
  id: string;
  title: string;
  keywords: string[];
  group: string;
  /** Shortcut text shown beside the result. */
  hint?: string;
  /** Dangerous commands only ever open a confirmation; they never act on their own. */
  danger?: boolean;
  run(ctx: CommandContext): void | Promise<void>;
}

export interface CommandInputs {
  panels: { id: string; title: string; category: PanelCategory }[];
  workspaces: string[];
  customs: string[];
  state: Pick<AppState, 'scanner' | 'watch'>;
  desktop: boolean;
}

const shortcutOf = (id?: string): string | undefined => (id ? SHORTCUTS.find((s) => s.id === id)?.keys : undefined);

/** Confirm, then close every open position one by one. Used only from the palette. */
export async function closeAllWithConfirm(confirm: Confirm, positions: { id: string; strike_symbol: string }[]): Promise<void> {
  if (positions.length === 0) return;
  const ok = await confirm({
    title: `Close all ${positions.length} open position${positions.length === 1 ? '' : 's'}?`,
    confirmLabel: 'Close all positions', danger: true, phrase: 'CLOSE ALL',
    body: `Every open paper position is closed at the current price: ${positions.map((p) => p.strike_symbol).join(', ')}.`,
  });
  if (!ok) return;
  for (const p of positions) await actions.closePosition(p.id);
}

export async function resetPortfolioWithConfirm(confirm: Confirm): Promise<void> {
  const ok = await confirm({
    title: 'Reset the paper portfolio?', confirmLabel: 'Reset portfolio', danger: true,
    body: 'Open positions are closed and the day\'s trades are archived (not deleted). This cannot be undone from the dashboard.',
  });
  if (ok) await actions.resetPortfolio();
}

/** Symbols the user can jump to: current signals, open positions, watched candidates and the index radar. */
export function symbolTargets(state: Pick<AppState, 'scanner' | 'watch'>): { symbol: string; kind: 'signal' | 'position'; id: string; detail: string }[] {
  const out = new Map<string, { symbol: string; kind: 'signal' | 'position'; id: string; detail: string }>();
  for (const p of state.scanner.paper_portfolio?.active_positions ?? []) {
    out.set(p.symbol, { symbol: p.symbol, kind: 'position', id: p.id, detail: `open ${p.strike_symbol} ${formatCurrencyShort(p.pnl_rupees)}` });
  }
  for (const s of state.scanner.signals) {
    if (!out.has(s.symbol)) out.set(s.symbol, { symbol: s.symbol, kind: 'signal', id: s.id, detail: `${s.option_type} signal` });
  }
  return [...out.values()].sort((a, b) => a.symbol.localeCompare(b.symbol));
}

export function registerCommands(input: CommandInputs): Command[] {
  const list: Command[] = [];
  for (const p of input.panels) {
    list.push({ id: `open:${p.id}`, title: `Open ${p.title}`, keywords: [p.id, p.category, 'panel', 'show'], group: 'Panels', run: (c) => c.dock.openPanel(p.id) });
  }
  if (input.desktop) {
    for (const name of [...input.workspaces, ...input.customs]) {
      list.push({ id: `workspace:${name}`, title: `Switch to ${name} workspace`, keywords: [name, 'workspace', 'layout', 'view'], group: 'Workspaces', run: (c) => c.switchWorkspace(name) });
    }
    list.push({ id: 'layout:save', title: 'Save layout as…', keywords: ['layout', 'workspace', 'store'], group: 'Layout', run: (c) => c.layoutAction('saveAs') });
    list.push({ id: 'layout:reset', title: 'Reset workspace to default', keywords: ['layout', 'restore', 'default'], group: 'Layout', run: (c) => c.layoutAction('reset') });
    for (const e of DOCK_COMMAND_ENTRIES) {
      if (e.id === 'resetWorkspace') continue;
      list.push({ id: `dock:${e.id}`, title: e.label, keywords: ['dock', 'panel', 'window'], group: 'Dock', hint: shortcutOf(e.shortcut), run: (c) => e.run(c.dock) });
    }
  }
  for (const t of symbolTargets(input.state)) {
    list.push({ id: `go:${t.symbol}`, title: `Go to ${t.symbol}`, keywords: [t.symbol, t.detail, 'symbol', 'select'], group: 'Symbols', run: (c) => c.select({ kind: t.kind, id: t.id }) });
  }
  list.push(
    { id: 'scan', title: 'Scan now', keywords: ['refresh', 'scanner'], group: 'Actions', run: () => { void actions.scanNow(); } },
    { id: 'refresh', title: 'Refresh data', keywords: ['reload', 'poll', 'update'], group: 'Actions', run: (c) => c.refreshData() },
    { id: 'theme', title: 'Toggle light or dark theme', keywords: ['dark', 'light', 'mode', 'appearance'], group: 'View', run: (c) => c.toggleTheme() },
    { id: 'density:compact', title: 'Density: compact', keywords: ['rows', 'spacing'], group: 'View', run: (c) => c.setDensity('compact') },
    { id: 'density:comfortable', title: 'Density: comfortable', keywords: ['rows', 'spacing'], group: 'View', run: (c) => c.setDensity('comfortable') },
    { id: 'help', title: 'Show keyboard shortcuts', keywords: ['help', 'keys', 'hotkeys'], group: 'Help', hint: shortcutOf('help'), run: (c) => c.showHelp() },
    { id: 'danger:kill', title: 'Kill switch… (opens a confirmation)', keywords: ['emergency', 'stop', 'halt', 'close everything'], group: 'Danger', danger: true, hint: shortcutOf('killSwitch'), run: (c) => c.openKillSwitch() },
    { id: 'danger:close-all', title: 'Close all positions… (opens a confirmation)', keywords: ['exit', 'flatten', 'square off'], group: 'Danger', danger: true,
      run: (c) => closeAllWithConfirm(c.confirm, (input.state.scanner.paper_portfolio?.active_positions ?? []).map((p) => ({ id: p.id, strike_symbol: p.strike_symbol }))) },
    { id: 'danger:reset', title: 'Reset paper portfolio… (opens a confirmation)', keywords: ['clear', 'archive', 'wipe'], group: 'Danger', danger: true, run: (c) => resetPortfolioWithConfirm(c.confirm) },
  );
  return list;
}

/**
 * Higher is better; 0 means no match. Exact title > title prefix > word prefix > substring > keyword > fuzzy (letters in order).
 */
export function scoreCommand(query: string, cmd: Pick<Command, 'title' | 'keywords'>): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const title = cmd.title.toLowerCase();
  if (title === q) return 1000;
  if (title.startsWith(q)) return 800 - Math.min(100, title.length - q.length);
  const words = title.split(/[\s…()]+/);
  if (words.some((w) => w.startsWith(q))) return 600 - Math.min(100, title.indexOf(q));
  const at = title.indexOf(q);
  if (at >= 0) return 400 - Math.min(100, at);
  if (cmd.keywords.some((k) => k.toLowerCase().includes(q))) return 300;
  // Letters in order, penalising gaps.
  let pos = 0;
  let gaps = 0;
  for (const ch of q.replace(/\s+/g, '')) {
    const i = title.indexOf(ch, pos);
    if (i < 0) return 0;
    gaps += i - pos;
    pos = i + 1;
  }
  return Math.max(1, 200 - gaps * 5);
}

export function rankCommands(query: string, commands: Command[], limit = 50): Command[] {
  const scored = commands.map((c, i) => ({ c, i, s: scoreCommand(query, c) })).filter((x) => x.s > 0);
  scored.sort((a, b) => b.s - a.s || a.i - b.i);
  return scored.slice(0, limit).map((x) => x.c);
}
