import { expect, type Page } from '@playwright/test';

const tenantId = process.env.SMOKE_TENANT_ID || process.env.VITE_DEFAULT_TENANT_ID || '';
const farmId = process.env.SMOKE_FARM_ID || process.env.VITE_DEFAULT_FARM_ID || '';
const barnId = process.env.SMOKE_BARN_ID || '';
const batchId = process.env.SMOKE_BATCH_ID || '';

const DEFAULT_LOGIN_TIMEOUT_MS = 45_000;

const buildUrl = (path: string, params: Record<string, string>) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value) {
      search.set(key, value);
    }
  }

  const query = search.toString();
  return query ? `${normalizedPath}?${query}` : normalizedPath;
};

export const buildContextPath = (
  path: string,
  overrides: Partial<Record<'tenant_id' | 'farm_id' | 'barn_id' | 'batch_id', string>> = {},
) =>
  buildUrl(path, {
    tenant_id: overrides.tenant_id ?? tenantId,
    farm_id: overrides.farm_id ?? farmId,
    barn_id: overrides.barn_id ?? barnId,
    batch_id: overrides.batch_id ?? batchId,
  });

export const loginAndWaitForSession = async (page: Page) => {
  await page.goto(buildContextPath('/login'), { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Email address').fill('admin@farmiq.com');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForFunction(() => {
    const onPostLoginRoute =
      /\/select-tenant|\/select-context|\/select-farm|\/overview/.test(window.location.pathname);
    const hasToken =
      !!window.localStorage.getItem('farmiq_auth_token') ||
      !!window.sessionStorage.getItem('farmiq_auth_token');
    const hasProfile =
      !!window.localStorage.getItem('farmiq_user_profile') ||
      !!window.sessionStorage.getItem('farmiq_user_profile');
    return onPostLoginRoute || (hasToken && hasProfile);
  }, undefined, { timeout: DEFAULT_LOGIN_TIMEOUT_MS });
};

export const expectPostLoginRoute = async (page: Page) => {
  await expect(page).toHaveURL(
    /\/select-tenant|\/select-context|\/select-farm|\/overview/,
    { timeout: DEFAULT_LOGIN_TIMEOUT_MS },
  );
};
