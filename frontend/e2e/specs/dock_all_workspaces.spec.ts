import { test, expect, type Page } from '@playwright/test';
import axe from 'axe-core';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';

/** Tab titles each built-in workspace must show (a preset panel that failed to load would be missing). */
const EXPECTED: Record<string, string[]> = {
  Trading: ['Signals', 'Earnings watch', 'Focus', 'Chart', 'Positions table', 'Trades', 'Session', 'Open positions', 'Risk overview'],
  Risk: ['Risk overview', 'Exposure', 'Controls', 'Positions table', 'Audit trail', 'Alerts'],
  Performance: ['Performance summary', 'Equity and drawdown', 'Attribution', 'Distributions', 'Setup statistics', 'Costs'],
  Execution: ['Execution quality', 'Live routing', 'Orders and fills', 'Costs', 'Trades'],
  Review: ['Session', 'Journal', 'Trades', 'Telemetry'],
  Operations: ['System health', 'Alerts', 'Readiness', 'Recorder', 'Telemetry', 'Universe', 'Settings'],
  Earnings: ['Earnings'],
};

const serious = (page: Page) => page.evaluate(async () => {
  const res = await (window as unknown as { axe: { run: (n: Element, o: unknown) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } });
  return res.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(', ')}`);
});

test.describe('Every workspace opens with all of its panels', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await resetServerLayouts(page, getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); localStorage.removeItem('bb_workspace'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
    await page.goto('/?shell=dock');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
    await page.addScriptTag({ content: axe.source });
  });

  for (const [name, titles] of Object.entries(EXPECTED)) {
    test(`${name}: every panel title is a tab, nothing failed to show, axe finds nothing serious`, async ({ page }) => {
      await page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name, exact: true }).click();
      for (const title of titles) await expect(page.getByRole('tab', { name: title, exact: true }).first()).toBeVisible({ timeout: 15000 });
      await page.waitForTimeout(1200);
      await expect(page.getByText('This panel could not be shown.')).toHaveCount(0);
      await expect(page.getByText(/^Unknown panel/)).toHaveCount(0);
      expect(await serious(page)).toEqual([]);
    });
  }
});
