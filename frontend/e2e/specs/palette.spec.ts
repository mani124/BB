import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';
import axe from 'axe-core';

test.describe('Command palette', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await resetServerLayouts(page, getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
    await page.goto('/?shell=dock&workspace=Trading');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
  });

  test('Ctrl+K opens, Escape closes and restores focus', async ({ page }) => {
    await page.getByRole('tab', { name: 'Chart' }).focus();
    await page.keyboard.press('Control+k');
    const dlg = page.getByRole('dialog', { name: /command palette/i });
    await expect(dlg).toBeVisible();
    await expect(dlg.getByRole('combobox')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dlg).toBeHidden();
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeFocused();
  });

  test('re-opens a closed panel from the palette', async ({ page }) => {
    await page.getByRole('tab', { name: 'Chart' }).click();
    await page.keyboard.press('Alt+w');
    await expect(page.getByRole('tab', { name: 'Chart' })).toHaveCount(0);
    await page.keyboard.press('Control+k');
    await page.locator('#palette-input').fill('chart');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible();
  });

  test('a danger command only opens a confirmation', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await page.locator('#palette-input').fill('reset portfolio');
    await page.keyboard.press('Enter');
    const dlg = page.getByRole('dialog').last();
    await expect(dlg).toBeVisible();
    await expect(dlg.getByRole('button', { name: /cancel/i })).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('has no serious axe violations while open', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await expect(page.getByRole('dialog', { name: /command palette/i })).toBeVisible();
    await page.addScriptTag({ content: axe.source });
    const res = await page.evaluate(async () => {
      const r = await (window as unknown as { axe: { run: (n: Element, o: unknown) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe.run(document.querySelector('[role="dialog"]')!, { rules: { 'color-contrast': { enabled: false } } });
      return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id);
    });
    expect(res).toEqual([]);
  });
});
