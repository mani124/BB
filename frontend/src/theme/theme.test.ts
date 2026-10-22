import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { contrast } from '../lib/contrast';

const read = (f: string) => readFileSync(resolve(__dirname, f), 'utf8');
const css = `${read('../index.css')}\n${read('./tokens.css')}`;

function block(selector: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = new RegExp(`(^|\\n)${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'g');
  let m: RegExpExecArray | null;
  while ((m = re.exec(css))) {
    for (const d of m[2].matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim();
  }
  return out;
}

const light = { ...block(':root') };
const dark = { ...light, ...block(':root.dark') };

describe('design tokens', () => {
  const required = ['density-row', 'density-pad', 'focus-ring', 'mode-paper', 'mode-dry', 'mode-live', 'stale'];
  it.each(required)('defines --%s for light and dark', (name) => {
    expect(light[name]).toBeTruthy();
    expect(block(':root.dark')[name] ?? light[name]).toBeTruthy();
  });

  it('comfortable density widens rows', () => {
    expect(block(":root[data-density='comfortable']")['density-row']).toBe('32px');
    expect(light['density-row']).toBe('24px');
  });

  it('dockview theme maps the documented variables', () => {
    const t = read('./dockview-theme.css');
    for (const v of ['--dv-group-view-background-color', '--dv-tabs-and-actions-container-background-color', '--dv-activegroup-visiblepanel-tab-color', '--dv-separator-border']) {
      expect(t).toContain(v);
    }
  });

  const pairs: [string, string, string][] = [
    ['fg', 'panel', 'text'], ['muted', 'panel', 'muted'], ['up', 'panel', 'up'], ['down', 'panel', 'down'],
    ['warn', 'panel', 'warn'], ['accent', 'panel', 'accent'], ['stale', 'panel', 'stale'],
    ['mode-live-fg', 'mode-live', 'live banner'], ['mode-paper-fg', 'mode-paper', 'paper pill'], ['mode-dry', 'mode-dry-fill', 'dry-run banner'],
  ];
  for (const [theme, vars] of [['light', light], ['dark', dark]] as const) {
    it.each(pairs)(`${theme}: %s on %s (%s) has contrast >= 4.5`, (fg, bg) => {
      const f = vars[fg] ?? vars[fg.replace('mode-live-fg', 'mode-live-fg')];
      expect(f, fg).toBeTruthy();
      expect(vars[bg], bg).toBeTruthy();
      expect(contrast(f, vars[bg])).toBeGreaterThanOrEqual(4.5);
    });
  }
});
