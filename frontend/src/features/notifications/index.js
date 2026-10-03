// features/notifications — ทางเข้าเดียว (public API) ของ feature นี้: feature อื่น/app import ผ่านไฟล์นี้เท่านั้น
// ไฟล์ใน feature: newSignalAlert.js, recentSignalsLog.js (Phase C-2)
export { checkNewSignals, requestNotifPermission } from './newSignalAlert.js';
export { refreshRecentSignalsLog } from './recentSignalsLog.js';
