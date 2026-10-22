import { test, expect } from '@playwright/test';
import axe from 'axe-core';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('Workspace management', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); localStorage.removeItem('bb_workspace'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
    await page.goto('/?shell=dock');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
  });

  const menu = async (page: import('@playwright/test').Page, item: string | RegExp) => {
    await page.getByRole('button', { name: /^Layout/ }).click();
    await page.getByRole('menuitem', { name: item }).click();
  };

  test('saves a custom layout and it is still there after reload', async ({ page }) => {
    await menu(page, /Save layout as/);
    await page.getByLabel('Layout name').fill('Scalping');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    const nav = page.getByRole('navigation', { name: 'Workspaces' });
    await expect(nav.getByRole('button', { name: 'Scalping' })).toBeVisible();
    await page.waitForTimeout(1500);
    await page.reload();
    await expect(page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name: 'Scalping' })).toBeVisible({ timeout: 15000 });
  });

  test('reset workspace restores the preset after a change', async ({ page }) => {
    await page.getByRole('tab', { name: 'Chart' }).focus();
    await page.getByRole('tab', { name: 'Chart' }).press('Enter');
    await page.keyboard.press('Alt+w');
    await expect(page.getByRole('tab', { name: 'Chart' })).toHaveCount(0);
    await menu(page, 'Reset workspace');
    await page.getByRole('dialog').getByRole('button', { name: 'Reset workspace' }).click();
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 10000 });
  });

  test('importing invalid JSON shows an error', async ({ page }) => {
    await menu(page, /Import layout/);
    await page.getByLabel('Layout JSON').fill('{not valid');
    await page.getByRole('button', { name: 'Import', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Not a valid layout' })).toBeVisible();
  });

  test('the desktop dock has no serious or critical axe violations', async ({ page }) => {
    await page.waitForTimeout(1500);
    await page.addScriptTag({ content: axe.source });
    const found = await page.evaluate(async () => {
      const res = await (window as unknown as { axe: { run: (n: Element, o: unknown) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } });
      return res.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(', ')}`);
    });
    expect(found).toEqual([]);
  });
});
