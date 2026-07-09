import { Page, Locator, expect } from '@playwright/test';

export class OrderPage {
  readonly page: Page;
  readonly productSearchInput: Locator;
  readonly addToCartButton: Locator;
  readonly checkoutButton: Locator;
  readonly orderConfirmationBanner: Locator;
  readonly orderIdText: Locator;

  constructor(page: Page) {
    this.page = page;
    this.productSearchInput = page.getByPlaceholder('Search products');
    this.addToCartButton = page.getByRole('button', { name: 'Add to cart' });
    this.checkoutButton = page.getByRole('button', { name: 'Checkout' });
    this.orderConfirmationBanner = page.getByRole('status');
    this.orderIdText = page.getByTestId('order-id');
  }

  async goto(): Promise<void> {
    await this.page.goto('/orders/new');
  }

  async createOrder(productName: string): Promise<void> {
    await this.productSearchInput.fill(productName);
    await this.page.getByText(productName, { exact: false }).first().click();
    await this.addToCartButton.click();
    await this.checkoutButton.click();
  }

  async expectOrderConfirmed(): Promise<string> {
    await expect(this.orderConfirmationBanner).toBeVisible();
    return (await this.orderIdText.textContent()) ?? '';
  }
}
