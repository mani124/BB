import { Page, Locator, expect } from '@playwright/test';

export class DashboardPage {
  readonly page: Page;
  readonly header: Locator;
  readonly themeToggle: Locator;
  readonly accessKeyButton: Locator;
  readonly connectDhanButton: Locator;
  readonly riskControls: Locator;
  readonly capabilityInput: Locator;
  readonly authorizeSessionButton: Locator;
  readonly scanNowButton: Locator;
  readonly signalsSection: Locator;
  readonly positionsSection: Locator;

  constructor(page: Page) {
    this.page = page;
    this.header = page.locator('header');
    this.themeToggle = page.getByRole('button', { name: 'Toggle theme' }).first();
    this.accessKeyButton = page.getByRole('button', { name: 'Dashboard key' }).first();
    this.connectDhanButton = page.getByRole('button', { name: 'Connect Dhan' }).first();
    this.riskControls = page.locator('[data-testid="risk-controls"]').first();
    this.capabilityInput = page.locator('#capability-input');
    this.authorizeSessionButton = page.getByRole('button', { name: 'Authorize session' });
    this.scanNowButton = page.getByRole('button', { name: 'Scan now' }).first();
    this.signalsSection = page.locator('section[aria-labelledby="signals-title"]');
    this.positionsSection = page.locator('section[aria-label="Tables"]');
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('domcontentloaded');
  }

  async injectAuthKey(key: string) {
    await this.page.addInitScript((token) => {
      window.localStorage.setItem('dashboard_capability', token);
    }, key);
  }

  async enterKeyInDialog(key: string) {
    await expect(this.capabilityInput).toBeVisible({ timeout: 5000 });
    await this.capabilityInput.fill(key);
    await this.authorizeSessionButton.click();
    await expect(this.page.locator('text=Key accepted. Session started.')).toBeVisible({ timeout: 5000 });
    await expect(this.capabilityInput).not.toBeVisible({ timeout: 5000 });
  }

  async toggleTheme() {
    await this.themeToggle.click();
  }

  async triggerScan() {
    await this.scanNowButton.click();
  }
}
