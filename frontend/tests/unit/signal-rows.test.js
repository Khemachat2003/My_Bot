// signalRows.test.js — helper ตารางสัญญาณ C-4: rr / markerIndex / cfdInfo / dirBadge / cfdCells
import { describe, expect, it } from 'vitest';
import { rr } from '../../src/shared/lib/rr.js';
import { cfdCells, cfdInfo, dirBadge, markerIndex } from '../../src/shared/lib/signalRows.js';

describe('rr — Risk:Reward = |tp-entry| / |entry-sl|', () => {
  it('CALL (entry 2000, SL 1990, TP 2025) → risk 10 reward 25 → 2.5', () => {
    expect(rr(2000, 1990, 2025)).toBeCloseTo(2.5, 10);
  });
  it('PUT (entry ต่ำกว่า SL/TP) → abs ทั้งสองด้าน ค่าเท่าเดิม', () => {
    expect(rr(2000, 2010, 1975)).toBeCloseTo(2.5, 10);
  });
  it('ข้อมูลไม่ครบ/ไม่ใช่ตัวเลข → null (รวม null/undefined/เกิน)', () => {
    expect(rr(null, 1990, 2025)).toBeNull();     // Number(null)=0 หลอก — ต้องเช็คก่อน
    expect(rr(2000, undefined, 2025)).toBeNull();
    expect(rr(2000, 1990, NaN)).toBeNull();
    expect(rr('abc', 1990, 2025)).toBeNull();
  });
  it('SL เท่ากับ entry (risk = 0) → null', () => {
    expect(rr(2000, 2000, 2025)).toBeNull();
  });
  it('TP เท่ากับ entry (reward = 0) → null', () => {
    expect(rr(2000, 1990, 2000)).toBeNull();
  });
});

describe('markerIndex — first-wins (markers เรียงใหม่→เก่า)', () => {
  it('key เดียวกันซ้ำ → เอาตัวแรก (ล่าสุด)', () => {
    const idx = markerIndex([
      { type: 'ML', id: 7, cfd: { sl: 1 } },
      { type: 'ML', id: 7, cfd: { sl: 2 } },
      { type: 'SETUP', id: 3, cfd: { sl: 3 } },
    ]);
    expect(idx['ML:7'].cfd.sl).toBe(1);
    expect(idx['SETUP:3'].cfd.sl).toBe(3);
    expect(idx['SETUP:9']).toBeUndefined();
  });
  it('marker ไม่มี type/id → ข้าม (รวม null/ไม่ใช่ array)', () => {
    expect(markerIndex([null, {}, { type: 'ML' }, { id: 1 }])).toEqual({});
    expect(markerIndex('not-array')).toEqual({});
  });
});

describe('cfdInfo — จับคู่แถวกับ CFD จาก markers', () => {
  const markers = [
    { type: 'ML', id: 1, price: 2000, cfd: { sl: 1990, tp1: 2025, tp2: 2050 } },
    { type: 'SETUP', id: 2, price: 3000 }, // ไม่มี cfd
  ];
  it('มี cfd → ได้ sl/tp1/tp2 + rr1/rr2 (คิดจาก marker price)', () => {
    const c = cfdInfo('ML', 1, markers);
    expect(c.sl).toBe(1990);
    expect(c.tp1).toBe(2025);
    expect(c.tp2).toBe(2050);
    expect(c.rr1).toBeCloseTo(2.5, 10);   // reward 25 / risk 10
    expect(c.rr2).toBeCloseTo(5, 10);     // reward 50 / risk 10
  });
  it('ไม่มี cfd / ไม่เจอ marker → {} (ตารางแสดง –)', () => {
    expect(cfdInfo('SETUP', 2, markers)).toEqual({});
    expect(cfdInfo('ML', 99, markers)).toEqual({});
  });
});

describe('dirBadge — ▲ CALL / ▼ PUT / ○ รอ (คู่สี dim+semantic)', () => {
  it('ทิศทางที่รู้จัก → badge call/put', () => {
    expect(dirBadge('CALL')).toBe('<span class="dir-badge call">▲ CALL</span>');
    expect(dirBadge('PUT')).toBe('<span class="dir-badge put">▼ PUT</span>');
  });
  it('ทิศอื่น/ว่าง → badge wait', () => {
    expect(dirBadge('')).toBe('<span class="dir-badge wait">○ รอ</span>');
    expect(dirBadge(null)).toBe('<span class="dir-badge wait">○ รอ</span>');
  });
});

describe('cfdCells — 3 <td> ต่อท้าย Entry: SL / TP1·TP2 / R:R', () => {
  const markers = [
    { type: 'ML', id: 1, price: 2000, cfd: { sl: 1990, tp1: 2025, tp2: 2050 } },
    { type: 'SETUP', id: 2, price: 3000, cfd: { sl: 2990, tp1: 3015, tp2: 3040 } },
  ];
  it('ML dec=2 → ทศนิยม 2 ตำแหน่ง, R:R รูปแบบ 1:x.x คู่ TP1/TP2', () => {
    const html = cfdCells('ML', 1, markers, 2);
    expect(html).toContain('<td class="mono">1990.00</td>');
    expect(html).toContain('<td class="mono">2025.00 / 2050.00</td>');
    expect(html).toContain('<td class="mono">1:2.5 / 1:5.0</td>');
    expect(html.split('<td').length - 1).toBe(3);
  });
  it('Setup dec=5 → ทศนิยม 5 ตำแหน่ง (ตามคอลัมน์ Entry)', () => {
    const html = cfdCells('SETUP', 2, markers, 5);
    expect(html).toContain('<td class="mono">2990.00000</td>');
    expect(html).toContain('<td class="mono">3015.00000 / 3040.00000</td>');
  });
  it('ไม่มี CFD → ทุกช่องเป็น –', () => {
    expect(cfdCells('ML', 99, markers, 2))
      .toBe('<td class="mono">–</td><td class="mono">–</td><td class="mono">–</td>');
  });
  it('TP ขาดตัวใดตัวหนึ่ง → ช่องนั้นเป็น – แต่อีกตัวยังแสดง', () => {
    const m = [{ type: 'ML', id: 3, price: 2000, cfd: { sl: 1990, tp1: 2025 } }];
    expect(cfdCells('ML', 3, m, 2)).toContain('<td class="mono">2025.00 / –</td>');
  });
});