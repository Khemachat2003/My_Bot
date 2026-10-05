// markersCache.test.js — แคช markers ของตารางสัญญาณ (C-4): TTL 60 วิ + in-flight dedupe
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/shared/api/client.js', () => ({ fetchJSON: vi.fn() }));

import { fetchJSON } from '../../src/shared/api/client.js';
import { cachedMarkers, ensureMarkers, resetForTest, setMarkersCache } from '../../src/shared/lib/markersCache.js';

const MARKERS = [{ type: 'ML', id: 1, price: 2000, cfd: { sl: 1990, tp1: 2025, tp2: 2050 } }];
const MARKERS_URL = '/api/signals/markers?symbol=frxXAUUSD&limit=50';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
  resetForTest();
  fetchJSON.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  delete globalThis.document;
});

describe('setMarkersCache + cachedMarkers — TTL 60 วิ', () => {
  it('เก็บแล้วอ่านได้ภายใน 60 วิ (ขอบบน 60_000 ยังสด)', () => {
    expect(setMarkersCache(MARKERS)).toBe(true);
    expect(cachedMarkers()).toEqual(MARKERS);
    vi.advanceTimersByTime(60_000);
    expect(cachedMarkers()).toEqual(MARKERS);
  });
  it('เกิน 60 วิ → หมดอายุ (null) — ensureMarkers จะยิง fetch แทน', () => {
    setMarkersCache(MARKERS);
    vi.advanceTimersByTime(60_001);
    expect(cachedMarkers()).toBeNull();
  });
  it('ปฏิเสธ array ว่าง / ไม่ใช่ array — ไม่เขียนทับแคชเดิม', () => {
    setMarkersCache(MARKERS);
    expect(setMarkersCache([])).toBe(false);
    expect(setMarkersCache(null)).toBe(false);
    expect(cachedMarkers()).toEqual(MARKERS);
  });
});

describe('ensureMarkers', () => {
  it('แคชสดอยู่แล้ว → ไม่ยิง fetch', async () => {
    setMarkersCache(MARKERS);
    await expect(ensureMarkers()).resolves.toEqual(MARKERS);
    expect(fetchJSON).not.toHaveBeenCalled();
  });
  it('ยังไม่มีแคช → ยิง URL เดียวกับ refreshPrice แล้วเก็บลงแคช', async () => {
    fetchJSON.mockResolvedValue(MARKERS);
    await expect(ensureMarkers()).resolves.toEqual(MARKERS);
    expect(fetchJSON).toHaveBeenCalledTimes(1);
    expect(fetchJSON).toHaveBeenCalledWith(MARKERS_URL, 2500);
    expect(cachedMarkers()).toEqual(MARKERS);
  });
  it('TTL หมด → ยิง fetch ใหม่', async () => {
    setMarkersCache(MARKERS);
    vi.advanceTimersByTime(60_001);
    fetchJSON.mockResolvedValue(MARKERS);
    await expect(ensureMarkers()).resolves.toEqual(MARKERS);
    expect(fetchJSON).toHaveBeenCalledTimes(1);
  });
  it('dedupe: เรียกซ้อนกัน (loop + ตาราง ML + Setup) → fetch ครั้งเดียว', async () => {
    fetchJSON.mockResolvedValue(MARKERS);
    const [a, b, c] = await Promise.all([ensureMarkers(), ensureMarkers(), ensureMarkers()]);
    expect(fetchJSON).toHaveBeenCalledTimes(1);
    expect(a).toEqual(MARKERS);
    expect(b).toEqual(MARKERS);
    expect(c).toEqual(MARKERS);
  });
  it('fetch พัง → คืน [] ไม่ throw (ห้ามบล็อก render ตาราง)', async () => {
    fetchJSON.mockRejectedValue(new Error('boom'));
    await expect(ensureMarkers()).resolves.toEqual([]);
    expect(cachedMarkers()).toBeNull();
  });
  it('อ่าน symbol จาก #chartSymbol ถ้ามี DOM', async () => {
    globalThis.document = { getElementById: () => ({ value: 'frxEURUSD' }) };
    fetchJSON.mockResolvedValue(MARKERS);
    await expect(ensureMarkers()).resolves.toEqual(MARKERS);
    expect(fetchJSON).toHaveBeenCalledWith('/api/signals/markers?symbol=frxEURUSD&limit=50', 2500);
  });
});