import { beforeEach, describe, expect, it, vi } from 'vitest';
import { actions } from '../../data/actions';
import { initialScanner } from '../../data/appStore';
import { NOOP_COMMANDS } from './dockCommands';
import { rankCommands, registerCommands, scoreCommand, symbolTargets, type Command, type CommandContext, type CommandInputs } from './commandRegistry';
import { pos, signal } from '../../test/panelHarness';

const inputs = (over: Partial<CommandInputs> = {}): CommandInputs => ({
  panels: [{ id: 'risk', title: 'Risk overview', category: 'risk' }, { id: 'trades', title: 'Trades', category: 'review' }],
  workspaces: ['Trading', 'Risk'], customs: ['Mine'],
  state: { scanner: { ...initialScanner(), signals: [signal()], paper_portfolio: { active_positions: [pos()] } as never }, watch: null },
  desktop: true, ...over,
});

const ctx = (over: Partial<CommandContext> = {}): CommandContext => ({
  dock: NOOP_COMMANDS, switchWorkspace: vi.fn(), layoutAction: vi.fn(), confirm: vi.fn(async () => false), openKillSwitch: vi.fn(async () => {}),
  showHelp: vi.fn(), toggleTheme: vi.fn(), setDensity: vi.fn(), refreshData: vi.fn(), select: vi.fn(), ...over,
});

describe('scoreCommand', () => {
  const c = (title: string, keywords: string[] = []) => ({ title, keywords });
  it('ranks exact above prefix above word start above substring above keyword above fuzzy', () => {
    const exact = scoreCommand('trades', c('Trades'));
    const prefix = scoreCommand('tra', c('Trades'));
    const word = scoreCommand('over', c('Risk overview'));
    const sub = scoreCommand('isk', c('Risk overview'));
    const kw = scoreCommand('emergency', c('Kill switch', ['emergency']));
    const fuzzy = scoreCommand('rko', c('Risk overview'));
    expect([exact, prefix, word, sub, kw, fuzzy].every((n) => n > 0)).toBe(true);
    expect(exact).toBeGreaterThan(prefix);
    expect(prefix).toBeGreaterThan(word);
    expect(word).toBeGreaterThan(sub);
    expect(sub).toBeGreaterThan(kw);
    expect(kw).toBeGreaterThan(fuzzy);
  });
  it('returns 0 for no match and a neutral score for an empty query', () => {
    expect(scoreCommand('zzz', c('Trades'))).toBe(0);
    expect(scoreCommand('', c('Trades'))).toBeGreaterThan(0);
    expect(scoreCommand('  ', c('Trades'))).toBeGreaterThan(0);
  });
  it('fuzzy needs the letters in order', () => { expect(scoreCommand('sdr', c('Trades'))).toBe(0); expect(scoreCommand('trs', c('Trades'))).toBeGreaterThan(0); });
});

describe('rankCommands', () => {
  it('puts the exact panel first and keeps the original order for ties', () => {
    const list = registerCommands(inputs());
    expect(rankCommands('trades', list)[0].id).toBe('open:trades');
    expect(rankCommands('', list).map((x) => x.id)).toEqual(list.map((x) => x.id).slice(0, 50));
  });
  it('limits the number of results', () => { expect(rankCommands('', registerCommands(inputs()), 5)).toHaveLength(5); });
});

describe('registerCommands', () => {
  it('has a command to open every panel, every workspace and every dock command', () => {
    const ids = registerCommands(inputs()).map((c) => c.id);
    for (const id of ['open:risk', 'open:trades', 'workspace:Trading', 'workspace:Mine', 'layout:save', 'layout:reset', 'dock:float', 'dock:maximise', 'dock:closePanel', 'scan', 'refresh', 'theme', 'help', 'danger:kill', 'danger:close-all', 'danger:reset', 'go:NIFTY']) expect(ids).toContain(id);
  });
  it('leaves out workspace and dock commands on the mobile shell', () => {
    const ids = registerCommands(inputs({ desktop: false })).map((c) => c.id);
    expect(ids.some((i) => i.startsWith('workspace:') || i.startsWith('dock:'))).toBe(false);
    expect(ids).toContain('open:risk');
  });
  it('marks exactly the three dangerous commands', () => {
    expect(registerCommands(inputs()).filter((c) => c.danger).map((c) => c.id).sort()).toEqual(['danger:close-all', 'danger:kill', 'danger:reset']);
  });
  it('go-to prefers an open position over a signal and lists each symbol once', () => {
    const t = symbolTargets(inputs().state);
    expect(t).toEqual([{ symbol: 'NIFTY', kind: 'position', id: 'P1', detail: expect.stringContaining('open') }]);
  });
  it('go-to selects the target', () => {
    const select = vi.fn();
    void registerCommands(inputs()).find((c) => c.id === 'go:NIFTY')!.run(ctx({ select }));
    expect(select).toHaveBeenCalledWith({ kind: 'position', id: 'P1' });
  });
});

describe('dangerous commands never act without a confirmation', () => {
  let spies: ReturnType<typeof vi.spyOn>[];
  beforeEach(() => {
    spies = [vi.spyOn(actions, 'killSwitch'), vi.spyOn(actions, 'closePosition'), vi.spyOn(actions, 'resetPortfolio')] as never;
    spies.forEach((s) => s.mockResolvedValue({ ok: true, message: '' } as never));
  });
  const danger = (id: string): Command => registerCommands(inputs()).find((c) => c.id === id)!;

  it('close all and reset only call actions after the dialog is accepted', async () => {
    const refuse = ctx({ confirm: vi.fn(async () => false) });
    await danger('danger:close-all').run(refuse);
    await danger('danger:reset').run(refuse);
    expect(refuse.confirm).toHaveBeenCalledTimes(2);
    spies.forEach((s) => expect(s).not.toHaveBeenCalled());

    const accept = ctx({ confirm: vi.fn(async () => true) });
    await danger('danger:close-all').run(accept);
    expect(actions.closePosition).toHaveBeenCalledWith('P1');
    await danger('danger:reset').run(accept);
    expect(actions.resetPortfolio).toHaveBeenCalledTimes(1);
  });
  it('close all asks for a typed phrase and lists the positions', async () => {
    const confirm = vi.fn(async () => false);
    await danger('danger:close-all').run(ctx({ confirm }));
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ phrase: 'CLOSE ALL', danger: true, body: expect.stringContaining('NIFTY 24500 CE') }));
  });
  it('the kill switch command only opens its own dialog', async () => {
    const c = ctx();
    await danger('danger:kill').run(c);
    expect(c.openKillSwitch).toHaveBeenCalledTimes(1);
    expect(actions.killSwitch).not.toHaveBeenCalled();
  });
  it('close all with no open positions does nothing', async () => {
    const empty = registerCommands(inputs({ state: { scanner: initialScanner(), watch: null } })).find((c) => c.id === 'danger:close-all')!;
    const c = ctx();
    await empty.run(c);
    expect(c.confirm).not.toHaveBeenCalled();
  });
});
