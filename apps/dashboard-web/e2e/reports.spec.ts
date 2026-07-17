import { test, expect } from '@playwright/test';
import { buildContextPath, expectPostLoginRoute, loginAndWaitForSession } from './support/session';

const tenantId = process.env.SMOKE_TENANT_ID || process.env.VITE_DEFAULT_TENANT_ID || '';

test.describe('Reports module', () => {
  test('create report job flow', async ({ page }) => {
    if (!tenantId) {
      test.skip(true, 'SMOKE_TENANT_ID is required for reports e2e.');
    }

    await loginAndWaitForSession(page);
    await expectPostLoginRoute(page);

    await page.goto(buildContextPath('/reports'), { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();

    await page.getByRole('button', { name: /create export/i }).click();
    await expect(page).toHaveURL(/\/reports\/jobs\/new|\/reports\/new/);
    await expect(page.getByRole('heading', { level: 1, name: 'Create Report' })).toBeVisible();

    await page.getByLabel(/start date/i).fill(new Date().toISOString().slice(0, 10));
    await page.getByLabel(/end date/i).fill(new Date().toISOString().slice(0, 10));
    await page.getByRole('button', { name: /create export/i }).click();

    await expect(page).toHaveURL(/\/reports\/jobs(\/[^/]+)?$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /Report Job|Report Jobs/ })
    ).toBeVisible({ timeout: 10000 });
  });
});
