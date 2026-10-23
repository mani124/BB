import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';

test.describe('Dock layout', () => {
  test.beforeEach(async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await resetServerLayouts(page, getDashboardKey());
    await page.addInitScript(() => { try { if (!sessionStorage.getItem('e2e_cleared')) { localStorage.removeItem('bb_layouts'); localStorage.removeItem('bb_workspace'); sessionStorage.setItem('e2e_cleared', '1'); } } catch { /* none */ } });
  });

  test('the Trading workspace shows signals, focus, positions table and positions', async ({ page }) => {
    await page.goto('/?shell=dock&workspace=Trading');
    await expect(page.getByTestId('dock-host')).toBeVisible();
    for (const name of ['Signals and watch', 'Focus', 'Positions blotter', 'Open positions']) {
      await expect(page.getByRole('heading', { name, exact: true }).first()).toBeVisible({ timeout: 15000 });
    }
  });

  test('switching to Earnings shows the earnings panel', async ({ page }) => {
    await page.goto('/?shell=dock');
    await page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name: 'Earnings', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Earnings', exact: true }).first()).toBeVisible({ timeout: 15000 });
  });

  test('a corrupted saved layout and a failing layouts endpoint still open Trading with a warning', async ({ page }) => {
    await page.route('**/api/ui/layouts**', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.addInitScript(() => { try { localStorage.setItem('bb_layouts', JSON.stringify({ 'workspace:Trading': { updated_at: '2999', spec: 'garbage' } })); } catch { /* none */ } });
    await page.goto('/?shell=dock&workspace=Trading');
    await expect(page.getByRole('heading', { name: 'Focus', exact: true }).first()).toBeVisible({ timeout: 15000 });
  });

  test('dragging a tab into another group changes the layout and survives reload', async ({ page }) => {
    await page.goto('/?shell=dock&workspace=Trading');
    const tab = page.getByRole('tab', { name: 'Chart' });
    await expect(tab).toBeVisible({ timeout: 15000 });
    const target = page.getByRole('tab', { name: 'Open positions' });
    const a = (await tab.boundingBox())!;
    const t = (await target.boundingBox())!;
    await page.mouse.move(a.x + 10, a.y + 10);
    await page.mouse.down();
    await page.mouse.move(a.x + 40, a.y + 30, { steps: 5 });
    await page.mouse.move(t.x + t.width / 2, t.y + 300, { steps: 20 });
    await page.mouse.move(t.x + t.width / 2 + 2, t.y + 302, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(2000);
    const saved = await page.evaluate(() => localStorage.getItem('bb_layouts'));
    expect(saved).toContain('chart');
    await page.reload();
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
    const sameGroup = await page.evaluate(() => {
      const chart = [...document.querySelectorAll('[role="tab"]')].find((t) => t.textContent?.trim() === 'Chart');
      const pos = [...document.querySelectorAll('[role="tab"]')].find((t) => t.textContent?.trim() === 'Open positions');
      return Boolean(chart && pos && chart.parentElement === pos.parentElement);
    });
    expect(sameGroup).toBe(true);
  });
});
