import { defineConfig } from '@playwright/test';

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  use: {
    baseURL: process.env.WORKBENCH_BASE_URL || 'http://127.0.0.1:8000',
    headless: true,
    ...(executablePath ? { launchOptions: { executablePath } } : {}),
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium', ...(executablePath ? { launchOptions: { executablePath } } : {}) },
    },
  ],
});
