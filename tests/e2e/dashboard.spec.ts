import { test, expect } from '@playwright/test';

test.describe('Dashboard E2E Data Flow', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/login');
        await page.fill('input[type="email"]', 'admin@farmiq.com');
        await page.fill('input[type="password"]', 'password123');
        await page.getByRole('button', { name: /sign in/i }).click();
        await expect(page).toHaveURL(/\/select-tenant|\/select-context|\/overview/);
    });

    test('Login flow reaches a valid post-auth page', async ({ page }) => {
        if (page.url().includes('/select-tenant')) {
            const tenantCards = page.getByRole('button', { name: /enter workspace/i });
            const overrideInput = page.getByLabel('Developer tenant ID');

            if (await tenantCards.first().isVisible().catch(() => false)) {
                await tenantCards.first().click();
                await expect(page).toHaveURL(/\/select-farm|\/overview/);
                return;
            }

            if (await overrideInput.isVisible().catch(() => false)) {
                await overrideInput.fill(process.env.SMOKE_TENANT_ID || 'tenant-batch5-e2e');
                await page.getByRole('button', { name: /use this tenantid/i }).click();
                await expect(page).toHaveURL(/\/select-farm|\/overview/);
                return;
            }
        }

        await expect(page).toHaveURL(/\/overview|\/select-context|\/select-tenant/);
    });
});
