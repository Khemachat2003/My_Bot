// markersCache.js — แคชผล /api/signals/markers ที่ refreshPrice ดึงมาวาดกราฟอยู่แล้ว
// C-4 Signal Center: ตารางสัญญาณอ่านจากแคชนี้แทนการ fetch ซ้ำ (ไม่เพิ่ม request ใหม่)
// เก็บไว้ 60 วิ — ถ้าเกิน (หรือยังไม่มีข้อมูลเลย) refreshLoop จะ prefetch ให้ก่อน render

import { fetchJSON } from '../api/client.js';

const MAX_AGE_MS = 60000;
let cache = { markers: null, fetchedAt: 0 };
let inflight = null;   // dedupe: เรียก ensureMarkers ซ้อนกัน (loop + ตาราง ML + Setup) → fetch ครั้งเดียว

function markersAge() {
  return cache.markers && cache.markers.length ? Date.now() - cache.fetchedAt : Infinity;
}

function setMarkersCache(markers) {
  if (!Array.isArray(markers) || !markers.length) return false;
  cache = { markers, fetchedAt: Date.now() };
  return true;
}

function cachedMarkers() {
  return markersAge() <= MAX_AGE_MS ? cache.markers : null;
}

// URL/params เดียวกับที่ refreshPrice ยิง — เอา symbol จาก select ของกราฟถ้ามี (guard ไว้สำหรับ node/test)
function markersUrl() {
  let sym = 'frxXAUUSD';
  try {
    const el = typeof document !== 'undefined' ? document.getElementById('chartSymbol') : null;
    if (el && el.value) sym = el.value;
  } catch (e) { /* ไม่มี DOM — ใช้ default */ }
  return '/api/signals/markers?symbol=' + encodeURIComponent(sym) + '&limit=50';
}

// ถ้าแคชสดอยู่แล้ว คืนทันที — ไม่งั้นยิง /api/signals/markers เอง ด้วย timeout สั้น (2.5 วิ)
// เพื่อไม่ให้ render ตารางรอนาน — concurrent เรียกซ้อนกันรอ promise เดียวกัน (dedupe)
async function ensureMarkers() {
  const fresh = cachedMarkers();
  if (fresh) return fresh;
  if (!inflight) {
    inflight = fetchJSON(markersUrl(), 2500)
      .then((m) => { setMarkersCache(m); return m; })
      .catch(() => null)                     // fetch พัง → ใช้แคชเดิม/ว่างต่อ ห้ามบล็อก render ตาราง
      .finally(() => { inflight = null; });
  }
  await inflight;
  return cachedMarkers() || [];
}

// เทสต์เท่านั้น — เคลียร์แคช + in-flight ระหว่าง case
function resetForTest() {
  cache = { markers: null, fetchedAt: 0 };
  inflight = null;
}

export { cachedMarkers, ensureMarkers, resetForTest, setMarkersCache };