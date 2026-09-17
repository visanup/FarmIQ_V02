import { defineConfig, devices } from '@playwright/test';

const workerCount = Number(process.env.PLAYWRIGHT_WORKERS || (process.env.CI ? 1 : 1));

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  timeout: 60_000,
  workers: Number.isFinite(workerCount) && workerCount > 0 ? workerCount : 1,
  reporter: 'html',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5135',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5135',
    reuseExistingServer: !process.env.CI,
  },
});

