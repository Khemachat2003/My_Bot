// pnlText.js — ตัวเลขผลงาน + กฎสี design_system 5.3 (Phase C-5)
//   กำไร = --bull คู่ + · ขาดทุน = --bear คู่ − · ศูนย์/ยังไม่ปิด = --muted — ไม่มีสีอื่น
//   ข้อความ: เลขคู่เครื่องหมายเสมอ (+123.45 / -123.45 / 0 ไม่มีเครื่องหมาย)
//   คงรูปแบบเลขเดิมของแต่ละจุด: fixed=true → toFixed (แบบ CFD) · ปกติ → toLocaleString('th-TH') (แบบ journal)

function pnlText(v, opts) {
  const o = opts || {};
  const digits = o.digits == null ? 2 : o.digits;
  const prefix = o.prefix || '', suffix = o.suffix || '';
  const n = Number(v);
  if (!Number.isFinite(n)) return prefix + '0' + suffix; // null/undefined/NaN → '0' (สีจัดการโดย pnlColor → muted)
  const sign = n > 0 ? '+' : (n < 0 ? '-' : '');
  const body = o.fixed
    ? Math.abs(n).toFixed(digits)
    : Math.abs(n).toLocaleString('th-TH', { maximumFractionDigits: digits });
  return sign + prefix + body + suffix;
}

// ชื่อ token สี ('bull'|'bear'|'muted') ตามค่า P&L — ศูนย์/ไม่ใช่ตัวเลข → 'muted' (แก้จุดเดิมที่ศูนย์ได้ green ผิดกฎ 5.3)
function pnlColor(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return 'muted';
  return n > 0 ? 'bull' : 'bear';
}

// สี winrate ('bull'|'warn'|'bear'): wr >= good → bull · ส่ง mid = 3 ระดับ (>= mid → warn) · นอกนั้น bear
// ไม่ส่ง mid = สองระดับ ตามพฤติกรรมเดิมของ backtest TP1/TP2 และแท็บ Journal (good = breakeven จาก API)
function wrColor(wr, good = 54.95, mid = null) {
  if (good == null || !Number.isFinite(Number(good))) good = 54.95; // API ไม่ส่ง breakeven → ใช้ค่า default
  const n = Number(wr);
  if (!Number.isFinite(n)) return 'bear'; // เหมือนเดิม: >= ล้มเหลวแล้วตกกิ่งสีแดง
  if (n >= good) return 'bull';
  if (mid != null && n >= mid) return 'warn';
  return 'bear';
}

export { pnlColor, pnlText, wrColor };