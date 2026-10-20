import React, { useState } from 'react';
import { Activity, ArrowLeftRight, BookOpen, CalendarDays, Globe2, History, Layers, PanelLeftClose, PanelLeftOpen, Radar, Settings, SlidersHorizontal } from 'lucide-react';
import type { AppTab } from '../types';
import { Tabs } from './Tabs';
import type { ControlView } from './ControlScreen';

interface Props {
  activeTab: AppTab;
  activeView: ControlView | null;
  onTabChange: (tab: AppTab) => void;
  onOpenView: (view: ControlView) => void;
  openCount?: number | null;
}

const COLLAPSE_KEY = 'app_sidebar_collapsed';
const icon = 'h-[18px] w-[18px] shrink-0';

// Until the operator picks, laptops start with icons only so the tables keep their width.
const readCollapsed = (): boolean => {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    if (saved !== null) return saved === '1';
  } catch { /* storage unavailable */ }
  return typeof window !== 'undefined' && window.innerWidth < 1536;
};

const workspaces: { id: ControlView; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'legacy-review', label: 'Review and journal', Icon: BookOpen },
  { id: 'setup16', label: 'Setup 16', Icon: Layers },
  { id: 'cx', label: 'Commodities & FX', Icon: Globe2 },
  { id: 'earnings', label: 'Earnings', Icon: CalendarDays },
  { id: 'settings', label: 'Runtime settings', Icon: Settings },
];

/** Primary navigation: a left rail on laptops and desktops, a bottom bar on phones and tablets. */
export const Sidebar: React.FC<Props> = ({ activeTab, activeView, onTabChange, onOpenView, openCount }) => {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => setCollapsed((value) => {
    try { localStorage.setItem(COLLAPSE_KEY, value ? '0' : '1'); } catch { /* storage unavailable */ }
    return !value;
  });
  const label = (text: string, badge?: React.ReactNode) => (
    <>
      <span className="desk-nav-label">{text}</span>
      {badge}
    </>
  );
  return (
    <aside className="desk-rail" data-collapsed={collapsed} aria-label="Dashboard navigation">
      <div className="desk-rail-brand">
        <Activity className={icon} aria-hidden />
        <span className="desk-nav-label font-semibold text-base">BB Options</span>
      </div>
      <Tabs<AppTab>
        idPrefix="main"
        label="Sections"
        orientation="vertical"
        className="desk-rail-tabs"
        tabClassName="desk-nav"
        value={activeTab}
        onChange={onTabChange}
        items={[
          { id: 'watch', name: 'Watch', label: <><Radar className={icon} aria-hidden />{label('Watch', openCount ? <span className="desk-pill desk-num desk-nav-label ml-auto" title="Open positions">{openCount}</span> : null)}</> },
          { id: 'trades', name: 'Trades', label: <><ArrowLeftRight className={icon} aria-hidden />{label('Trades')}</> },
          { id: 'session', name: 'Session', label: <><History className={icon} aria-hidden />{label('Session')}</> },
          { id: 'control', name: 'Control', label: <><SlidersHorizontal className={icon} aria-hidden />{label('Control')}</> },
        ]}
      />
      <nav className="desk-rail-work" aria-label="Workspaces">
        <p className="desk-label desk-nav-label px-3 pb-1">Workspaces</p>
        {workspaces.map(({ id, label: text, Icon }) => (
          <button key={id} type="button" className="desk-nav" title={text} aria-label={`${text} workspace`}
            aria-current={activeView === id ? 'page' : undefined} onClick={() => onOpenView(id)}>
            <Icon className={icon} aria-hidden />
            <span className="desk-nav-label">{text}</span>
          </button>
        ))}
      </nav>
      <button type="button" className="desk-nav desk-rail-toggle" onClick={toggle} aria-pressed={collapsed}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
        {collapsed ? <PanelLeftOpen className={icon} aria-hidden /> : <PanelLeftClose className={icon} aria-hidden />}
        <span className="desk-nav-label">Collapse</span>
      </button>
    </aside>
  );
};
