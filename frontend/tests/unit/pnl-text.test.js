// pnlText.test.js — กฎ design_system 5.3 (Phase C-5): เลขคู่เครื่องหมาย + สี bull/bear/muted/warn เท่านั้น
import { describe, expect, it } from 'vitest';
import { pnlColor, pnlText, wrColor } from '../../src/shared/lib/pnlText.js';

describe('pnlText — เลขคู่เครื่องหมายเสมอ (+ / − / 0 ไม่มีเครื่องหมาย)', () => {
  it('โหมดปกติ (th-TH): กำไร +, ขาดทุน −, ศูนย์เปล่า (แบบ fmtMoney เดิมของ journal)', () => {
    expect(pnlText(123.45)).toBe('+123.45');
    expect(pnlText(-123.45)).toBe('-123.45');
    expect(pnlText(0)).toBe('0');
  });
  it('โหมด fixed (แบบ CFD): toFixed ทศนิยมตายตัว, เครื่องหมายวางหน้า prefix', () => {
    expect(pnlText(8.2, { fixed: true, digits: 2, prefix: '$' })).toBe('+$8.20');
    expect(pnlText(-8.2, { fixed: true, digits: 2, prefix: '$' })).toBe('-$8.20');
    expect(pnlText(0, { fixed: true, digits: 2, prefix: '$' })).toBe('$0.00');
  });
  it('suffix + digits: "+1,234.5 THB" — รูปแบบเลข th-TH เหมือนเดิม', () => {
    expect(pnlText(1234.5, { digits: 2, suffix: ' THB' })).toBe('+1,234.5 THB');
    expect(pnlText(-0.5, { suffix: ' THB' })).toBe('-0.5 THB');
  });
  it('ค่าไม่ใช่ตัวเลข (null/undefined/NaN) → "0" ไม่มีเครื่องหมาย', () => {
    expect(pnlText(null)).toBe('0');
    expect(pnlText(undefined)).toBe('0');
    expect(pnlText(NaN)).toBe('0');
  });
  it('digits:0 (แบบ chips กราฟ equity) → จำนวนเต็มปัดตาม toLocaleString', () => {
    expect(pnlText(1234.6, { digits: 0 })).toBe('+1,235');
    expect(pnlText(-1234.6, { digits: 0 })).toBe('-1,235');
  });
});

describe('pnlColor — คืน bull/bear/muted เท่านั้น (5.3: ไม่มีสีอื่น)', () => {
  it('บวก → bull, ลบ → bear', () => {
    expect(pnlColor(0.01)).toBe('bull');
    expect(pnlColor(-0.01)).toBe('bear');
  });
  it('ศูนย์/null/undefined/NaN → muted (แก้จุดเดิมที่ศูนย์ได้ green)', () => {
    expect(pnlColor(0)).toBe('muted');
    expect(pnlColor(null)).toBe('muted');
    expect(pnlColor(undefined)).toBe('muted');
    expect(pnlColor(NaN)).toBe('muted');
  });
});

describe('wrColor — สอง/สามระดับตาม threshold เดิมของแต่ละจุด', () => {
  it('ไม่ส่ง mid = สองระดับ: >=54.95 bull, น้อยกว่า bear (แบบ TP1 และ journal)', () => {
    expect(wrColor(54.95)).toBe('bull');
    expect(wrColor(54.94)).toBe('bear');
    expect(wrColor(60)).toBe('bull');
  });
  it('ส่ง mid = สามระดับ: >=54.95 bull · >=40 warn · น้อยกว่า bear (แบบ paper trading เดิม)', () => {
    expect(wrColor(55, 54.95, 40)).toBe('bull');
    expect(wrColor(45, 54.95, 40)).toBe('warn');
    expect(wrColor(39.9, 54.95, 40)).toBe('bear');
  });
  it('ส่ง good เองได้ (แบบ TP2 = 40 และ journal ใช้ breakeven จาก API)', () => {
    expect(wrColor(41, 40)).toBe('bull');
    expect(wrColor(39, 40)).toBe('bear');
    expect(wrColor(54.95, 52.5)).toBe('bull');
  });
  it('good เป็น null/ไม่ใช่เลข → fallback 54.95 (กัน API ไม่ส่ง breakeven)', () => {
    expect(wrColor(55, null)).toBe('bull');
    expect(wrColor(50, null)).toBe('bear');
  });
  it('ค่าไม่ใช่ตัวเลข → bear (เหมือนเดิมที่ >= ล้มเหลวแล้วตกกิ่งสีแดง)', () => {
    expect(wrColor(null)).toBe('bear');
    expect(wrColor(undefined)).toBe('bear');
  });
});