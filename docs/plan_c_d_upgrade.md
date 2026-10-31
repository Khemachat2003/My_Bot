# Handoff: Phase ถัดไป — C (Winrate Logic Fix) + D (VPS Upgrade)

> เอกสารส่งต่องาน สร้าง 2026-10-31 หลังปิดงาน A (disk quick-win) + B (auto_retrain fix + DB data pipeline)
> อ่านคู่กับ `WORKLOG.md` (LOCAL เท่านั้น) — รายงาน audit เต็มอยู่ใน entry 2026-10-31

---

## สถานะที่ปิดแล้ว (A + B)

### A — Disk quick-win บน VPS (207.148.123.201, ~/My_Bot)
- ลบ `~/.vscode-server` (คืน ~5.1 GB)
- Prune `data/backups/` เหลือ 3 zip ล่าสุด (คืน ~1 GB)
- Prune `setup_scores` เก่ากว่า 7 วัน + `VACUUM` bot.db (1.85 GB → ลดลงมาก)
- หมายเหตุ: ถ้ายังไม่ได้ทำ → ทำใหม่ได้ตามคำสั่งใน WORKLOG entry 2026-10-31

### B — auto_retrain fix (commit `9701626` + tag v1.0.5 แล้ว deploy)
- **Root cause ที่ยืนยัน:** แถวขยะ `"0"` บรรทัดที่ 4 ของ `data/deriv_R_100_60s.csv` บน VPS
  → `pd.read_csv(parse_dates=["datetime"])` คืน object Index → `df.index.tz` AttributeError
  → auto_retrain ตายทุกรอบ (ทุก 6 ชม.) ตั้งแต่ ~10 ต.ค. 2026 · โมเดล production ค้างที่ 2 ส.ค.
- **แก้ใน `backend/ml_forecaster/auto_retrain.py`:**
  - `_load_price_data(data_dir=None)` — parse แบบกันพัง: `pd.to_datetime(..., errors="coerce", utc=True)`
    + `pd.to_numeric(..., errors="coerce")` + dropna → แถวขยะถูกข้ามอัตโนมัติ
  - เพิ่ม `_load_prices_from_db()` — ดึงแท่ง M1 สดล่าสุด (50,000 แท่ง/symbol ≈ 34 วัน) จากตาราง
    `prices` ใน bot.db มารวมกับ CSV cache (DB ใส่ท้าย → ทับแท่งซ้ำเก่าตอน dedupe keep="last")
    → ข้อมูลเทรนไม่ค้างที่ 2 ต.ค. อีกต่อไป (cache CSV เดิมถูก "กัน count เล็กทับ" ทำให้ไม่เคยอัปเดต)
- **เทสต์:** `tests/test_auto_retrain_price_data.py` (4 เคส: แถวขยะ/ไฟล์ว่าง/ตัวเลขเพี้ยน/อ่าน DB)
- **ตรวจหลัง deploy:** รอ auto_retrain รอบถัดไป (ทุก 6 ชม.) แล้วเช็ค `docker logs xauusd-bot`
  ต้องไม่มี `AttributeError: 'Index' object has no attribute 'tz'` อีก และ mtime ของ
  `backend/ml_forecaster/model_m5.joblib` บน VPS ต้องเปลี่ยน + มี Telegram [AUTO-RETRAIN]
- แถวขยะใน CSV บน VPS แก้ด้วยมือแล้ว (ถ้ายัง: `sed -i '/^0$/d' data/deriv_R_100_60s.csv`)

---

## งาน C — ยก Winrate Rule-Based (⛔ กฎเหล็กข้อ 1: ต้องถามผู้ใช้อนุมัติก่อนแตะ)

### ข้อเท็จจริงจาก DB (ยืนยัน 2026-10-31)
- `setup_signals`: WIN 841 / LOSE 876 / DRAW 8 = **49.0%** (ต่ำกว่า BE และต่ำกว่า ML 53.24%)
- เทียบ: เดือน ต.ค. ML ทำ ~61% (52W/33L) — โมเดลจาก 2 ส.ค. ทำงานได้จริง

### จุดบกพร่องที่พบ (พร้อมบรรทัดอ้างอิง)


## งาน C — ยก Winrate Rule-Based (⛔ กฎเหล็กข้อ 1: ต้องถามผู้ใช้อนุมัติก่อนแตะ)

### ข้อเท็จจริงจาก DB (ยืนยัน 2026-10-31)
- `setup_signals`: WIN 841 / LOSE 876 / DRAW 8 = **49.0%** (ต่ำกว่า BE และต่ำกว่า ML 53.24%)
- เทียบ: เดือน ต.ค. ML ทำ ~61% (52W/33L) — โมเดลจาก 2 ส.ค. ทำงานได้จริง

### จุดบกพร่องที่พบ (พร้อมบรรทัดอ้างอิง)

1. **Tier 1 ยิงไม่สน checklist** — `backend/setup_scorer.py:720-737`:
   `if importance1: tier = "FIRE"` แม้ `passed_count` = 0/11 · c5 ADX / c10 MTF / c11 slope
   เป็น "log เฉย ๆ" ไม่เกตอะไรเลย → สัญญาณหลอกจากแท่งที่แตะ EMA200 ตอนตลาดเฉื่อย

2. **Repaint — ประเมินบนแท่งที่ยังไม่ปิด** — `backend/setup_feed.py:236-239`:
   เรียก `_check_setup_scorer` เมื่อ timestamp แท่งล่าสุด "เปลี่ยน" (แท่ง M1 ใหม่เกิดมา 1 tick)
   → `last_close` ณ ตอนนั้นคือราคา tick แรกของแท่ง ไม่ใช่ราคาปิดจริง
   → ทิศทาง (CALL/PUT) และเงื่อนไขทั้งหมดตัดสินจากข้อมูลที่ยังเปลี่ยนได้
   อนึ่ง: `_resample()` รวมแท่ง M1→M5 ด้วย first/max/min/last ของแท่ง "กำลังก่อตัว" เช่นกัน

3. **ขาด Trend Momentum gate** — ไม่มี session filter (Asian quiet), ไม่มี ATR floor
   (ตลาด range แคบ = สัญญาณ reversion หลอกง่าย), checklist 11 ข้อเป็นบวก/ลบล้วน

4. **ประเมิน 8 symbols ด้วยเกณฑ์เดียว** — `setup_config.json` ต่อเครื่องเดียว

### แผนแก้ที่เสนอ (รอผู้ใช้อนุมัติ — แก้บน branch ใหม่ ห้าม main ตรง ๆ)

- **C1 (เกต Tier 1)** ใน `setup_scorer.py` ช่วง TIER DETERMINATION:
  - ค่าเริ่มเสนอ: `importance1` จะ FIRE ต่อเมื่อ `passed_count >= 5/11` **และ** `adx_val >= 20`
    **และ** `touch_case in {"BREAKOUT", "WICK_BOUNCE"}` (TICK_TOUCH = เก็บเป็น research เฉย ๆ
    เพราะคือแท่งที่ยังไม่ปิด)
  - ถ้าไม่ผ่านเกต → บันทึก setup_scores เหมือนเดิม แต่ tier="WAIT" + note เหตุผล
  - ตั้งค่าทุกเกตผ่าน `setup_config.json` (`tier1_min_conditions`, `tier1_min_adx`,
    `tier1_allowed_touch_cases`) — ปรับได้ไม่ต้องแก้โค้ด
- **C2 (กัน repaint)** ใน `setup_feed.py`:
  - ประเมิน checklist **เฉพาะเมื่อแท่งล่าสุดปิดแล้ว**: ใช้แท่งก่อนหน้า (iloc[-2]) เป็นข้อมูลตัดสิน
    หรือ delay การประเมิน M5 ไปที่ท้ายแท่ง (เริ่มแท่งใหม่ = แท่งเก่าปิดแล้ว — ประเมินด้วย
    `self.buffer.iloc[:-1]` ที่ resample แล้ว)
  - จุดเสี่ยง: `_resample` ใช้แท่งก่อตัว → ต้องกรองแท่งกำลังก่อตัวออกก่อนคำนวณ EMA/ATR ทั้งชุด
- **C3 (Momentum gate)** ใน `setup_scorer.py`:
  - เพิ่มเงื่อนไขข้อ 12 (ไม่ขยาย max_score ยัง): ATR% ≥ floor (เช่น 0.05% M5) + session filter
    (ปิดช่วง Asian quiet 0:00-2:00 UTC หรือทำ per-session weight)
  - ใช้ข้อมูล `tick_touch_log` (5,038 rows) + `setup_scores` ตรวจย้อนหลังว่าเกตไหนยก winrate
    จริงก่อนเปิดใช้ (มีสคริปต์แนวเดียวกันใน `scripts/data_tools/backfill_ema200.py` เป็นตัวอย่าง)
- **C4 (วัดผล A/B)**: หลังเปิดเกต ให้ดู winrate ใน setup_signals รายสัปดาห์ + daily_stats เทียบ
  baseline 49.0% — เป้าหมาย ≥ 55% ก่อนพิจารณาขยายสัญญาณ

### ข้อควรระวัง
- **ห้ามแตะ** `executor/`, สูตร R:R, CFD paper-trade (db.CFD_*) — อยู่นอกขอบเขตที่ผู้ใช้อนุมัติ
- `_ema200_touch检测` + `classify_ema200_touch` เป็นฟังก์ชันกลางที่ tick-touch research ใช้ร่วม —
  อย่าเปลี่ยน semantics ของมัน ให้เปลี่ยนเฉพาะตัวตัดสิน "จะ FIRE หรือไม่" ใน score_setup
- tests/test_setup_scorer.py มี characterization เดิม — เพิ่มเคสใหม่ อย่าแก้เคสเดิมโดยไม่ถาม


---

## งาน D — อัปเกรด VPS เป็น 2 GB RAM / 55 GB SSD (แผนเชิงปฏิบัติ)

### ข้อเท็จจริงจาก audit (2026-10-31)
- RAM: used 708/955 MB + swap 841/2,399 MB ค้างถาวร · kswapd สะสม CPU 150 นาที/89 วัน
- OOM จริง 2 ครั้ง/14 วัน (memcg limit 700M ใน docker-compose.yml:38) → container restart
  → สัญญาณหายช่วง restart
- uvicorn กิน 294-299 MB และ "โตช้า ๆ" — สงสัย memory leak ใน API endpoint กราฟ/ตาราง
  (ดึง prices 400k rows) — ตรวจเพิ่มก่อน upgrade: เปิด dashboard แล้ววัด RSS uvicorn
  ทุก 10 นาที (`docker stats`)

### ขั้นตอนอัปเกรด (Vultr Regular Cloud Compute)
1. **Backup ก่อน shutdown เสมอ**: รัน backup.py ใน container (ส่ง zip เข้า Telegram) หรือ
   `sqlite3 data/bot.db ".backup ..."` + zip models → เก็บ 2 สำเนา (VPS + เครื่อง local)
2. Vultr → Server → Resize: ปิดเครื่อง → เลือก plan ใหม่ (2GB/55GB) → บูต
   (⚠️ Vultr resize disk **ขยายได้อย่างเดียว ลดย้อนไม่ได้** — ตัดสินใจแล้วอย่าถอย)
3. บูตแล้ว: เช็ค `df -h` (vda2 ต้องโตเป็น ~54G — ถ้าไม่โต → `sudo growpart /dev/vda 2`
   + `sudo resize2fs /dev/vda2`)
4. **คืน limit ให้เหมาะสม**: แก้ `docker-compose.yml` `memory: 700M` → `1536M` (2GB RAM)
   + เพิ่ม swap OS เป็น 4G แล้ว `docker compose up -d`
5. **หลัง upgrade**: `docker stats` จับ RSS uvicorn 1 สัปดาห์ — ถ้ายังโตไม่หยุด = memory leak
   ใน API ต้องหาต่อ (uvicorn เคยทะลุ 466MB เมื่อ 27 ต.ค. ก่อนโดน OOM)
6. **ขยาย retention ข้อมูล**: `MAX_PRICE_ROWS = 50_000` (db/connection.py:23) เป็นเพดานต่อ
   symbol — ดิสก์ 55GB รับได้ถึง ~300k/symbol แต่จับตา DB growth ทุกสัปดาห์
   + เสนอเพิ่ม cron prune `setup_scores` > 7-14 วัน (แนวทางเดียวกับงาน A)
7. **แผนสำรองถ้ายังหน่วง**: ปัญหาเหลือที่ (a) 1 vCPU ต่อ setup_feed poll 8 symbols/15s +
   (b) dashboard query หนัก → ต่อคือ cache layer หรือ setup_feed ย่อเหลือ 4-5 symbols หลัก

### จุดเสี่ยง / ที่ต้องถามก่อน
- ปิด container ช่วง resize = สัญญาณ/ประเมินผลหยุด ~10-30 นาที — เลือกช่วงตลาดปิด
  (เสาร์-อาทิตย์ หรือก่อนตลาดเปิด Monday 22:00 UTC)
- แก้ docker-compose.yml = เปลี่ยน deploy pipeline → **ต้องถามผู้ใช้ก่อน** (กฎ AGENTS)
- VPS กำลัง detached HEAD บน tag — upgrade ไม่กระทบ git แต่หลัง resize ควร
  `docker compose up -d --build` ซ้ำ 1 ครั้งเพื่อยืนยัน build ยังผ่าน

---

## เช็คลิสต์เริ่มงาน session ใหม่
1. อ่าน `WORKLOG.md` entry 2026-10-31 (audit + A/B ปิดแล้ว)
2. เช็ค VPS: `docker logs xauusd-bot` หา error ใหม่ + ยืนยัน auto_retrain รอบแรกหลัง deploy
   สำเร็จ (mtime model_m5.joblib ต้องใหม่ + Telegram [AUTO-RETRAIN])
3. งาน C: นำเสนอแผน C1-C4 ให้ผู้ใช้อนุมัติ → ทำบน branch `feature/tier1-gate`
4. งาน D: ยืนยันแพลน Vultr กับผู้ใช้ก่อน resize (ถามเสมอ — เปลี่ยน pipeline/infra)
