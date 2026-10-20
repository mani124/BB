import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('Dashboard Navigation & Layout E2E', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
    const validKey = getDashboardKey();
    await dashboard.injectAuthKey(validKey);
    await dashboard.goto();
  });

  test('should display proper page title and header controls', async ({ page }) => {
    await expect(page).toHaveTitle(/BB Options/i);
    await expect(dashboard.header).toBeVisible();
    await expect(dashboard.themeToggle).toBeVisible();
  });

  test('should toggle dark and light themes smoothly', async ({ page }) => {
    const html = page.locator('html');
    
    // Check initial class
    const initialIsDark = await html.evaluate((el) => el.classList.contains('dark'));

    // Click toggle
    await dashboard.toggleTheme();

    // Verify state flipped
    await expect.poll(async () => {
      return await html.evaluate((el) => el.classList.contains('dark'));
    }).toBe(!initialIsDark);

    // Toggle back
    await dashboard.toggleTheme();
    await expect.poll(async () => {
      return await html.evaluate((el) => el.classList.contains('dark'));
    }).toBe(initialIsDark);
  });

  test('should render core sections (signals and blotter/tables)', async ({ page }) => {
    await expect(dashboard.signalsSection).toBeVisible({ timeout: 10000 });
    await expect(dashboard.positionsSection).toBeVisible();
  });
});
