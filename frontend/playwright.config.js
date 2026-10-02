// playwright.config.js — visual/network regression ของ dashboard
//   UI_TARGET=legacy → ถ่าย baseline จาก _archive/index.legacy.html (ไฟล์ก้อนเดียวเดิม)
//   (ไม่ตั้ง)        → เทียบ frontend/dist/index.html (ต้อง npm run build ก่อน)
// ข้อมูล API มาจาก tests/visual/fixtures/*.json (สร้างด้วย capture_fixtures.py) — ไม่ยิง backend จริง
import { defineConfig } from '@playwright/test';

const PORT = 4321;

export default defineConfig({
  testDir: 'tests/visual',
  snapshotPathTemplate: '{testDir}/__snapshots__/{arg}{ext}',
  timeout: 120_000,
  workers: 1,
  reporter: [['list']],
  expect: { toHaveScreenshot: { maxDiffPixels: 0, animations: 'disabled', caret: 'hide' } },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: process.env.PW_CHANNEL || 'chrome', // ใช้ Chrome ที่ติดตั้งในเครื่อง (ไม่ต้องดาวน์โหลด browser)
    headless: true,
    locale: 'th-TH',
    timezoneId: 'UTC',
  },
  webServer: {
    command: `node tests/visual/server.mjs ${PORT}`,
    url: `http://127.0.0.1:${PORT}/__health`,
    reuseExistingServer: false,
    env: { UI_TARGET: process.env.UI_TARGET || 'dist' },
  },
});
