import type React from 'react';
import type { SliceName } from '../data/types';
import { DEFINITIONS } from './definitions';

export type PanelId = string;
export type PanelCategory = 'trading' | 'risk' | 'performance' | 'execution' | 'operations' | 'books' | 'review';

/** The slice of the Dockview panel API that panels may use. Panels never import Dockview. */
export interface DockPanelApi {
  setTitle?(title: string): void;
  close?(): void;
  setActive?(): void;
  readonly id?: string;
}

export interface PanelProps {
  id: PanelId;
  params: Record<string, unknown>;
  setParams(p: Record<string, unknown>): void;
  api?: DockPanelApi;
}

export interface PanelDefinition {
  /** Stable, never reused. */
  id: PanelId;
  title: string;
  icon: string;
  component: React.LazyExoticComponent<React.ComponentType<PanelProps>> | React.ComponentType<PanelProps>;
  category: PanelCategory;
  singleton: boolean;
  defaultSize?: { w: number; h: number };
  sources: SliceName[];
  /** Validates saved per-panel params; returns a cleaned object (unknown keys dropped). */
  validateParams?: (raw: Record<string, unknown>) => Record<string, unknown>;
  minWidth?: number;
  minHeight?: number;
}

/** Throws on a duplicate id (a registry mistake must never ship). */
export function validateRegistry(defs: PanelDefinition[]): PanelDefinition[] {
  const seen = new Set<string>();
  for (const d of defs) {
    if (seen.has(d.id)) throw new Error(`Duplicate panel id: ${d.id}`);
    seen.add(d.id);
  }
  return defs;
}

/** All panels; the list itself lives in definitions.ts. */
export const PANELS: PanelDefinition[] = validateRegistry(DEFINITIONS);

export function getPanel(id: PanelId, defs: PanelDefinition[] = PANELS): PanelDefinition | undefined {
  return defs.find((d) => d.id === id);
}
