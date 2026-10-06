// siglog-rows.test.js — mergeRows ของ sub-tab "ประวัติสัญญาณ" (C-6)
// pure function ที่ export อยู่แล้วแต่ยังไม่มีเทสต์ — ล็อกพฤติกรรมเดิมทุกค่า
// (merge ML+Setup / sort เวลาใหม่→เก่า ข้ามระบบ / slice 100 / field ขาด → '–')
// เฉพาะหน้าตา (badge ทิศ C-6) ไม่ได้อยู่ที่นี่ — mergeRows คืนข้อมูลดิบ การแสดงผลเป็นงานของ render
import { describe, expect, it } from 'vitest';
import { mergeRows } from '../../src/features/notifications/recentSignalsLog.js';

describe('mergeRows — รวมสัญญาณ ML + Setup เป็นตารางเดียว', () => {
  it('merge สองระบบ → kind ตรงต้นทาง + strength แปลงตามเดิม (ML % / Setup x.x/total)', () => {
    const rows = mergeRows(
      [{ signal_time: '2026-01-02T10:00:00', direction: 'CALL', entry_price: 2650.5, confidence: 0.785, result: 'WIN' }],
      [{ signal_time: '2026-01-01T09:00:00', direction: 'PUT', entry_price: 2640.25, score: 7.5, total: 11, result: 'LOSE' }],
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      t: '2026-01-02T10:00:00', kind: 'ML', dir: 'CALL', price: 2650.5, strength: '78.5%', result: 'WIN',
    });
    expect(rows[1]).toEqual({
      t: '2026-01-01T09:00:00', kind: 'Setup', dir: 'PUT', price: 2640.25, strength: '7.5/11', result: 'LOSE',
    });
  });

  it('sort เวลาใหม่→เก่า ข้ามระบบ (ML/Setup สลับลำดับตามเวลา)', () => {
    const rows = mergeRows(
      [{ signal_time: '2026-01-01T08:00:00', direction: 'CALL', entry_price: 1, confidence: 0.5, result: null }],
      [{ signal_time: '2026-01-01T12:00:00', direction: 'PUT', entry_price: 1, score: 5, total: 10, result: 'WIN' }],
    );
    expect(rows.map((r) => r.kind)).toEqual(['Setup', 'ML']);
  });

  it('slice 100 — เกิน 100 แถวเก็บใหม่สุด (ตัดเก่าสุดทิ้ง)', () => {
    const ml = Array.from({ length: 120 }, (_, i) => ({
      signal_time: `2026-01-01T${String(Math.floor(i / 60)).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}:00`,
      direction: 'CALL', entry_price: 1, confidence: 0.5, result: null,
    }));
    const rows = mergeRows(ml, []);
    expect(rows).toHaveLength(100);
    expect(rows[0].t).toBe('2026-01-01T01:59:00');  // ใหม่สุด
    expect(rows[99].t).toBe('2026-01-01T00:20:00'); // เก่าสุดที่เหลือ — 00:00–00:19 (20 แถว) ถูกตัด
  });

  it('field ขาด → strength เป็น – (confidence null / score null) — price/result คงค่าดิบ', () => {
    const rows = mergeRows(
      [{ signal_time: '2026-01-02T11:00:00', direction: 'PUT', entry_price: 2640, score: null, result: null }],
      [{ signal_time: '2026-01-02T10:00:00', direction: 'CALL', entry_price: null, confidence: null, result: null }],
    );
    expect(rows[0].strength).toBe('–'); // Setup — score ขาด
    expect(rows[1].strength).toBe('–'); // ML — confidence ขาด
    expect(rows[1].price).toBeNull();   // ราคาขาด → render เป็น – เอง
  });

  it('total ขาดแต่มี score → x.x/–', () => {
    const rows = mergeRows([], [{ signal_time: '2026-01-01T09:00:00', direction: 'PUT', entry_price: 1, score: 7.5 }]);
    expect(rows[0].strength).toBe('7.5/–');
  });

  it('ทิศทาง/ผลคงค่าดิบ (BUY/SELL ไม่ถูกแปลง — mapping เป็นงานของ render)', () => {
    const rows = mergeRows(
      [{ signal_time: '2026-01-01T10:00:00', direction: 'BUY', entry_price: 1, confidence: 0.9, result: 'PENDING' }],
      [{ signal_time: '2026-01-01T09:30:00', direction: 'SELL', entry_price: 1, score: 9, total: 10, result: null }],
    );
    expect(rows[0]).toMatchObject({ dir: 'BUY', result: 'PENDING' });
    expect(rows[1]).toMatchObject({ dir: 'SELL', result: null });
  });

  it('signal_time ขาด → ไปท้ายสุด (sort ด้วย String(t || ""))', () => {
    const rows = mergeRows(
      [{ direction: 'CALL', entry_price: 1, confidence: 0.5, result: null }],
      [{ signal_time: '2026-01-01T09:00:00', direction: 'PUT', entry_price: 1, score: 5, total: 10, result: 'WIN' }],
    );
    expect(rows[0].t).toBe('2026-01-01T09:00:00');
    expect(rows[1].t).toBeUndefined(); // t คงค่าดิบ — String(t || '') มีผลแค่ตอน sort (row ว่างไปท้าย)
  });

  it('ไม่มีข้อมูลทั้งสองระบบ → [] (แผงแสดง empty state)', () => {
    expect(mergeRows([], [])).toEqual([]);
  });
});