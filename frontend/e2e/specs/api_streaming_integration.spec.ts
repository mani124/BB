import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('API & Live Streaming E2E Integration', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
    const validKey = getDashboardKey();
    await dashboard.injectAuthKey(validKey);
  });

  test('should successfully fetch signals API snapshot on load', async ({ page }) => {
    const snapshotPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/signals') && resp.status() === 200,
      { timeout: 15000 }
    );

    await dashboard.goto();
    const response = await snapshotPromise;
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('universe_count');
    expect(data).toHaveProperty('active_mode');
  });

  test('should establish SSE streaming connection without error alerts', async ({ page }) => {
    await dashboard.goto();

    await page.waitForTimeout(2000);
    const errorAlert = page.locator('.desk-alert:has-text("Disconnected")');
    await expect(errorAlert).not.toBeVisible();
  });

  test('should handle Scan Now button click without crashing', async ({ page }) => {
    await dashboard.goto();
    await expect(dashboard.scanNowButton).toBeVisible({ timeout: 10000 });

    const scanPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/signals/scan-now') && resp.status() === 200,
      { timeout: 15000 }
    );

    await dashboard.triggerScan();
    const response = await scanPromise;
    expect(response.ok()).toBeTruthy();
  });
});
