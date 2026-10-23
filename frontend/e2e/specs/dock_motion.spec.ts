import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';
import { getDashboardKey } from '../fixtures/auth.fixture';

const animationOf = (page: import('@playwright/test').Page) => page.evaluate(() => {
  const el = document.createElement('div');
  el.style.animation = 'desk-shimmer 1s linear infinite';
  document.body.appendChild(el);
  const name = getComputedStyle(el).animationName;
  el.remove();
  return name;
});

test.describe('Reduced motion', () => {
  test('animations run normally and stop under prefers-reduced-motion', async ({ page }) => {
    await new DashboardPage(page).injectAuthKey(getDashboardKey());
    await page.goto('/?shell=dock');
    await expect(page.getByTestId('dock-app')).toBeVisible({ timeout: 15000 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    expect(await animationOf(page)).toBe('desk-shimmer');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(await animationOf(page)).toBe('none');
  });
});
