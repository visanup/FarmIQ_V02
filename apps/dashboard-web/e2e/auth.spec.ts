import { test, expect } from '@playwright/test';
import { buildContextPath, expectPostLoginRoute, loginAndWaitForSession } from './support/session';

const barnId = process.env.SMOKE_BARN_ID || 'some-barn-id';

test.describe('Authentication Flow', () => {
  test('happy path login reaches tenant or overview flow', async ({ page }) => {
    await loginAndWaitForSession(page);
    await expectPostLoginRoute(page);

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

    await expect(page).toHaveURL(/\/select-tenant|\/select-farm|\/overview|\/select-context/);
  });

  test('security cross-tenant navigation should error', async ({ page }) => {
    await loginAndWaitForSession(page);
    await expectPostLoginRoute(page);
    await page.goto(buildContextPath(`/barns/${barnId}`, { tenant_id: 'different-tenant-id' }));

    await expect(
      page.locator('text=/something went wrong|error|forbidden|access denied|barn not found/i')
    ).toBeVisible({ timeout: 10000 });
  });
});
