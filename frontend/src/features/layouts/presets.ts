import { LAYOUT_SCHEMA_VERSION, PRESET_VERSION, type LayoutNode, type LayoutSpec, type WorkspaceName } from './layoutModel';

const g = (ids: string[], extra: Record<string, { params?: Record<string, unknown>; title?: string }> = {}): LayoutNode => ({
  type: 'group',
  panels: ids.map((id) => ({ id, ...(extra[id] ?? {}) })),
  active: ids[0],
});
const row = (sizes: number[], ...children: LayoutNode[]): LayoutNode => ({ type: 'split', direction: 'row', sizes, children });
const col = (sizes: number[], ...children: LayoutNode[]): LayoutNode => ({ type: 'split', direction: 'column', sizes, children });

const spec = (name: WorkspaceName, root: LayoutNode): LayoutSpec => ({ schema_version: LAYOUT_SCHEMA_VERSION, name, preset_version: PRESET_VERSION, root });

/** Panels the presets name that are built in later phases; the preset test tightens to "registered only" at Phase 5. */
export const PLANNED_PANEL_IDS: string[] = ['risk', 'exposure', 'audit', 'alerts', 'perf-summary', 'equity', 'attribution', 'distributions', 'execution', 'orders', 'health', 'readiness', 'recorder', 'universe'];

export const PRESETS: Record<WorkspaceName, LayoutSpec> = {
  Trading: spec('Trading', row([0.22, 0.56, 0.22],
    g(['signals', 'signals#2'], { 'signals#2': { title: 'Earnings watch', params: { view: { mode: 'watching', sortBy: 'newest', bookFilter: 'earnings', statusFilter: 'all' } } } }),
    col([0.62, 0.38], g(['focus', 'chart']), g(['positions-table', 'trades', 'session'])),
    g(['positions', 'risk']))),
  Risk: spec('Risk', col([0.5, 0.5],
    row([0.4, 0.3, 0.3], g(['risk']), g(['exposure']), g(['controls'])),
    row([0.55, 0.45], g(['positions-table']), g(['audit', 'alerts'])))),
  Performance: spec('Performance', col([0.14, 0.43, 0.43],
    g(['perf-summary']),
    row([0.55, 0.45], g(['equity']), g(['attribution'])),
    row([0.5, 0.5], g(['distributions']), g(['setup-stats', 'costs'])))),
  Execution: spec('Execution', col([0.5, 0.5],
    row([0.55, 0.45], g(['execution']), g(['live', 'orders'])),
    row([0.4, 0.6], g(['costs']), g(['trades'])))),
  Review: spec('Review', col([0.55, 0.45],
    row([0.4, 0.3, 0.3], g(['session']), g(['journal']), g(['trades'])),
    g(['telemetry']))),
  Operations: spec('Operations', col([0.5, 0.5],
    row([0.4, 0.3, 0.3], g(['health']), g(['alerts']), g(['readiness', 'recorder'])),
    row([0.6, 0.4], g(['telemetry']), g(['universe', 'settings'])))),
  Earnings: spec('Earnings', g(['earnings'])),
};
