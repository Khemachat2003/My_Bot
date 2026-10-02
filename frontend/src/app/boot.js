// เริ่มระบบ: โหลด symbol → ขอสิทธิ์แจ้งเตือน → refreshAll ทุก REFRESH_MS
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3460–3466 แบบ move-only

import { requestNotifPermission } from '../features/notifications/index.js';
import { loadSymbols } from '../features/watchlist/index.js';
import { REFRESH_MS, refreshAll } from './refreshLoop.js';

(async()=>{
  await loadSymbols();
  requestNotifPermission();
  refreshAll();
  setInterval(refreshAll, REFRESH_MS);
})();
