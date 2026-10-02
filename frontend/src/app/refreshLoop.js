// รอบ refresh: refreshAll() เรียกทุกแผงพร้อมกัน
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1133–1134, 3446–3459 แบบ move-only

import { refreshCFDPaper } from '../features/cfd/index.js';
import { refreshPrice } from '../features/chart/index.js';
import { refreshGauges } from '../features/gauges/index.js';
import { refreshJournalMoney, refreshJournalTab } from '../features/journal/index.js';
import { refreshMlTab } from '../features/ml-signals/index.js';
import { checkNewSignals } from '../features/notifications/index.js';
import { refreshOverview } from '../features/overview/index.js';
import { refreshSetupAll, refreshSetupMini, refreshSetupTab } from '../features/setup-signals/index.js';
import { refreshHeaderSignals, updateClock } from '../features/status-bar/index.js';
import { refreshWatchlist } from '../features/watchlist/index.js';

const REFRESH_MS = 5000;

async function refreshAll(){
  updateClock();
  // watchlist ต้องไม่ถูกบล็อกโดยแผงอื่น — เดิมรออยู่หลัง Promise.all
  // ถ้าตัวไหนค้าง (VPS ช้า/ถูก reset) ทั้ง Promise.all ไม่จบ → watchlist ไม่มีอะไรขึ้นเลย
  refreshWatchlist().catch(()=>{});
  // allSettled: แผงหนึ่งพัง ห้ามลากทั้งรอบ (เดิม Promise.all → reject ทิ้ง → รอบถัดไปก็พังตาม)
  await Promise.allSettled([
    refreshOverview(),refreshPrice(),refreshGauges(),refreshHeaderSignals(),
    refreshMlTab(),refreshSetupTab(),refreshSetupMini(),refreshSetupAll(),
    refreshJournalTab(),refreshJournalMoney(),refreshCFDPaper(),
  ]);
  checkNewSignals();
}


export { REFRESH_MS, refreshAll };
