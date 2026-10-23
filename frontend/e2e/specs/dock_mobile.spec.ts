import { test, expect } from '@playwright/test';
import axe from 'axe-core';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.use({ viewport: { width: 390, height: 844 } });

test.describe('Mobile shell', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.goto('/?shell=dock');
    await expect(page.getByTestId('mobile-shell')).toBeVisible({ timeout: 15000 });
  });

  test('has no horizontal scroll and the kill switch stays visible', async ({ page }) => {
    await expect(page.getByTestId('kill-switch')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const name of ['Detail', 'Positions', 'Tables', 'More']) {
      await page.getByRole('navigation', { name: 'Screen sections' }).getByRole('button', { name }).click();
      const o = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(o, name).toBeLessThanOrEqual(0);
    }
  });

  test('More opens any panel full screen', async ({ page }) => {
    await page.getByRole('navigation', { name: 'Screen sections' }).getByRole('button', { name: 'More' }).click();
    await page.getByLabel('All panels').getByRole('button', { name: 'Controls' }).click();
    await expect(page.getByRole('button', { name: 'Back' })).toBeVisible();
    await expect(page.getByTestId('mobile-shell').getByRole('button', { name: 'Scan now' })).toBeVisible({ timeout: 15000 });
  });

  test('passes axe on the signals pane', async ({ page }) => {
    await page.waitForTimeout(1000);
    await page.addScriptTag({ content: axe.source });
    const ids = await page.evaluate(async () => {
      const res = await (window as unknown as { axe: { run: (n: Element, o: unknown) => Promise<{ violations: { id: string; impact: string }[] }> } }).axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
      return res.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id);
    });
    expect(ids).toEqual([]);
  });
});
