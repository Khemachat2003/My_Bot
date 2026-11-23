import { test } from '@playwright/test';

const FIXED_NOW = new Date('2026-10-02T10:30:00Z');

test('probe compact signal cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.clock.setFixedTime(FIXED_NOW);
  await page.route(/^https?:\/\/(fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net)\//, (r) =>
    r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await page.locator('.bn-item[data-tab="signals"]').click();
  await page.waitForTimeout(800);
  await page.locator('#mlFullTable tbody tr').first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const h1 = await page.evaluate(() => document.querySelector('#mlFullTable tbody tr')?.getBoundingClientRect().height);
  await page.locator('#mlFullTable tbody tr').first().screenshot({ path: 'probe-out/compact-ml.png' });
  await page.locator('#tab-signals .subtab[data-subtab="setup"]').click();
  await page.waitForTimeout(800);
  await page.locator('#setupTable tbody tr').first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const h2 = await page.evaluate(() => document.querySelector('#setupTable tbody tr')?.getBoundingClientRect().height);
  await page.locator('#setupTable tbody tr').first().screenshot({ path: 'probe-out/compact-setup.png' });
  console.log('card heights ml/setup:', h1, h2);
});