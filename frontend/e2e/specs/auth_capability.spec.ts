import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('Dashboard Capability Authentication E2E', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
  });

  test('should prompt for dashboard key on first visit without credentials', async ({ page }) => {
    // Clear any local storage
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });

    await dashboard.goto();

    // Verify capability dialog is shown
    await expect(dashboard.capabilityInput).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Dashboard key' })).toBeVisible();
  });

  test('should reject invalid dashboard access key with an error message', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });

    await dashboard.goto();
    await expect(dashboard.capabilityInput).toBeVisible({ timeout: 10000 });

    // Enter wrong key
    await dashboard.capabilityInput.fill('invalid-dummy-key-12345');
    await dashboard.authorizeSessionButton.click();

    // Verify error alert
    await expect(page.locator('text=That key was not accepted. Check it and try again.')).toBeVisible({ timeout: 5000 });
  });

  test('should authorize successfully with valid key and unlock dashboard', async ({ page }) => {
    const validKey = getDashboardKey();

    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });

    await dashboard.goto();
    await dashboard.enterKeyInDialog(validKey);

    // Dialog should disappear and main app should be accessible
    await expect(dashboard.capabilityInput).not.toBeVisible();
    await expect(dashboard.header).toBeVisible();
  });
});
