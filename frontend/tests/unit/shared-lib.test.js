// formatTime.test.js — ทดสอบสูตร/format ที่ย้ายมาจาก index.html เดิม (move-only → ค่าต้องตรงเดิม)
import { describe, expect, it } from 'vitest';
import { fmtHM, fmtTime } from '../../src/shared/lib/formatTime.js';
import { _buildEqData } from '../../src/shared/lib/equityData.js';
import { adx, fractal, rsi } from '../../src/shared/lib/indicators.js';

describe('formatTime', () => {
  it('ค่าว่าง → –', () => {
    expect(fmtTime(null)).toBe('–');
    expect(fmtHM('')).toBe('–');
  });
  it('format แบบ th-TH 2 หลัก', () => {
    expect(fmtHM('2026-10-02T10:30:05')).toMatch(/^10:30:05$/);
  });
});

describe('indicators (คำนวณเพื่อวาดกราฟ — ต้องคงสูตรเดิม)', () => {
  it('rsi: ไต่ขึ้นต่อเนื่อง → ใกล้ 100', () => {
    const closes = Array.from({ length: 30 }, (_, i) => 2400 + i);
    expect(rsi(closes, 14)[29]).toBeCloseTo(100, 5);
  });
  it('adx: ขึ้นตรงๆ → DI+ มากกว่า DI-', () => {
    const h = Array.from({ length: 40 }, (_, i) => 10 + i);
    const l = Array.from({ length: 40 }, (_, i) => 9 + i);
    const c = Array.from({ length: 40 }, (_, i) => 9.5 + i);
    const out = adx(h, l, c, 14);
    expect(out.pdi[39]).toBeGreaterThan(out.ndi[39]);
    expect(out.adx[39]).toBeGreaterThan(0);
  });
  it('fractal: ยอดกลางสูงสุดใน 15 แท่ง', () => {
    const nd = Array.from({ length: 20 }, (_, i) => ({ h: i, l: i - 1, c: i - 0.5, o: i - 0.5, i }));
    nd[10].h = 25; // ยอด
    expect(fractal(nd, 7, 7).filter((p) => p.t === 'H').pop()?.v).toBe(25);
  });
});

describe('equityData._buildEqData', () => {
  it('รวม capital + equity*stake และเรียงเวลาไม่ซ้ำ (สูตรเดิม)', () => {
    const out = _buildEqData(
      { capital: 5000, stake: 100, points: [{ t: '2026-01-01 10:00:00', equity: 0.1 }, { t: '2026-01-02 10:00:00', equity: 0.2 }] },
      { base: 5000, points: [{ exit_time: '2026-01-01 11:00:00', pnl: 8.2 }] },
    );
    expect(out.optPts[0].value).toBe(5010);
    expect(out.optPnl).toBe(5020 - 5000);
    expect(out.cfdPts[0].value).toBe(5008);
    expect(out.cfdPnl).toBe(8);
  });
});
