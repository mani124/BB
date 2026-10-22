import { lazy } from 'react';
import type { PanelDefinition } from './registry';

const def = (d: Omit<PanelDefinition, 'singleton'> & { singleton?: boolean }): PanelDefinition => ({ singleton: true, ...d });

/** Every panel the dock can show. Components are lazy so the dock shell stays small. */
export const DEFINITIONS: PanelDefinition[] = [
  def({ id: 'signals', title: 'Signals', icon: 'ListFilter', component: lazy(() => import('./signals')), category: 'trading', singleton: false, sources: ['scanner', 'watch'], defaultSize: { w: 19, h: 30 } }),
  def({ id: 'focus', title: 'Focus', icon: 'Crosshair', component: lazy(() => import('./focus')), category: 'trading', singleton: false, sources: ['scanner', 'portfolio', 'watch'] }),
  def({ id: 'positions', title: 'Open positions', icon: 'Briefcase', component: lazy(() => import('./positions')), category: 'trading', sources: ['portfolio', 'closedTrades'] }),
  def({ id: 'positions-table', title: 'Positions table', icon: 'Table2', component: lazy(() => import('./positions-table')), category: 'trading', sources: ['portfolio'] }),
  def({ id: 'chart', title: 'Chart', icon: 'LineChart', component: lazy(() => import('./chart')), category: 'trading', singleton: false, sources: ['scanner', 'portfolio'] }),
  def({ id: 'market', title: 'Market radar', icon: 'Radar', component: lazy(() => import('./market')), category: 'trading', sources: ['scanner'] }),
  def({ id: 'trades', title: 'Trades', icon: 'Receipt', component: lazy(() => import('./trades')), category: 'review', sources: ['trades'] }),
  def({ id: 'session', title: 'Session', icon: 'Clock', component: lazy(() => import('./session')), category: 'review', sources: ['trades'] }),
  def({ id: 'journal', title: 'Journal', icon: 'BookOpen', component: lazy(() => import('./journal')), category: 'review', sources: ['closedTrades'] }),
  def({ id: 'earnings', title: 'Earnings', icon: 'CalendarDays', component: lazy(() => import('./earnings')), category: 'books', sources: [] }),
  def({ id: 'settings', title: 'Settings', icon: 'Settings', component: lazy(() => import('./settings')), category: 'operations', sources: [] }),
  def({ id: 'live', title: 'Live routing', icon: 'Radio', component: lazy(() => import('./live')), category: 'operations', sources: ['live'] }),
  def({ id: 'controls', title: 'Controls', icon: 'SlidersHorizontal', component: lazy(() => import('./controls')), category: 'operations', sources: ['portfolio'] }),
  def({ id: 'telemetry', title: 'Telemetry', icon: 'Activity', component: lazy(() => import('./telemetry')), category: 'operations', sources: ['analytics'] }),
  def({ id: 'costs', title: 'Costs', icon: 'Coins', component: lazy(() => import('./costs')), category: 'performance', sources: ['analytics'] }),
  def({ id: 'setup-stats', title: 'Setup statistics', icon: 'BarChart3', component: lazy(() => import('./setup-stats')), category: 'performance', sources: ['analytics'] }),
];
