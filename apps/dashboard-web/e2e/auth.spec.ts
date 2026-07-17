import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('happy path login reaches tenant or overview flow', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@farmiq.com');
    await page.fill('input[type="password"]', 'password123');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/select-tenant|\/select-context|\/overview/);

    if (page.url().includes('/select-tenant')) {
      const tenantCards = page.getByRole('button', { name: /enter workspace/i });
      const overrideInput = page.getByLabel('Developer tenant ID');

      if (await tenantCards.first().isVisible().catch(() => false)) {
        await tenantCards.first().click();
      } else if (await overrideInput.isVisible().catch(() => false)) {
        await overrideInput.fill(process.env.SMOKE_TENANT_ID || 'tenant-batch5-e2e');
        await page.getByRole('button', { name: /use this tenantid/i }).click();
      }
    }

    await expect(page).toHaveURL(/\/select-farm|\/overview|\/select-context/);
  });

  test('security cross-tenant navigation should error', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@farmiq.com');
    await page.fill('input[type="password"]', 'password123');
    await page.getByRole('button', { name: /sign in/i }).click();

    await page.waitForURL(/\/select-tenant|\/select-context|\/overview/);
    await page.goto('/barns/some-barn-id?tenant_id=different-tenant-id');

    await expect(
      page.locator('text=/error|forbidden|access denied/i')
    ).toBeVisible({ timeout: 5000 });
  });
});
