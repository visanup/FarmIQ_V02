import { test } from '@playwright/test';
import { buildContextPath, expectPostLoginRoute, loginAndWaitForSession } from './support/session';

test.describe('Evidence Collection', () => {
  test('capture screenshots of key pages', async ({ page }) => {
    await page.goto(buildContextPath('/login'), { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'evidence/ui/01-login.png' });

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

    await page.waitForURL(/\/select-tenant|\/overview|\/select-farm|\/select-context/, { timeout: 20000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'evidence/ui/02-overview.png' });

    const paths = [
      ['/farms', '03-farms-list.png'],
      ['/barns', '04-barns-list.png'],
      ['/weighvision/sessions', '05-weighvision-sessions.png'],
      ['/feeding/daily', '06-feeding-daily.png'],
      ['/sensors/matrix', '07-sensors-matrix.png'],
      ['/admin/users', '08-admin-users.png'],
      ['/settings', '09-settings.png'],
    ] as const;

    for (const [path, filename] of paths) {
      await page.goto(buildContextPath(path), { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `evidence/ui/${filename}` });
    }
  });
});
