import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the Login screen. Locators follow the nxtQA locator
 * policy: getByRole > getByLabel > getByPlaceholder > getByText > data-testid.
 * Never raw CSS/XPath unless explicitly flagged as an exception in the
 * Automation Generation Contract.
 */
export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorBanner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.getByLabel('Username');
    this.passwordInput = page.getByLabel('Password');
    this.submitButton = page.getByRole('button', { name: 'Sign in' });
    this.errorBanner = page.getByRole('alert');
  }

  async goto(): Promise<void> {
    await this.page.goto('/login');
  }

  async login(username: string, password: string): Promise<void> {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async expectLoginError(message: string): Promise<void> {
    await expect(this.errorBanner).toBeVisible();
    await expect(this.errorBanner).toContainText(message);
  }
}
