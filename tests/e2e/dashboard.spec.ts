import { test, expect } from '@playwright/test';

test('dashboard renders microbes and enzyme panels', async ({ page }) => {
  await page.goto('/?autorun=1&days=60');
  // App shell load (fallback to clicking Run if autorun didn’t trigger)
  await page.waitForLoadState('domcontentloaded');
  const runButton = page.getByRole('button', { name: 'Run Simulation' });
  if (await runButton.isVisible({ timeout: 2000 })) {
    await runButton.click();
  }
  // Wait for key chart headers to appear
  await expect(page.locator('text=Soil nitrogen by layer')).toBeVisible({ timeout: 180000 });
  await expect(page.locator('text=Microbial biomass (totals)')).toBeVisible({ timeout: 180000 });

  // Soil tab (default) has nitrogen and microbes sections
  await expect(page.locator('text=Soil nitrogen by layer')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('text=Microbial biomass (totals)')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('text=Enzyme group totals (C cost)')).toBeVisible({ timeout: 30000 });

  // Switch to Weather tab and back to ensure charts are interactive
  await page.getByRole('tab', { name: 'Weather' }).click();
  await expect(page.locator('text=Weather overview')).toBeVisible({ timeout: 90000 });
  await page.getByRole('tab', { name: 'Soil' }).click();

  // Visual regression snapshot
  await expect(page).toHaveScreenshot('dashboard-microbes.png', { fullPage: true });
});


