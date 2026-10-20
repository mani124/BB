import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('Risk Controls & Kill Switch E2E', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboard = new DashboardPage(page);
    const validKey = getDashboardKey();
    await dashboard.injectAuthKey(validKey);
  });

  test('should render risk controls chip and kill switch button in the header', async ({ page }) => {
    await dashboard.goto();
    await expect(dashboard.riskControls).toBeVisible({ timeout: 10000 });
  });

  test('should trigger kill switch toggle with confirmation dialog', async ({ page }) => {
    await dashboard.goto();
    await expect(dashboard.riskControls).toBeVisible({ timeout: 10000 });

    const killSwitchBtn = dashboard.riskControls.locator('button');
    const initialText = await killSwitchBtn.innerText();

    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/paper/kill-switch') && resp.status() === 200,
      { timeout: 10000 }
    );

    await killSwitchBtn.click();
    await responsePromise;

    // After response, button text should change or reflect toggled state
    await expect(killSwitchBtn).not.toHaveText(initialText, { timeout: 5000 });
  });
});
