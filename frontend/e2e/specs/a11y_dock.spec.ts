import { test, expect, type Page } from '@playwright/test';
import axe from 'axe-core';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';

const WORKSPACES = ['Trading', 'Risk', 'Performance', 'Execution', 'Review', 'Operations', 'Earnings'];

const serious = (page: Page) => page.evaluate(async () => {
  const res = await (window as unknown as { axe: { run: (n: Element, o: unknown) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document.body);
  return res.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(', ')}`);
});

for (const theme of ['light', 'dark'] as const) {
  test.describe(`Accessibility, ${theme} theme, including colour contrast`, () => {
    test.beforeEach(async ({ page }) => {
      await new DashboardPage(page).injectAuthKey(getDashboardKey());
      await resetServerLayouts(page, getDashboardKey());
      await page.addInitScript((t) => {
        try { localStorage.setItem('app_theme', t); if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); localStorage.removeItem('bb_workspace'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ }
      }, theme);
      await page.goto('/?shell=dock');
      await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
      await page.addScriptTag({ content: axe.source });
    });

    for (const name of WORKSPACES) {
      test(`${name} has no serious or critical axe violations`, async ({ page }) => {
        await page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name, exact: true }).click();
        await page.waitForTimeout(1500);
        expect(await page.evaluate(() => document.documentElement.classList.contains('dark'))).toBe(theme === 'dark');
        expect(await serious(page)).toEqual([]);
      });
    }
  });
}
