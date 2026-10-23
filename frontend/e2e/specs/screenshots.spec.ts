import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';
import { resetServerLayouts } from '../fixtures/layouts';
import { installFakeStream, position, snapshot } from '../fixtures/fakeStream';

/** Evidence screenshots (Phase 7.4). Run with SCREENSHOTS=1; skipped in the normal suite. */
const OUT = resolve(process.cwd(), '../docs/screenshots/institutional');
const WORKSPACES = ['Trading', 'Risk', 'Performance', 'Execution', 'Review', 'Operations', 'Earnings'];
const sig = (i: number) => ({
  id: `shot-${i}`, symbol: ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS'][i % 4], timeframe: ['3m', '5m', '15m'][i % 3], setup_type: 'SETUP_1', option_type: i % 2 ? 'CE' : 'PE',
  timestamp: new Date(Date.now() - i * 60_000).toISOString(), is_confirmed: true, entry_price: 22000 + i, stop_loss: 21950 + i, target_1: 22050 + i, target_2: 22100 + i,
  strike_recommendation: { strike: 22000, option_type: i % 2 ? 'CE' : 'PE', symbol: 'NIFTY 22000' },
  indicators_snapshot: { close: 22000, bb_upper: 22060, bb_middle: 22000, bb_lower: 21940, bandwidth: 0.1, percent_b: 0.5, vwap: 22000, rsi: 55, ema_9: 22000, adx: 25 }, rationale: 'Squeeze breakout with VWAP agreement',
});

test.skip(!process.env.SCREENSHOTS, 'set SCREENSHOTS=1 to regenerate docs/screenshots/institutional');

for (const theme of ['light', 'dark'] as const) {
  test(`desktop workspaces, ${theme}`, async ({ page }) => {
    test.setTimeout(180_000);
    mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await resetServerLayouts(page, getDashboardKey());
    await installFakeStream(page, snapshot([position('pos-1'), { ...position('pos-2'), strike_symbol: 'BANKNIFTY 48000 PE', option_type: 'PE', pnl_rupees: -420, est_net_pnl: -470 }], { signals: Array.from({ length: 8 }, (_, i) => sig(i)) }), true);
    await page.addInitScript((t) => { try { localStorage.setItem('app_theme', t); localStorage.removeItem('bb_layouts'); } catch { /* none */ } }, theme);
    await page.goto('/?shell=dock&workspace=Trading');
    await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
    for (const name of WORKSPACES) {
      await page.getByRole('navigation', { name: 'Workspaces' }).getByRole('button', { name, exact: true }).click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${OUT}/${name.toLowerCase()}-${theme}.png` });
    }
  });
}

test('mobile shell', async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await new DashboardPage(page).injectAuthKey(getDashboardKey());
  await installFakeStream(page, snapshot([position('pos-1')], { signals: Array.from({ length: 5 }, (_, i) => sig(i)) }), true);
  await page.goto('/?shell=dock');
  await expect(page.getByTestId('dock-app')).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/mobile-signals-light.png` });
});

test('command palette', async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await new DashboardPage(page).injectAuthKey(getDashboardKey());
  await installFakeStream(page, snapshot([position('pos-1')], { signals: Array.from({ length: 8 }, (_, i) => sig(i)) }), true);
  await page.goto('/?shell=dock&workspace=Trading');
  await expect(page.getByRole('tab', { name: 'Chart' })).toBeVisible({ timeout: 15000 });
  await page.keyboard.press('Control+k');
  await page.locator('#palette-input').fill('risk');
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/command-palette-light.png` });
});
