import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';
import { installFakeStream, position, snapshot } from '../fixtures/fakeStream';

const gotoDock = async (page: import('@playwright/test').Page, workspace = 'Trading') => {
  await page.goto(`/?shell=dock&workspace=${workspace}`);
  await expect(page.getByTestId('dock-app')).toBeVisible({ timeout: 15000 });
};

test.describe('Dock flows', () => {
  test('without a dashboard key the capability dialog opens (401 path)', async ({ page }) => {
    await page.goto('/?shell=dock');
    await expect(page.locator('#capability-input')).toBeVisible({ timeout: 15000 });
  });

  test('kill switch: typed phrase is required, failed positions are named', async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await installFakeStream(page, snapshot([position('pos-1'), position('pos-2')]), true);
    let posted = 0;
    await page.route('**/api/paper/kill-switch', async (route) => { posted += 1; await route.fulfill({ json: { ok: true, failed: ['NIFTY 22000 CE'] } }); });
    await gotoDock(page);
    await page.getByTestId('kill-switch').click();
    const dialog = page.getByRole('dialog');
    const engage = dialog.getByRole('button', { name: 'Engage kill switch' });
    await expect(dialog).toContainText('2 open positions will be closed');
    await expect(engage).toBeDisabled();
    expect(posted).toBe(0);
    await dialog.getByRole('textbox').fill('KILL');
    await expect(engage).toBeEnabled();
    await engage.click();
    await expect.poll(() => posted).toBe(1);
    await page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name: 'Risk', exact: true }).click();
    await page.getByRole('tab', { name: 'Alerts', exact: true }).click();
    await expect(page.getByText(/could not be closed: NIFTY 22000 CE/).first()).toBeVisible({ timeout: 10000 });
  });

  test('closing a position asks first, sends nothing until confirmed, then the audit panel lists it', async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await resetServerLayouts(page, getDashboardKey());
    await installFakeStream(page, snapshot([position('pos-1')]), true);
    let closed = 0;
    await page.route('**/api/paper/close/pos-1', async (route) => { closed += 1; await route.fulfill({ json: { ok: true } }); });
    await page.route('**/api/audit/actions*', (route) => route.fulfill({ json: closed ? [{ id: 1, ts: new Date().toISOString(), client: 'dashboard', action: 'paper.close', target: 'pos-1', outcome: 'ok', method: 'POST', route: '/api/paper/close/pos-1', status: 200 }] : [] }));
    await gotoDock(page, 'Risk');
    await page.getByRole('button', { name: /Close NIFTY 22000 CE from table/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('Close NIFTY 22000 CE?');
    expect(closed).toBe(0);
    await page.keyboard.press('Escape');
    expect(closed).toBe(0);
    await page.getByRole('button', { name: /Close NIFTY 22000 CE from table/ }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Close position' }).click();
    await expect.poll(() => closed).toBe(1);
    await page.getByRole('tab', { name: 'Audit trail' }).click();
    await expect(page.getByRole('table', { name: 'Audit rows' }).getByText('paper.close')).toBeVisible({ timeout: 15000 });
  });

  test('a silent stream turns the status bar stale and shows the connection banner', async ({ page }) => {
    test.setTimeout(60_000);
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await installFakeStream(page, snapshot(), false);
    await gotoDock(page);
    await expect(page.getByTestId('status-stream')).toContainText('Fresh', { timeout: 15000 });
    await expect(page.getByTestId('status-stream')).toContainText(/Stale/, { timeout: 30000 });
    await expect(page.getByTestId('status-stream')).toHaveAttribute('data-state', /stale/);
  });

  test('a layout saved in one browser context appears in a second one on the same backend', async ({ browser }) => {
    const key = getDashboardKey();
    const a = await browser.newContext();
    const pa = await a.newPage();
    await new DashboardPage(pa).injectAuthKey(key);
    await resetServerLayouts(pa, key);
    await gotoDock(pa);
    await pa.getByRole('button', { name: /Layout/ }).click();
    await pa.getByRole('menuitem', { name: /Save layout as/ }).click();
    await pa.getByLabel('Layout name').fill('Shared view');
    await pa.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
    await expect(pa.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name: 'Shared view' })).toBeVisible();
    // The save is debounced; wait until the server really has it before the second context opens.
    await expect.poll(async () => {
      const res = await pa.request.get('/api/ui/layouts', { headers: { 'X-Dashboard-Capability': key } });
      return res.ok() ? (await res.json() as { name: string }[]).map((l) => l.name) : [];
    }, { timeout: 15000 }).toContain('custom:Shared view');
    const b = await browser.newContext();
    const pb = await b.newPage();
    await new DashboardPage(pb).injectAuthKey(key);
    await gotoDock(pb);
    await expect(pb.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name: 'Shared view' })).toBeVisible({ timeout: 15000 });
    await resetServerLayouts(pb, key);
    await a.close(); await b.close();
  });

  test('the legacy shell flag rolls back and bb_shell is honoured', async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.goto('/?shell=legacy');
    await expect(page.getByTestId('dock-app')).toHaveCount(0);
    expect(await page.evaluate(() => localStorage.getItem('bb_shell'))).toBe('legacy');
    await page.goto('/');
    await expect(page.getByTestId('dock-app')).toHaveCount(0);
  });
});
