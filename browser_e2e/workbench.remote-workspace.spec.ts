import { test, expect } from '@playwright/test';

const authPayload = {
  bearer: '',
  userId: 'browser-e2e-user',
  userRole: 'operator',
  tenantId: '',
  managementKey: '',
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript((payload) => {
    localStorage.setItem('acp-workbench-auth', JSON.stringify(payload));
  }, authPayload);
});

test('workbench supports remote workspace and saved view flow', async ({ page }) => {
  await page.goto('/workbench');
  await expect(page.locator('h1')).toContainText('ACP Live Workbench');
  await expect(page.locator('#remote-workspace-executors')).toContainText('Planning-only executor');

  await page.locator('#project-filter').fill('proj-browser');
  await page.locator('#remote-workspace-id').fill('ws-browser');
  await page.locator('#remote-workspace-repo-url').fill('https://github.com/example/repo');
  await page.locator('#remote-workspace-repo-branch').fill('main');
  await page.locator('#remote-workspace-command').fill('pytest -q');

  await page.locator('#save-remote-workspace').click();
  await expect(page.locator('#remote-workspace-snapshots')).toContainText('ws-browser');
  await expect(page.locator('#remote-workspace-snapshots')).toContainText('proj-browser');

  await page.locator('#request-remote-workspace-run').click();
  await expect(page.locator('#remote-workspace-executions')).toContainText('run_checks');
  await expect(page.locator('#remote-workspace-executions')).toContainText('planned');

  await page.locator('#workbench-view-name').fill('browser-view');
  await page.locator('#save-workbench-view').click();
  await expect(page.locator('#workbench-saved-views')).toContainText('browser-view');
  await expect(page.locator('#workbench-saved-views')).toContainText('ws-browser');

  await page.getByRole('button', { name: 'Apply' }).first().click();
  await expect(page.locator('#remote-workspace-id')).toHaveValue('ws-browser');
  await expect(page.locator('#project-filter')).toHaveValue('proj-browser');

  await page.getByRole('button', { name: 'Delete' }).first().click();
  await expect(page.locator('#workbench-saved-views')).not.toContainText('browser-view');
});
