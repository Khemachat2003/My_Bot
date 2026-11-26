# แผน Setup V2 — Gate ตามหลักฐานจากงานวิจัย (ส่งให้ผู้ใช้อนุมัติก่อนแตะโค้ด)

> สร้าง 2026-11-26 ต่อจากงานวิจัย session เดียวกัน (ดู WORKLOG 2026-11-26 สองรอบ)
> แผนนี้ = งาน C1/C2 ใน `docs/plan_c_d_upgrade.md` ฉบับอัปเดตด้วยหลักฐานใหม่ + เพิ่ม H1 trend gate

## 1. ทำไมต้องแก้ (สรุปหลักฐานจากข้อมูลจริง 6,758 เคส)

| หลักฐาน | ตัวเลข |
|---|---|
| แตะ EMA200 เปล่า ๆ ไม่มีสัญญาณ | binary WR 49.0% · CFD R:R ExpR −0.083 · กลับทิศก็แพ้ |
| **เทรน H1-EMA200 คือตัวแยกกำไร** | ตามเทรน ExpR **+0.032** vs สวนเทรน **−0.199** (gap 0.23R) |
| ADX ≥ 20 ช่วยจริง (เกตเดียวที่ lift ทั้ง 2 โครงสร้าง) | binary +2.9pp · CFD ตามเทรน+ADX ExpR **+0.068** PF 1.11 (n=707) |
| WICK_BOUNCE ในเทรนดาวน์แรงสุด | PUT +0.173R PF 1.31 (n=564) · XAUUSD ตามเทรน +0.386R PF 1.85 |
| `c3_rsi_ob_os` pass = แย่ลง | binary −2.9pp → ใช้เป็นเกตกัน |
| checklist 11 ข้อฉบับปัจจุบันไม่มี predictive power | 5 ใน 11 เป็น const (c10/c11 pass 0 ครั้ง — buffer M1 1000 แท่ง ≈ 17 ชม. ไม่พอคำนวณเทรน TF สูง, c8/c9 pass 100%) |
| repaint | ประเมินบนแท่งที่ยังไม่ปิด (`setup_feed.py:236-239`) → ทิศ/เงื่อนไขตัดสินจากข้อมูลที่ยังเปลี่ยนได้ |

**Setup ใหม่ที่จะทำให้ "จุดแตะ EMA200 + gate" กลายเป็นระบบที่ใช้ได้จริง:**
แตะ EMA200 บนแท่งปิดแล้ว → ดีด (WICK_BOUNCE) → **ทิศตรงเทรน H1-EMA200** → **ADX ≥ 20** → ไม่มี RSI OB/OS → FIRE

## 2. สิ่งที่จะแก้ (ชี้ไฟล์/ฟังก์ชัน/บรรทัดจริง)

### 2.1 เพิ่มข้อมูลเทรน H1 (setup_feed.py) — แก้รากที่ c10_mtf pass 0 ครั้ง
- `SetupFeedEngine.__init__` / `_seed_buffer`: seed แยกด้วย `fetch_candles_history(symbol, granularity=3600, count=1000)` → `self._h1_closes` (ประมาณ 1,000 ชั่วโมง ≈ 42 วัน พอสำหรับ EMA200(H1))
- ทุกรอบ poll: แต่ง H1 close ของชั่วโมงที่กำลังก่อตัวจาก M1 buffer (เฉพาะชั่วโมงที่ปิดแล้วเท่านั้นจะเข้า EMA — กัน lookahead เหมือน backtest)
- คำนวณ `self._h1_trend` = "UP" ถ้า close ชั่วโมงปิดล่าสุด > EMA200(H1), "DOWN" ถ้าต่ำกว่า, None ถ้าข้อมูลไม่พอ
- ส่งเข้า `score_setup(..., h1_trend=...)` ทั้ง path `_check_setup_scorer` และ `_check_tick_touch` (research ได้ column ใหม่ฟรีผ่าน conditions_json)

### 2.2 เกต v2 ใน score_setup (setup_scorer.py:588 ลายเซ็น + :720-739 ช่วง TIER)
- ลายเซ็น: `score_setup(df, timeframe, target_hold_minutes, symbol, h1_trend=None)` — additive, เทสต์/ผู้เรียกเดิมไม่กระทบ
- ใน `importance1` (แตะ EMA200): อ่าน `cfg["v2_gates"]` → ตรวจ 4 เกต:
  1. `h1_trend` ตรงทิศ (CALL↔UP, PUT↔DOWN; `None` = ไม่ผ่าน — fail-closed)
  2. `adx_val >= min_adx` (ใช้ adx_val ที่คำนวณแล้วใน score_setup)
  3. `touch_case in allowed_touch_cases` (default `["WICK_BOUNCE"]`)
  4. เงื่อนไขใน `avoid_conditions` ต้อง **ไม่** pass (default `["c3_rsi_ob_os"]`)
- โหมด: `shadow=true` → พฤติกรรมเดิมทุกอย่าง + จดผลเกตใน `conditions_log["_v2_gate"]` (pass/reasons) และ `_h1_trend` · `shadow=false` (enforce) → ไม่ผ่านเกต = `tier="WAIT"`, `entry_trigger=False`, note บอกเหตุผล (บันทึก setup_scores เหมือนเดิมทุกครั้ง)
- `_v2_gate`/`_h1_trend` ไหลไปเก็บใน `setup_scores.conditions_log` และ `tick_touch_log.conditions_json` **อัตโนมัติ** — ไม่แต้ม schema ไม่แต้ม API (กฎข้อ 5)

### 2.3 แก้ repaint (setup_feed.py `_check_setup_scorer` ~:477) = แผน C2 เดิม
- ประเมินจากแท่งที่ปิดแล้ว: resample จาก `self.buffer.iloc[:-1]` (ตัดแท่ง M1 ที่กำลังก่อตัว) แล้ว **ตัดแท่ง M5 ท้ายสุดที่ยังไม่ครบ 5 นาที** ออกก่อนคำนวณ EMA/ATR/ประเมิน
- ผลข้างเคียง: สัญญาณมาช้ากว่าเดิม ~1 แท่ง M5 (แลกกับทิศ/เงื่อนไขไม่ repaint) — cooldown อิง DB อยู่แล้วไม่กระทบ
- TICK_TOUCH (เคสแท่งยังไม่ปิด) เป็นของ research path อยู่แล้ว → gate `allowed_touch_cases` ไม่รวม

### 2.4 ค่า config (setup_config.json — ปรับได้ไม่ต้องแก้โค้ด, mtime-cache โหลดใหม่เอง)
```json
"v2_gates": {
  "enabled": false,          // P1: true (shadow เก็บสถิติ ไม่เปลี่ยนพฤติกรรม)
  "shadow": true,            // P2: false = enforce จริง
  "h1_trend_required": true,
  "min_adx": 20,
  "allowed_touch_cases": ["WICK_BOUNCE"],
  "avoid_conditions": ["c3_rsi_ob_os"],
  "live_symbols": ["frxXAUUSD"]   // enforce เฉพาะ symbol ในลิสต์, ตัวอื่น shadow ต่อ
}
```
default ที่ commit = `enabled:false` → **merge แล้วระบบพฤติกรรมเดิม 100%** จนกว่าจะเปิดที่ .env รายเครื่อง/VPS

## 3. แผนเดิน 2 เฟส

**P1 — Shadow (เปิดบน VPS แบบ enabled:true, shadow:true)**
- สัญญาณ/Telegram/CFD paper เดิมทั้งหมด — เพิ่ม log `_v2_gate` ให้วัดผลเงียบ ๆ
- วัดทุกสัปดาห์: (ก) query `setup_scores` เฉพาะ `_v2_gate.pass=true` → binary WR (ข) รันสคริปต์ CFD R:R backtest (เก็บไว้ที่ `scripts/data_tools/`) รวมข้อมูลใหม่ → ExpR/PF
- **เกณฑ์เปิด P2:** shadow ≥ 4 สัปดาห์ · gated n ≥ 300 · ExpR ≥ +0.05R และ PF ≥ 1.10 · ไม่มีสัปดาห์ไหน ExpR ติดลบชัดเจน · XAUUSD ยังเป็นตัวนำ

**P2 — Enforce (shadow:false, live_symbols เริ่มเฉพาะ frxXAUUSD)**
- ไม้ที่ไม่ผ่านเกต tier=WAIT (ยัง log ครบ) → Telegram เงียบลงเหลือไม้คุณภาพ
- CFD paper (เปิดอัตโนมัติ `_backfill_cfd_paper_trades` — SL 20/TP 40/60 pips แบบเดิม) ใช้เป็นเส้นวัดที่สอง · ทราบชัด: geometry ต่างจาก backtest (ATR-based) — ถ้าเลขไม่เข้ากันจะรายงานให้เทียบเอง
- symbol อื่นเป็น shadow ต่อจนครบเกณฑ์ → ค่อยเพิ่ม `live_symbols` ทีละตัวตาม ExpR ของตัวเอง (ข้อมูลชี้ USDJPY แย่สุด −0.295R → ไว้ท้ายสุด/ไม่เพิ่ม)

## 4. การเทสต์ (ห้ามแก้ characterization เดิม — เพิ่มอย่างเดียว)
- `tests/test_setup_scorer.py` เพิ่มเคส: เมทริกซ์เกต (ผ่านทุกข้อ / fail h1_trend=None fail-closed / fail adx / fail case BREAKOUT / fail เพราะ c3 pass) × shadow vs enforce + `_v2_gate` อยู่ใน conditions_log
- ไฟล์ใหม่ `tests/test_setup_feed_h1.py`: seed H1 fixture → trend UP/DOWN/None + ไม่ใช้ชั่วโมงที่ยังไม่ปิด (no-lookahead) + repaint fix (score ถูกเรียกบนแท่งปิดแล้ว)
- รัน `pytest -q` ทั้งชุด + `ruff check backend` — ต้องเขียวทั้งเดิมและใหม่ก่อน commit ทุกก้อน (pre-commit บังคับอยู่แล้ว)

## 5. ความเสี่ยง / กันไม้พลาด
| ความเสี่ยง | การกัน |
|---|---|
| ข้อมูลหลังฐานเป็นช่วงเหรียญแข็ง (PUT อาจเป็น regime) | shadow 4-6 สัปดาห์บนข้อมูลใหม่ก่อน enforce + ดู ExpR รายสัปดาห์ |
| H1 fetch เพิ่มโหลด Deriv | seed ครั้งเดียว 1,000 แท่ง + incremental จาก M1 ที่มีอยู่ |
| เปิดแล้วไม้น้อยเกินไป | `live_symbols` ขยายทีหลังได้ (config) — เริ่ม XAUUSD เพราะเลขดีสุด |
| ถอยหลัง | ตั้ง `enabled:false` ใน config = กลับพฤติกรรมเดิมทันที ไม่ต้อง rollback โค้ด |

## 6. ขอบเขตที่ "ไม่" แตะ
- `executor/`, สูตร R:R, `notifier.py` (สัญญาณไหลเหมือนเดิม), `db/cfd.py` ค่าคงที่ SL/TP, `backend/db/schema.py` (ไม่มี migration — ทุกอย่างใหม่ไหลผ่าน JSON log), รูปร่าง `/api/*` เดิม (กฎข้อ 5), deploy (แยกอนุมัติทีหลังตามกฎข้อ 2)

## 7. ด่านอนุมัติ
1. ✅ อนุมัติแผนนี้ → ลงมือ P1 บน branch `feature/setup-v2-gates` (commit เล็กทีละขั้น + เทสต์ครบทุกก้อน)
2. ⏳ โชว์ผล + diff ให้ตรวจก่อน merge/deploy (กฎข้อ 2 — push tag เฉพาะเมื่อสั่ง)
3. ⏳ เปิด shadow บน VPS → รายงานรายสัปดาห์ → ตัดสินเปิด enforce พร้อมกัน
