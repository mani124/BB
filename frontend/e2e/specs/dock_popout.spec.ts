import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

const openMenu = async (page: import('@playwright/test').Page, title: string, item: string) => {
  await page.getByRole('button', { name: `${title} panel menu` }).click();
  await page.getByRole('menuitem', { name: item }).click();
};

test.describe('Floating and pop-out', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
  });

  test('a blocked pop-up shows a message and the panel stays docked', async ({ page }) => {
    await page.addInitScript(() => { window.open = () => null; });
    await page.goto('/?shell=dock&workspace=Trading');
    await page.getByRole('tab', { name: 'Session' }).click();
    await openMenu(page, 'Session', 'Pop out');
    await expect(page.getByText('Pop-out was blocked by the browser. Allow pop-ups for this site.').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('tab', { name: 'Session' })).toBeVisible();
  });

  test('a real pop-out keeps updating, closing it returns the panel, reload floats it with a banner', async ({ page }) => {
    await page.goto('/?shell=dock&workspace=Trading');
    await page.getByRole('tab', { name: 'Positions table' }).click();
    const popupPromise = page.waitForEvent('popup');
    await openMenu(page, 'Positions blotter', 'Pop out');
    const popup = await popupPromise;
    await expect(popup.getByTestId('panel-asof').first()).toBeVisible({ timeout: 10000 });
    const first = await popup.getByTestId('panel-asof').first().textContent();
    await expect.poll(async () => popup.getByTestId('panel-asof').first().textContent(), { timeout: 15000 }).not.toBe(first);

    // The layout is saved with the pop-out; a reload restores it as a floating panel with a banner.
    await page.waitForTimeout(1800);
    const saved = await page.evaluate(() => localStorage.getItem('bb_layouts') ?? '');
    expect(saved).toContain('"popouts":["positions-table"]');
    await page.reload();
    await expect(page.getByTestId('popout-banner')).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: 'Re-open pop-outs' })).toBeVisible();
    await expect(page.locator('.dv-resize-container')).toHaveCount(1);
  });

  test('closing the pop-out window returns the panel to the main dock', async ({ page }) => {
    await page.goto('/?shell=dock&workspace=Trading');
    await page.getByRole('tab', { name: 'Session' }).click();
    const popupPromise = page.waitForEvent('popup');
    await openMenu(page, 'Session', 'Pop out');
    const popup = await popupPromise;
    await expect(page.getByRole('tab', { name: 'Session' })).toHaveCount(0);
    await popup.close();
    await expect(page.getByRole('tab', { name: 'Session' })).toBeVisible({ timeout: 10000 });
  });
});
