// staleBadge.test.js — logic Data Age / Stale badge (Phase C-2, เงื่อนไขผู้ใช้ข้อ 5)
import { describe, expect, it } from 'vitest';
import { staleState } from '../../src/app/staleBadge.js';

describe('staleState — stale badge', () => {
  it('ระบบปกติ (ตอบสำเร็จภายใน 2×REFRESH_MS) → null = ซ่อน badge', () => {
    const now = 10_000_000;
    expect(staleState(now - 1_000, now, 5_000)).toBeNull(); // 1 วิ
    expect(staleState(now - 5_000, now, 5_000)).toBeNull(); // 5 วิ = 1 รอบ
    expect(staleState(now - 10_000, now, 5_000)).toBeNull(); // 10 วิ = 2 รอบ (ขอบบน)
  });
  it('API ล่ม (เกิน 2×REFRESH_MS) → บอกเวลาค้างเป็นวินาที', () => {
    const now = 10_000_000;
    expect(staleState(now - 10_001, now, 5_000)).toEqual({ ageMs: 10_001, sec: 10 });
    expect(staleState(now - 65_000, now, 5_000)).toEqual({ ageMs: 65_000, sec: 65 });
  });
  it('ยังไม่เคย markPollSuccess (lastOk=0) → ยังไม่แสดง (หน้าเพิ่งเปิด)', () => {
    expect(staleState(0, 10_000_000, 5_000)).toBeNull();
  });
});