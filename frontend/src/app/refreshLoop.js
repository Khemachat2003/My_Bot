// รอบ refresh: refreshAll() เรียกทุกแผงพร้อมกัน
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1133–1134, 3446–3459 แบบ move-only
// Phase C-2: + refreshRecentSignalsLog (Log/Alert) + stale badge (markPollSuccess)
// Phase C-4: + ensureMarkers prefetch ให้ตารางสัญญาณ (แคชเดียวกับกราฟ)
// C-8 perf: refresh เฉพาะแผงของแท็บที่เปิดอยู่ (+ รอบแรกของหน้าโหลดทุกแผงครั้งเดียว) และหยุดเมื่อแท็บซ่อน —
//   ลดโหลด VPS จากการยิงครบทุกแท็บทุก 5 วิ (สาเหตุ load spike + sqlite database is locked)

import { refreshCFDPaper } from '../features/cfd/index.js';
import { refreshPrice } from '../features/chart/index.js';
import { refreshGauges } from '../features/gauges/index.js';
import { refreshHero } from '../features/hero/index.js';
import { refreshJournalMoney, refreshJournalTab } from '../features/journal/index.js';
import { refreshMlRecentFeed, refreshMlTab } from '../features/ml-signals/index.js';
import { checkNewSignals, refreshRecentSignalsLog } from '../features/notifications/index.js';
import { refreshOverview } from '../features/overview/index.js';
import { refreshMtfTab, refreshSetupAll, refreshSetupMini, refreshSetupTab } from '../features/setup-signals/index.js';
import { refreshHeaderSignals, updateClock } from '../features/status-bar/index.js';
import { refreshWatchlist } from '../features/watchlist/index.js';
import { ensureMarkers } from '../shared/lib/markersCache.js';
import { markPollSuccess } from './staleBadge.js';

const REFRESH_MS = 5000;

// แผงของแต่ละแท็บ (sidebar data-tab) — เรียกเฉพาะแท็บที่กำลังดู
const TAB_GROUPS = {
  overview: [refreshOverview, refreshPrice, refreshGauges, refreshHero, refreshMlRecentFeed,
    refreshSetupMini, refreshWatchlist, ensureMarkers],
  signals: [refreshMlTab, refreshSetupTab, refreshSetupAll, refreshMtfTab],
  performance: [refreshJournalTab, refreshJournalMoney, refreshCFDPaper],
  log: [refreshRecentSignalsLog],
};

function activeTab() {
  const el = document.querySelector('.nav-item.active[data-tab]');
  return el ? el.dataset.tab : 'overview';
}

// ทุกแท็บ: topbar (M1/M5 + ราคา) ต้องสดเสมอ
const ALWAYS = [refreshHeaderSignals];

let primed = false;

async function refreshAll() {
  // แท็บเบราว์เซอร์ถูกซ่อน → ไม่ต้องยิง API (ประหยัดทั้งเครื่องเราและ VPS)
  if (document.hidden) return;
  updateClock();
  // รอบแรกหลังโหลดหน้า: ยิงครบทุกแผงหนึ่งครั้ง เพื่อให้ข้อมูลทุกแท็บพร้อมก่อนสลับ
  // (รอบถัดไปเหลือเฉพาะแท็บที่เปิดอยู่ — ลด request ~60-70%)
  const fns = [...ALWAYS, ...(primed
    ? (TAB_GROUPS[activeTab()] || TAB_GROUPS.overview)
    : Object.values(TAB_GROUPS).flat())];
  primed = true;
  // allSettled: แผงหนึ่งพัง ห้ามลากทั้งรอบ (เดิม Promise.all → reject ทิ้ง → รอบถัดไปก็พังตาม)
  const results = await Promise.allSettled(fns.map((fn) => fn()));
  // stale badge: มีแผงไหนตอบสำเร็จถือว่าข้อมูลสด — ถ้าทุกแผงล่ม (API ล่ม) จะไม่ mark → badge ขึ้น
  if (results.some((r) => r.status === 'fulfilled')) markPollSuccess();
  checkNewSignals();
}

// C-8: กลับมาที่แท็บเบราว์เซอร์ → refresh ทันที (ไม่รอรอบ 5 วิ)
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshAll(); });
// C-8: กดเปลี่ยนแท็บ sidebar → refresh แผงของแท็บใหม่ทันที (ข้อมูลไม่ค้างจากตอนที่ยังไม่เคยเปิด)
document.addEventListener('click', (e) => {
  const nav = e.target instanceof Element ? e.target.closest('.nav-item[data-tab]') : null;
  if (nav) setTimeout(refreshAll, 0);
});


export { REFRESH_MS, refreshAll };
