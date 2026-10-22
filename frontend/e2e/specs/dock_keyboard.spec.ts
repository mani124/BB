import { test, expect, type Page } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

/** Identity of a tab's group: the titles in its tab strip. */
const groupOf = (page: Page, tabName: string) => page.evaluate((name) => {
  const tab = [...document.querySelectorAll('[role="tab"]')].find((t) => t.textContent?.trim() === name);
  return tab ? [...(tab.parentElement?.querySelectorAll('[role="tab"]') ?? [])].map((t) => t.textContent?.trim()).join('|') : '';
}, tabName);

test.describe('Dock keyboard parity', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
    await page.goto('/?shell=dock&workspace=Trading');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
  });

  test('? opens the shortcut help and Escape closes it', async ({ page }) => {
    await page.keyboard.press('Shift+?');
    await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeHidden();
  });

  test('moves a panel to the next group, maximises, restores and closes using only the keyboard', async ({ page }) => {
    await page.getByRole('tab', { name: 'Chart' }).focus();
    await page.getByRole('tab', { name: 'Chart' }).press('Enter');
    const before = await groupOf(page, 'Chart');
    await page.keyboard.press('Alt+Shift+}');
    await expect.poll(() => groupOf(page, 'Chart')).not.toBe(before);

    await page.keyboard.press('Alt+m');
    await expect.poll(async () => (await page.locator('.dv-groupview.dv-active-group').boundingBox())!.width).toBeGreaterThan(1100);
    await page.keyboard.press('Alt+m');
    await expect.poll(async () => (await page.locator('.dv-groupview.dv-active-group').boundingBox())!.width).toBeLessThan(900);

    await page.keyboard.press('Alt+w');
    await expect(page.getByRole('tab', { name: 'Chart' })).toHaveCount(0);
  });

  test('floats and docks a panel from its keyboard-operable menu', async ({ page }) => {
    await page.getByRole('tab', { name: 'Session' }).click();
    const menuButton = page.getByRole('region', { name: 'Session' }).getByRole('button', { name: 'Session panel menu' }).first();
    await menuButton.focus();
    await page.keyboard.press('Enter');
    await page.getByRole('menuitem', { name: 'Float' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.dv-resize-container')).toHaveCount(1);
    await page.getByRole('region', { name: 'Session' }).getByRole('button', { name: 'Session panel menu' }).first().press('Enter');
    await page.getByRole('menuitem', { name: 'Dock' }).press('Enter');
    await expect(page.locator('.dv-resize-container')).toHaveCount(0);
  });

  test('Alt+] moves focus to another group', async ({ page }) => {
    await page.getByRole('tab', { name: 'Chart' }).click();
    const active = () => page.evaluate(() => document.querySelector('.dv-active-group')?.querySelector('[role="tab"][aria-selected="true"]')?.textContent?.trim());
    const first = await active();
    await page.keyboard.press('Alt+]');
    await expect.poll(active).not.toBe(first);
  });
});
