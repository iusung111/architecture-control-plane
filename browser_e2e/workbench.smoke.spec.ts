import { test, expect } from '@playwright/test';

test('workbench smoke', async ({ page }) => {
  await page.goto('/workbench');
  await expect(page.locator('h1')).toContainText('ACP Live Workbench');
  await expect(page.locator('#save-remote-workspace')).toBeVisible();
  await expect(page.locator('#refresh-audit')).toBeVisible();
});
