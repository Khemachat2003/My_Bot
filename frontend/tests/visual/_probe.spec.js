// _probe.spec.js — วัดตำแหน่ง canvas ของกราฟหลักระหว่าง session (หาสาเหตุ A/B ของ overview screenshot)
import { test } from '@playwright/test';
import { writeFileSync } from 'node:fs';

const FIXED_NOW = new Date('2026-10-02T10:30:00Z');

test('probe canvas rect', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.setFixedTime(FIXED_NOW);
  await page.route(/^https?:\/\/(fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net)\//, (r) =>
    r.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  const info = await page.evaluate(() => {
    const rects = {};
    for (const sel of ['#candleChart', '#lwWrap', '#chartLegendBar', '.chart-toolbar', '#volChart']) {
      const el = document.querySelector(sel);
      if (el) rects[sel] = el.getBoundingClientRect().toJSON();
    }
    return {
      rects,
      fonts: document.fonts.status,
      loaded: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family + ' ' + f.weight).slice(0, 8),
    };
  });
  await page.screenshot({ path: 'probe-out/probe.png' });
  writeFileSync(`probe-out/probe-${Date.now()}.json`, JSON.stringify(info, null, 1));
});
