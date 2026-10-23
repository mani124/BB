import type { PanelId } from '../../panels/registry';

/** Operations on the dock. Implemented by the dock host (the only file that imports Dockview). */
export interface DockCommands {
  openPanel(id: PanelId, opts?: { newInstance?: boolean }): void;
  focusGroup(dir: 1 | -1): void;
  nextTab(): void;
  prevTab(): void;
  movePanelToGroup(dir: 1 | -1): void;
  split(dir: 'right' | 'down'): void;
  float(): void;
  dock(): void;
  popOut(): void;
  maximise(): void;
  close(): void;
  resetWorkspace(): void;
}

export const NOOP_COMMANDS: DockCommands = {
  openPanel: () => {}, focusGroup: () => {}, nextTab: () => {}, prevTab: () => {}, movePanelToGroup: () => {}, split: () => {},
  float: () => {}, dock: () => {}, popOut: () => {}, maximise: () => {}, close: () => {}, resetWorkspace: () => {},
};

export interface CommandEntry { id: string; label: string; hint?: string; run: (c: DockCommands) => void }

/** Every dock command is reachable from the palette; shortcut ids tie entries to SHORTCUTS where one exists. */
export const DOCK_COMMAND_ENTRIES: (CommandEntry & { shortcut?: string })[] = [
  { id: 'focusNextGroup', label: 'Focus next group', shortcut: 'focusNextGroup', run: (c) => c.focusGroup(1) },
  { id: 'focusPrevGroup', label: 'Focus previous group', shortcut: 'focusPrevGroup', run: (c) => c.focusGroup(-1) },
  { id: 'nextTab', label: 'Next tab', shortcut: 'nextTab', run: (c) => c.nextTab() },
  { id: 'prevTab', label: 'Previous tab', shortcut: 'prevTab', run: (c) => c.prevTab() },
  { id: 'movePanelNext', label: 'Move panel to next group', shortcut: 'movePanelNext', run: (c) => c.movePanelToGroup(1) },
  { id: 'movePanelPrev', label: 'Move panel to previous group', shortcut: 'movePanelPrev', run: (c) => c.movePanelToGroup(-1) },
  { id: 'splitRight', label: 'Split right', run: (c) => c.split('right') },
  { id: 'splitDown', label: 'Split down', run: (c) => c.split('down') },
  { id: 'float', label: 'Float panel', run: (c) => c.float() },
  { id: 'dock', label: 'Dock floating panel', run: (c) => c.dock() },
  { id: 'popOut', label: 'Pop out panel', run: (c) => c.popOut() },
  { id: 'maximise', label: 'Maximise or restore group', shortcut: 'maximise', run: (c) => c.maximise() },
  { id: 'closePanel', label: 'Close panel', shortcut: 'closePanel', run: (c) => c.close() },
  { id: 'resetWorkspace', label: 'Reset workspace', run: (c) => c.resetWorkspace() },
];
