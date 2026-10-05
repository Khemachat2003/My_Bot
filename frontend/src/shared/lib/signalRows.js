// signalRows.js — helper กลางของตารางสัญญาณ (ML + Setup): จับคู่แถวกับ CFD SL/TP จาก
// markers cache (/api/signals/markers — ข้อมูลเดียวกับกราฟ) + badge ทิศทาง ▲/▼/○
// C-4 Signal Center: ตารางจะ map กับ markers ด้วย type+id แทนการยิง API ใหม่

import { rr } from './rr.js';

// index[`${type}:${id}`] = marker (ต้องมี cfd) — เรียกซ้ำถูก เพราะ build จาก array เดิม
function markerIndex(markers) {
  const idx = {};
  (Array.isArray(markers) ? markers : []).forEach(m => {
    if (m && m.type && m.id != null) {
      const key = `${m.type}:${m.id}`;
      if (!idx[key]) idx[key] = m;   // markers sort ใหม่→เก่า อยู่แล้ว — เอาตัวแรก (ล่าสุด)
    }
  });
  return idx;
}

// คืน {sl, tp1, tp2, rr1, rr2} จาก markers cache — แถวไหนไม่มี CFD คืนค่าว่าง (ตารางแสดง –)
function cfdInfo(type, id, markers) {
  const m = markerIndex(markers)[`${type}:${id}`];
  if (!m || !m.cfd) return {};
  const c = m.cfd;
  return {
    sl: c.sl,
    tp1: c.tp1,
    tp2: c.tp2,
    rr1: rr(m.price, c.sl, c.tp1),
    rr2: rr(m.price, c.sl, c.tp2),
  };
}

// badge ทิศทาง — pattern เดียวกับ gauge C-3: ▲ CALL / ▼ PUT / ○ รอ (ทิศอื่น/ว่าง)
function dirBadge(direction) {
  if (direction === 'CALL') return '<span class="dir-badge call">▲ CALL</span>';
  if (direction === 'PUT') return '<span class="dir-badge put">▼ PUT</span>';
  return '<span class="dir-badge wait">○ รอ</span>';
}

// 3 <td> ต่อท้ายคอลัมน์ Entry ของตาราง: SL · TP1/TP2 · R:R — dec ตามคอลัมน์ Entry ของตารางนั้น
// (ML toFixed(2) / Setup toFixed(5)) — แถวไหนไม่มี CFD แสดง – ทุกช่อง
function cfdCells(type, id, markers, dec = 2) {
  const c = cfdInfo(type, id, markers);
  const fx = (v) => (v == null || !Number.isFinite(Number(v))) ? '–' : Number(v).toFixed(dec);
  const tp = (c.tp1 != null || c.tp2 != null) ? `${fx(c.tp1)} / ${fx(c.tp2)}` : '–';
  const rrTxt = (v) => (v == null ? '–' : '1:' + v.toFixed(1));
  const rrCell = (c.rr1 != null || c.rr2 != null) ? `${rrTxt(c.rr1)} / ${rrTxt(c.rr2)}` : '–';
  return `<td class="mono">${fx(c.sl)}</td><td class="mono">${tp}</td><td class="mono">${rrCell}</td>`;
}

export { cfdCells, cfdInfo, dirBadge, markerIndex };