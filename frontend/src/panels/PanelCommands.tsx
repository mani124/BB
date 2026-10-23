import { createContext, useContext } from 'react';
import type { PanelId } from './registry';

export interface PanelCommands {
  /** Open (or focus) a panel by id, optionally in the current workspace's active group. */
  openPanel(id: PanelId): void;
}

/** Provided by the dock host (Task 3.3). Outside the dock, opening a panel is a no-op. */
export const PanelCommandsContext = createContext<PanelCommands>({ openPanel: () => {} });
export const usePanelCommands = (): PanelCommands => useContext(PanelCommandsContext);
