import { test, expect } from '@playwright/test';

test.describe('Login Page', () => {
  test('should display login page', async ({ page }) => {
    await page.goto('/');
    
    // Check for main elements
    await expect(page.getByText('Asgard Basis')).toBeVisible();
    await expect(page.getByText('Automated yield farming strategy')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Get Started' })).toBeVisible();
  });

  test('should display feature list', async ({ page }) => {
    await page.goto('/');
    
    await expect(page.getByText('Market-neutral yield generation')).toBeVisible();
    await expect(page.getByText('Automated position management')).toBeVisible();
    await expect(page.getByText('Built-in risk controls')).toBeVisible();
  });

  test('should show security note', async ({ page }) => {
    await page.goto('/');
    
    await expect(page.getByText('Secured by Privy')).toBeVisible();
  });
});
