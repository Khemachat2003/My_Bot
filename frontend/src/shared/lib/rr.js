// rr.js — คำนวณ Risk:Reward จาก entry / sl / tp (pure function, ไม่มี side effect)
// ใช้โดยตารางสัญญาณ (ML / Setup) เพื่อแสดงคอลัมน์ R:R — แถวไหนข้อมูลไม่ครบคืน null

function rr(entry, sl, tp) {
  // null/undefined/'' ห้ามปล่อยผ่าน Number() — Number(null) และ Number('') ได้ 0 หลอก
  if ([entry, sl, tp].some((v) => v == null || v === '')) return null;
  const e = Number(entry), s = Number(sl), t = Number(tp);
  if (![e, s, t].every(Number.isFinite)) return null;
  const risk = Math.abs(e - s);
  if (!(risk > 1e-9)) return null;          // SL เท่ากับ entry (หรือมีข้อมูล) → หา R:R ไม่ได้
  const reward = Math.abs(t - e);
  if (!(reward > 0)) return null;
  return reward / risk;
}

export { rr };