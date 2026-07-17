import { test, expect } from '@playwright/test';
import { buildContextPath, loginAndWaitForSession } from './support/session';

const tenantId = process.env.SMOKE_TENANT_ID || '';
const farmId = process.env.SMOKE_FARM_ID || '';
const barnId = process.env.SMOKE_BARN_ID || '';

const routeScreens = [
  { path: '/farms', heading: 'Farms' },
  { path: '/barns', heading: 'Barns' },
  { path: '/devices', heading: 'Device Registry' },
  { path: '/sensors', heading: 'Sensor Catalog' },
  { path: '/feeding/kpi', heading: 'Feeding KPI Dashboard' },
  { path: '/barns/records', heading: 'Health & Records' },
];

test.describe('dashboard-web smoke', () => {
  test('key routes render without crashing', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await loginAndWaitForSession(page);

    if (!tenantId) {
      test.skip(true, 'SMOKE_TENANT_ID is required for route smoke checks.');
    }

    for (const route of routeScreens) {
      if (route.path === '/barns/records' && (!farmId || !barnId)) {
        continue;
      }
      await page.goto(buildContextPath(route.path), { waitUntil: 'domcontentloaded' });
      await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible();

      const hasTable = await page.locator('table').first().isVisible().catch(() => false);
      const hasGrid = await page.locator('[role="grid"]').first().isVisible().catch(() => false);
      const hasEmpty = await page.getByText(/no .*found|no data available|no .*available/i).first().isVisible().catch(() => false);
      const hasApiError = await page.getByText(/endpoint not found|api error/i).first().isVisible().catch(() => false);
      const hasContextGate = await page.getByText(/select a farm|select a barn|select a tenant/i).first().isVisible().catch(() => false);
      const hasLoading = await page.getByText(/loading |loading$|loading barns|loading devices|loading sensors/i).first().isVisible().catch(() => false);

      expect(hasTable || hasGrid || hasEmpty || hasApiError || hasContextGate || hasLoading).toBeTruthy();

      const safeName = route.path.replace(/\//g, '_').replace(/_{2,}/g, '_').replace(/^_/, '');
      await page.screenshot({
        path: `apps/dashboard-web/evidence/smoke/screens/${safeName}.png`,
        fullPage: true,
      });
    }

    expect(errors).toEqual([]);
  });
});
