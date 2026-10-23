import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

test.describe('Dock shell chrome (flagged)', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
  });

  test('?shell=dock renders the chrome, kill switch and status bar with live data', async ({ page }) => {
    await page.goto('/?shell=dock');
    await expect(page.getByTestId('dock-app')).toBeVisible();
    await expect(page.getByTestId('kill-switch')).toBeVisible();
    await expect(page.getByTestId('status-bar')).toBeVisible();
    await expect(page.getByTestId('status-stream')).toContainText('Fresh', { timeout: 15000 });
  });

  test('kill switch opens a confirmation and Escape cancels it', async ({ page }) => {
    await page.goto('/?shell=dock');
    await page.getByTestId('kill-switch').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    // Engage needs the typed phrase; release (when an earlier spec left the switch on) is a plain confirm.
    await expect(dialog.getByRole('button', { name: /Engage kill switch|Re-enable entries/ })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });

  test('the shell flag is remembered and ?shell=legacy rolls back', async ({ page }) => {
    await page.goto('/?shell=dock');
    await expect(page.getByTestId('dock-app')).toBeVisible();
    await page.goto('/');
    await expect(page.getByTestId('dock-app')).toBeVisible();
    await page.goto('/?shell=legacy');
    await expect(page.getByTestId('dock-app')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Toggle theme' }).first()).toBeVisible();
  });
});
