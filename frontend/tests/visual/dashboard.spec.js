// dashboard.spec.js — พิสูจน์ว่าหน้าเว็บหลังแยกไฟล์ "เหมือนเดิม"
//   1) screenshot ทุกแท็บ (desktop + mobile) ต้องตรง baseline ที่ถ่ายจาก index.legacy.html ทุก pixel
//   2) network: ชุด request /api/* (method + path + query + body) ต้องตรงกับของเดิม
//   3) console: ห้ามมี error ใหม่
// baseline: npm run test:visual:baseline  |  เทียบ: npm run build && npm run test:visual
import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const LEGACY = process.env.UI_TARGET === 'legacy';
const FIXED_NOW = new Date('2026-10-02T10:30:00Z'); // นาฬิกานิ่ง → เวลาบนจอเหมือนกันทุกครั้ง
const TABS = ['overview', 'signals', 'performance', 'log']; // Phase C-2: sidebar ใหม่ 4 แท็บ
const SUBTABS = { signals: ['ml', 'setup'], performance: ['journal', 'cfd'], log: ['siglog', 'ticktouch'] };
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
const NET_FILE = resolve(HERE, '__snapshots__/network.legacy.json');

async function openDashboard(page, viewport) {
  await page.setViewportSize(viewport);
  await page.clock.setFixedTime(FIXED_NOW);
  // ตัดของภายนอก (Google Fonts / CDN fallback) → ภาพนิ่ง ไม่ขึ้นกับเน็ต (ตัดเหมือนกันทั้งก่อน-หลัง)
  // ตอบว่างแทน abort → ไม่เกิด console error ปลอมจากตัวเทสต์เอง (ทั้ง legacy/dist ได้ fallback font เดียวกัน)
  await page.route(/^https?:\/\/(fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net)\//, (r) =>
    r.fulfill({ status: 200, contentType: 'text/css', body: '' }),
  );
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  await page.request.get('/__requests'); // ล้าง log
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500); // ให้ refreshAll รอบแรก + วาดกราฟเสร็จ
  // C-7: กัน chart canvas เบี่ยง 1-2px ระหว่าง session (ฟอนต์มาถึงช้า/เร็วไม่เท่ากัน →
  //   legendbar สูงต่างกันตอนกราฟวัดขนาดครั้งแรก) — รอฟอนต์พร้อมแล้วบังคับ re-layout กราฟ 1 ครั้ง
  //   เหมือนที่แอปทำเองตอนสลับแท็บ → ภาพ overview นิ่งทุก session (เทสต์ล้วน ไม่แตะโค้ดแอป)
  await page.evaluate(async () => {
    await document.fonts.ready;
    window.dispatchEvent(new Event('resize'));
  });
  await page.waitForTimeout(400);
  return errors;
}

// C-7 mobile: sidebar เป็น drawer (ซ่อนนอกจอ) — ต้องกด hamburger เปิดก่อนคลิกแท็บทุกครั้ง
//   เลือกแท็บแล้ว drawer ปิดเอง → ทุกภาพถ่ายตอน drawer ปิด (desktop คง flow เดิม)
//   legacy (UI_TARGET=legacy) ไม่มี #navToggle → ข้ามได้ เพื่อให้ regen baseline จาก legacy ยังรันได้
async function openTab(page, tab, isMobile) {
  if (isMobile) {
    const toggle = page.locator('#navToggle');
    if ((await toggle.count()) && (await toggle.isVisible())) {
      await toggle.click();
      await page.waitForTimeout(350); // รอ transition ของ drawer (.2s)
    }
  }
  await page.locator(`.nav-item[data-tab="${tab}"]`).click();
}

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  test(`ทุกแท็บเหมือนเดิม — ${vpName}`, async ({ page }) => {
    const errors = await openDashboard(page, viewport);
    const isMobile = vpName === 'mobile';
    for (const tab of TABS) {
      await openTab(page, tab, isMobile);
      await page.waitForTimeout(800);
      await expect(page).toHaveScreenshot(`${vpName}-${tab}.png`);
      // sub-tab ของแท็บรวม (Phase C-2) — ภาพเฉพาะ sub-tab ที่ 2 ขึ้นไป (อันแรกอยู่ในภาพหลักแล้ว)
      for (const sub of (SUBTABS[tab] || []).slice(1)) {
        await page.locator(`#tab-${tab} .subtab[data-subtab="${sub}"]`).click();
        await page.waitForTimeout(800);
        await expect(page).toHaveScreenshot(`${vpName}-${tab}-${sub}.png`);
      }
    }
    // พับ/ขยาย section (แทน inline onclick) ต้องทำงานเหมือนเดิม — อยู่ sub-tab journal ของ tab-performance
    await openTab(page, 'performance', isMobile);
    await page.locator('#tab-performance .subtab[data-subtab="journal"]').click();
    await page.locator('#jSecPeriod .j-section-head').click();
    await expect(page.locator('#jSecPeriod')).toHaveClass(/open/);
    await page.locator('#jSecPeriod .j-section-head').click();
    await expect(page.locator('#jSecPeriod')).not.toHaveClass(/open/);
    expect(errors, 'console error').toEqual([]);
  });
}

test('network ที่หน้าเว็บเรียก ตรงกับของเดิม', async ({ page }) => {
  await openDashboard(page, VIEWPORTS.desktop);
  await page.locator('.nav-item[data-tab="performance"]').click();
  await page.locator('#tab-performance .subtab[data-subtab="cfd"]').click();
  await page.locator('#btnRunCfdBacktest, [onclick="runCFDBacktest()"]').first().click(); // ปุ่ม Run Backtest
  await page.waitForTimeout(800);
  const reqs = await (await page.request.get('/__requests')).json();
  const set = [...new Set(reqs.map((r) => `${r.method} ${r.key} ${r.body ?? ''}`.trim()))].sort();
  if (LEGACY) {
    writeFileSync(NET_FILE, JSON.stringify(set, null, 1));
  } else {
    expect(existsSync(NET_FILE), 'ยังไม่มี baseline network — รัน test:visual:baseline ก่อน').toBe(true);
    expect(set).toEqual(JSON.parse(readFileSync(NET_FILE, 'utf8')));
  }
});
