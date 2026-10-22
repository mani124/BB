import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DhanAuthProvider, useDhanAuth } from '../context/DhanAuthContext';
import { ThemeProvider } from '../context/ThemeContext';
import { CapabilityDialog } from '../components/CapabilityDialog';
import { ConnectionBanner } from '../components/ConnectionStatus';
import { LiveAnnouncer } from '../components/LiveAnnouncer';
import { ConfirmProvider } from '../features/confirm/ConfirmProvider';
import { ToastHost } from '../features/toast/ToastHost';
import { appStore, useApp } from '../data/appStore';
import { closeCapabilityDialog, ensureSession, getDashboardCapability, submitCapability } from '../data/auth';
import { startPollers } from '../data/pollers';
import { startStream } from '../data/stream';
import { Chrome } from './Chrome';
import { DockHost } from './dockHost';
import { MobileShell } from './MobileShell';
import { useDesktopMedia } from './useDesktopMedia';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import { ShortcutHelp } from '../features/commands/ShortcutHelp';
import { DOCK_COMMAND_ENTRIES, NOOP_COMMANDS, type DockCommands } from '../features/commands/dockCommands';
import { matchShortcut } from '../features/shortcuts';
import { useLayouts } from '../features/layouts/useLayouts';
import { startAlertsEngine } from '../features/alerts/engine';
import { CommandPalette } from '../features/commands/CommandPalette';
import { registerCommands, type CommandContext } from '../features/commands/commandRegistry';
import { requestLayoutAction } from '../features/layouts/layoutUi';
import { useConfirm } from '../features/confirm/ConfirmProvider';
import { useKillSwitchDialog } from './KillSwitch';
import { setDensity } from './Chrome';
import { useTheme } from '../context/ThemeContext';
import { select } from '../data/selection';
import { pollNow } from '../data/pollers';
import { refreshPortfolio } from '../data/actions';
import { PANELS } from '../panels/registry';
import { Search } from 'lucide-react';
import { useAnnouncements } from '../features/alerts/announce';
import { AlertsBadge } from '../features/alerts/AlertsBadge';
import { ModeBanner } from './ModeBanner';
import { StatusBar } from './StatusBar';

/** Demo mode with a real saved token: reconnect once, as the legacy shell does (sentinel tokens are ignored). */
function useDhanAutoReconnect(): void {
  const { connect, isLoggedIn, tokenExpiry } = useDhanAuth();
  useEffect(() => { appStore.setState((st) => ({ ui: { ...st.ui, dhan: { loggedIn: isLoggedIn, expiry: tokenExpiry } } })); }, [isLoggedIn, tokenExpiry]);
  const activeMode = useApp((s) => s.scanner.active_mode);
  const busy = useRef(false);
  useEffect(() => {
    if (activeMode !== 'demo' || busy.current) return;
    let savedId: string | null = null;
    let savedToken: string | null = null;
    try { savedId = localStorage.getItem('dhan_client_id'); savedToken = localStorage.getItem('dhan_access_token'); } catch { return; }
    if (savedId && savedToken && !savedToken.includes('*') && savedToken !== 'server_active' && savedToken !== 'oauth_connected') {
      busy.current = true;
      void connect(savedId, savedToken).finally(() => { setTimeout(() => { busy.current = false; }, 15000); });
    }
  }, [activeMode, connect]);
}

const Content: React.FC = () => {
  const [nonce, setNonce] = useState(0);
  const [announcement, setAnnouncement] = useState('');
  const needsCapability = useApp((s) => s.ui.needsCapability);
  const scanner = useApp((s) => ({ activeMode: s.scanner.active_mode, feed: s.scanner.feed_status, ws: Boolean(s.scanner.ws_connected) }), (a, b) => a.activeMode === b.activeMode && a.feed === b.feed && a.ws === b.ws);
  const stream = useApp((s) => s.stream);
  const [capInput, setCapInput] = useState(getDashboardCapability());
  const [capError, setCapError] = useState<string | null>(null);
  const [capOk, setCapOk] = useState(false);
  useDhanAutoReconnect();
  useAnnouncements(setAnnouncement);
  const layouts = useLayouts();
  const desktop = useDesktopMedia();
  const commandsRef = useRef<DockCommands>(NOOP_COMMANDS);
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const confirm = useConfirm();
  const openKillSwitch = useKillSwitchDialog();
  const { toggleTheme } = useTheme();
  const paletteState = useApp((st) => ({ scanner: st.scanner, watch: st.watch }), (a, b) => a.scanner === b.scanner && a.watch === b.watch);
  const commands = useMemo(
    () => (paletteOpen ? registerCommands({ panels: PANELS.map((p) => ({ id: p.id, title: p.title, category: p.category })), workspaces: layouts.workspaces, customs: layouts.customs, state: paletteState, desktop }) : []),
    [paletteOpen, layouts.workspaces, layouts.customs, paletteState, desktop],
  );
  const ctx: CommandContext = useMemo(() => ({
    get dock() { return commandsRef.current; },
    switchWorkspace: layouts.switchTo, layoutAction: requestLayoutAction, confirm, openKillSwitch, showHelp: () => setHelpOpen(true), toggleTheme, setDensity,
    refreshData: () => { pollNow(); void refreshPortfolio(); }, select,
  }), [layouts.switchTo, confirm, openKillSwitch, toggleTheme]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const id = matchShortcut(e);
      if (!id || id === 'killSwitch') return;
      const entry = DOCK_COMMAND_ENTRIES.find((c) => c.shortcut === id);
      if (entry) { e.preventDefault(); entry.run(commandsRef.current); return; }
      if (id === 'help') { e.preventDefault(); setHelpOpen(true); }
      if (id === 'palette') { e.preventDefault(); setPaletteOpen((o) => !o); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    let stopStream: (() => void) | null = null;
    let stopPollers: (() => void) | null = null;
    let cancelled = false;
    void (async () => {
      const ok = await ensureSession();
      if (cancelled || !ok) return;
      stopStream = startStream();
      stopPollers = startPollers();
    })();
    return () => { cancelled = true; stopStream?.(); stopPollers?.(); };
  }, [nonce]);

  useEffect(() => startAlertsEngine({
    onCritical: (a) => {
      setAnnouncement(`Critical alert: ${a.message}`);
      try {
        if (appStore.getState().ui.notifications && typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification('BB critical alert', { body: a.message });
      } catch { /* notifications unavailable */ }
    },
  }), []);

  useEffect(() => { try { document.documentElement.dataset.density = appStore.getState().ui.density; } catch { /* no document */ } }, []);

  const onSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setCapError(null);
    if (await submitCapability(capInput)) {
      setCapOk(true);
      setNonce((n) => n + 1);
      setTimeout(() => { setCapOk(false); closeCapabilityDialog(); }, 700);
    } else {
      setCapError('That key was not accepted. Check it and try again.');
    }
  }, [capInput]);

  return (
    <div className="h-screen flex flex-col overflow-hidden" data-testid="dock-app">
      <ModeBanner />
      <Chrome workspaceSlot={desktop ? <WorkspaceSwitcher layouts={layouts} /> : undefined} alertsSlot={<AlertsBadge onOpen={() => commandsRef.current.openPanel('alerts')} />}
        paletteSlot={<button type="button" className="desk-btn" aria-label="Open command palette" title="Command palette (Ctrl+K)" onClick={() => setPaletteOpen(true)}><Search className="h-3.5 w-3.5" aria-hidden /></button>} />
      <LiveAnnouncer message={announcement} />
      <div className="px-2 pt-1 empty:hidden"><ConnectionBanner activeMode={scanner.activeMode} feedStatus={scanner.feed} wsConnected={scanner.ws} stream={stream} /></div>
      <main className="flex-1 min-h-0" aria-label="Workspace">
        {!desktop ? <MobileShell /> : layouts.ready
          ? <DockHost key={`${layouts.current}:${layouts.revision}`} layout={layouts.spec} onLayoutChange={layouts.onChange} commandsRef={commandsRef}
              onLoadError={layouts.reportLoadError} onReset={layouts.reset} />
          : <div className="p-4 text-sm desk-muted" role="status">Workspace loading</div>}
      </main>
      <StatusBar />
      <ToastHost />
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
      {paletteOpen && <CommandPalette commands={commands} ctx={ctx} onClose={() => setPaletteOpen(false)} />}
      {needsCapability && (
        <CapabilityDialog value={capInput} onChange={setCapInput} error={capError} success={capOk} onSubmit={onSubmit} onClose={closeCapabilityDialog} />
      )}
    </div>
  );
};

export default function DockApp() {
  return (
    <ThemeProvider>
      <DhanAuthProvider>
        <ConfirmProvider>
          <Content />
        </ConfirmProvider>
      </DhanAuthProvider>
    </ThemeProvider>
  );
}
