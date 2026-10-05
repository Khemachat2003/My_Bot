// รอบ refresh: refreshAll() เรียกทุกแผงพร้อมกัน
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1133–1134, 3446–3459 แบบ move-only
// Phase C-2: + refreshRecentSignalsLog (Log/Alert) + stale badge (markPollSuccess)
// Phase C-4: + ensureMarkers prefetch ให้ตารางสัญญาณ (แคชเดียวกับกราฟ)

import { refreshCFDPaper } from '../features/cfd/index.js';
import { refreshPrice } from '../features/chart/index.js';
import { refreshGauges } from '../features/gauges/index.js';
import { refreshJournalMoney, refreshJournalTab } from '../features/journal/index.js';
import { refreshMlTab } from '../features/ml-signals/index.js';
import { checkNewSignals, refreshRecentSignalsLog } from '../features/notifications/index.js';
import { refreshOverview } from '../features/overview/index.js';
import { refreshSetupAll, refreshSetupMini, refreshSetupTab } from '../features/setup-signals/index.js';
import { refreshHeaderSignals, updateClock } from '../features/status-bar/index.js';
import { refreshWatchlist } from '../features/watchlist/index.js';
import { ensureMarkers } from '../shared/lib/markersCache.js';
import { markPollSuccess } from './staleBadge.js';

const REFRESH_MS = 5000;

async function refreshAll(){
  updateClock();
  // watchlist ต้องไม่ถูกบล็อกโดยแผงอื่น — เดิมรออยู่หลัง Promise.all
  // ถ้าตัวไหนค้าง (VPS ช้า/ถูก reset) ทั้ง Promise.all ไม่จบ → watchlist ไม่มีอะไรขึ้นเลย
  refreshWatchlist().catch(()=>{});
  refreshRecentSignalsLog().catch(()=>{});
  // C-4: prefetch markers ให้ตารางสัญญาณ (แคชยังสด = no-op) — fire-and-forget ห้ามบล็อกรอบ
  ensureMarkers().catch(()=>{});
  // allSettled: แผงหนึ่งพัง ห้ามลากทั้งรอบ (เดิม Promise.all → reject ทิ้ง → รอบถัดไปก็พังตาม)
  const results = await Promise.allSettled([
    refreshOverview(),refreshPrice(),refreshGauges(),refreshHeaderSignals(),
    refreshMlTab(),refreshSetupTab(),refreshSetupMini(),refreshSetupAll(),
    refreshJournalTab(),refreshJournalMoney(),refreshCFDPaper(),
  ]);
  // stale badge: มีแผงไหนตอบสำเร็จถือว่าข้อมูลสด — ถ้าทุกแผงล่ม (API ล่ม) จะไม่ mark → badge ขึ้น
  if (results.some(r=>r.status==='fulfilled')) markPollSuccess();
  checkNewSignals();
}


export { REFRESH_MS, refreshAll };
