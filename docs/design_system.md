# XAUUSD Trading Terminal — Design System & Wireframes (Phase C)

> เอกสารแม่แบบสำหรับงาน UX/UI Redesign ของระบบเทรด XAUUSD  
> ยึดหลัก **"Information First & Meaningful Color"** (สไตล์ Pro Trading Terminal เช่น Bloomberg / TradingView Pro)  
> *ก่อนลงมือแก้โค้ด UI จริง ต้องได้รับการตรวจทานและยืนยัน wireframe จากผู้ใช้ก่อนเสมอ*

---

## 1. Design Principles (หลักการออกแบบ)

1. **Information Density & Contrast**
   - แสดงข้อมูลที่สำคัญต่อการตัดสินใจเทรดได้อย่างรวดเร็ว โดยไม่รกตา (Clean High-Density)
   - ใช้พื้นหลังโทนเข้มลึก (Dark Slate/Onyx) เพื่อลดความเมื่อยล้าของสายตาเมื่อต้องเฝ้าจอนาน
2. **Color = Semantic Meaning (ไม่ใช่ของตกแต่งสุ่ม)**
   - ตัดการใช้สีรุ้ง/นีออน 6 สีแบบสุ่ม หรือ glow/shadow ฟุ้งที่เลียนแบบ AI dashboard
   - ทุกสีมีหน้าที่และนิยามตายตัว 4 แกน:
     - 🟢 **Bull (`--bull`)**: เฉพาะ ขาขึ้น / ซื้อ / กำไร / TP / ผ่าน
     - 🔴 **Bear (`--bear`)**: เฉพาะ ขาลง / ขาย / ขาดทุน / SL / ไม่ผ่าน
     - 🟡 **Warn (`--warn`)**: เฉพาะ รอดำเนินการ / สถานะก้ำกึ่ง / Neutral / ข้อควรระวัง
     - 🔵 **Accent (`--accent`)**: ปฏิสัมพันธ์หลัก (Active tabs, ปุ่ม Call-to-action, Selected state)
3. **Typography for Tabular Data**
   - ตัวเลข, ราคา, เวลา, ค่า P&L ใช้ **IBM Plex Mono** (Tabular lining figures) คอลัมน์ตรงกันเสมอ ไม่อ่านเบี้ยว
   - ข้อความเนื้อหา/ตาราง/ฟอร์ม ใช้ **IBM Plex Sans**
   - ส่วนหัว (Header/Brand) ใช้ **Archivo** (น้ำหนัก 600-700) ให้ความรู้สึกมั่นคง น่าเชื่อถือแบบสถาบันการเงิน
4. **Emoji Removal & Professional Iconography**
   - ปลด emoji ในหัวข้อและตารางออกทั้งหมด (เช่น 📈, 📊, 🤖, 🔬, 🟢)
   - ใช้ `.accent-bar` นำหน้าหัวข้อ panel และใช้ Tabler Icons (`ti ti-*`) ขนาด 14–16px แทน เมื่อจำเป็นต้องมีสัญลักษณ์ประกอบ
5. **Color Never Carries Meaning Alone (กันสีตาบร่วม/ตามองข้ามจอ)**
   - สี `--bull`/`--bear` ทุกจุดต้องมีตัวบอกความหมายคู่เสมอ: เครื่องหมาย **+/−**, **▲/▼** หรือไอคอน tabler
     (เช่น BUY ▲ เขียว, SELL ▼ แดง, +1,240 ตัวเลขเขียว, −4.2% ตัวเลขแดง)
   - ห้ามใช้เฉพาะ "สีเขียว = ผ่าน" ลอย ๆ โดยไม่มีข้อความหรือสัญลักษณ์กำกับ

---

## 2. Design Tokens (ตารางค่าสีและสไตล์)

```css
:root {
  /* Surface & Backgrounds */
  --bg:          #0A0C10;   /* พื้นหลังแอปหลัก ดำลึก สบายตา */
  --surface:     #12151C;   /* พื้นหลัง Panel, Sidebar, Topbar */
  --surface-alt: #171B24;   /* พื้นหลัง Card ย่อย, Hover state, Input box */
  --border:      #232732;   /* เส้นขอบมาตรฐาน คมชัดบางเบา */
  --border-subtle:#1A1D27;  /* เส้นแบ่งภายในตาราง */

  /* Text & Labels */
  --text:        #EDEFF3;   /* ข้อความหลัก ชัดเจน */
  --muted:       #838B9C;   /* Label, หัวตาราง, คำอธิบายรอง */
  --dim:         #4C5566;   /* เฉพาะเส้น/ขอบ/ตกแต่ง — คอนทราสต์ 2.6:1 ห้ามใช้กับข้อความ */

  /* Semantic State Colors */
  --bull:        #16C784;   /* BUY / CALL / Profit / Active OK */
  --bear:        #F0465C;   /* SELL / PUT / Loss / Stop Loss */
  --warn:        #E8A33D;   /* Wait / Neutral / Moderate Confidence */
  --accent:      #4C8DFF;   /* Brand / Active State / Interactive Focus */

  /* Translucent Badges / Highlights */
  --bull-dim:    rgba(22, 199, 132, 0.12);
  --bear-dim:    rgba(240, 70, 92, 0.12);
  --warn-dim:    rgba(232, 163, 61, 0.12);
  --accent-dim:  rgba(76, 141, 255, 0.12);

  /* Typography — body ต้องมองเห็นอักษรไทยจริง: IBM Plex Sans Thai (self-host ใน frontend/src/vendor/fonts/)
     Archivo/Plex Sans (เวอร์ชันละติน) ใช้ได้เฉพาะข้อความอังกฤษ/ตัวเลขเท่านั้น ห้ามใช้รับข้อความไทย */
  --font-display:'Archivo', -apple-system, sans-serif;   /* จำกัดเฉพาะ brand/ตัวเลขหัว topbar */
  --font-body:   'IBM Plex Sans Thai', 'IBM Plex Sans', -apple-system, sans-serif;
  --font-mono:   'IBM Plex Mono', 'SF Mono', monospace;
```

> **การโหลดฟอนต์ (self-host):** ดาวน์โหลด `.woff2` ของ IBM Plex Sans Thai + IBM Plex Mono + Archivo
> ไว้ที่ `frontend/src/vendor/fonts/` + `@font-face` ใน `styles/global.css` — **ห้ามใช้ Google Fonts CDN**
> (หน้าเทรดต้องทำงานได้แม้ VPS/เครือข่ายบล็อก third-party; และลด latency การโหลดหน้า)

> **กฎการใช้ `--dim`:** คอนทราสต์กับ `--bg` ≈ 2.6:1 → **ต่ำกว่า WCAG AA (4.5:1)**
> ใช้ได้เฉพาะ **เส้น/ขอบ/สัญลักษณ์ตกแต่ง/track ของ gauge** เท่านั้น — **ห้ามใช้กับข้อความทุกชนิด**
> ข้อความระดับรองให้ใช้ `--muted` (≥ 4.5:1) แทนเสมอ

  /* Elevation */
  --shadow-sm:   0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-panel:0 2px 8px rgba(0, 0, 0, 0.4);
}
```

---

## 3. โครงสร้าง Navigation & การจัดกลุ่มเมนู

ปรับโครงสร้าง Sidebar ให้แบ่งเป็น 2 กลุ่มชัดเจน ระหว่าง **Real-time Monitoring** กับ **Historical & Analytical Reports**:

```
[ TOPBAR: Brand Mark | Symbol Box | Live Price (+Chg%) | Mode LIVE/PHANTOM | Engine Health | Clock UTC ]
─────────────────────────────────────────────────────────────────────────────────────────────
[ SIDEBAR ]                     [ MAIN CONTENT AREA ]
▼ มอนิเตอร์สด (Live Monitor)
  ├── 1. ภาพรวม (Dashboard)       ──> ชาร์ตหลัก Multi-TF, Watchlist, Prob Gauges, Quick Status
  ├── 2. ศูนย์สัญญาณ (Signal Center)─> ML Prob Signals & Rule-Based 11-Checklist & Confluence
▼ ผลงาน & บันทึก (Performance & Records)
  ├── 3. ผลงาน & บันทึก (Performance) ─> Equity Curve, CFD Paper Trade, Journal P&L
  └── 4. ประวัติ & แจ้งเตือน (Log/Alert)  ─> Tick-Touch Research, Trade Logs
─────────────────────────────────────────────────────────────────────────────────────────────
[ STATUSBAR: Data Age / Stale indicator | Market Session (London/NY) | Bot Runtime ]
```

> **ข้อแก้ตามข้อมูลจริง:** ระบบเดิมรับข้อมูลด้วย **HTTP polling ทุก 5 วิ (`app/refreshLoop.js` REFRESH_MS=5000)
> ไม่มี WebSocket** — ส่วน "Latency/WAL" ยังไม่มี endpoint จริง จึงตัดออกจาก topbar/statusbar
> (ย้ายไป "ข้อเสนอ backend" ดู Section 7) — ใช้ **Data Age (ตัวบอกข้อมูลเก่า)** แทน: จับเวลานับจาก response
> ล่าสุดของ polling เอง ถ้าเกิน 2× REFRESH_MS → แสดง badge "ข้อมูลค้าง" สี warn พร้อมเวลา (มีข้อมูลจริงฝั่ง client)

> **หมายเหตุ vs โค้ดปัจจุบัน:** sidebar เดิมมี 5 แท็บ (`overview / ml / setup / journal / cfd`)
> ข้อเสนอใหม่รวม `ml + setup` → **Signal Center** และ `journal + cfd` → **ผลงาน & บันทึก (Performance)**
> โดยเก็บ feature module เดิม (`src/features/*`) ไว้ทั้งหมด เปลี่ยนแค่ layout ของ tab container

---

## 4. Component Inventory (ชิ้นส่วนที่ใช้ร่วมกันทุกหน้า)

| Component | ที่มาในโค้ดปัจจุบัน | มาตรฐานใหม่ |
|---|---|---|
| Panel + `.accent-bar` heading | `shared/ui/cards.css` | หัว panel ใช้แถบสี `--accent` นำหน้า ห้ามใช้ emoji |
| Data Table | `shared/ui/tables.css` | ตัวเลขใช้ `--font-mono`, หัวตาราง `--muted` uppercase 11px, เส้นแบ่ง `--border-subtle` |
| Status Badge | (ยังไม่มีมาตรฐาน) | Badge 4 สี semantic เท่านั้น: `bull-dim / bear-dim / warn-dim / accent-dim` |
| Topbar | `features/status-bar/topbar.html` | Brand | Symbol+Price(mono) | Health dot | Session | Clock UTC | Logout |
| Sidebar | `app/sidebar.html` | 2 กลุ่ม (Live / Reports), Active = `--accent` แถบซ้าย |
| Statusbar | `features/status-bar/statusbar.html` | ข้อมูลระบบ runtime เท่านั้น ไม่ใส่สัญญาณเทรด |
| Toast / Alert | `shared/ui/toast.js` | bull = สำเร็จ, bear = error, warn = คำเตือน |
| Empty State | เช่น `eq-empty` ใน overview | ข้อความ `--muted` บรรยายสั้น + ไอคอน tabler (ถ้าจำเป็น) |
| Gauge | `features/gauges/` | **Gauge ความมั่นใจ (prob 0–1) ใช้ `--accent` เสมอ ไม่ใช้ bull/bear** — ทิศทาง BUY/SELL แสดงด้วย badge แยกต่างหาก (bull/bear + ▲▼) เพราะ "มั่นใจสูง" ≠ "ขาขึ้น" |

---

## 5. Wireframe ทีละหน้า

### 5.1 ภาพรวม (Dashboard) — tab `overview`

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
│ X XAUUSD PRO · frxXAUUSD 2,412.35 ▲+0.12% · ● LIVE · M1 ✓ M5 ✓ · 09:14 UTC │
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │  ┌ WATCHLIST ──────────┐ ┌ CHART MULTI-TF ────────────────────┐ │
│ ▼สด       │  │ XAUUSD  2,412.35 ▲  │ │ [M1 M5 M15 H1 H4] [Indicators ▾]   │ │
│  ●ภาพรวม  │  │ EURUSD  1.0850  ▼   │ │                                    │ │
│   สัญญาณ  │  │ GBPJPY  195.20  ▲   │ │        (Lightweight Charts)        │ │
│ ▼ผลงาน    │  └─────────────────────┘ │        legend: O H L C + Δ         │ │
│  ผลงาน    │  ┌ PROB GAUGES (accent) ┐ └────────────────────────────────────┘ │
│  ประวัติ  │  │ ML  ██████░░ 0.62    │ ┌ MINI SETUP ────────────────────────┐ │
│           │  │ RB  ████░░░░ 0.45    │ │ 11-Checklist: 7/11 ผ่าน + badge ▲BUY│ │
│           │  │ + badge: ▲ BUY (bull)│ └────────────────────────────────────┘ │
│           │  └─────────────────────┘                                        │
│           ├─────────────────────────────────────────────────────────────────┤
│           │ ML Winrate 61% (+2.1%) · RB Winrate 58% (+0.8%) · Models M1/M5   │
│           ├───────────────────────────┬─────────────────────────────────────┤
│           │ EQUITY CURVE (เส้นเดียว    │ สัญญาณล่าสุด (feed, scroll)          │
│           │ สี accent + fill bull/bear │                                     │
│           │ แบ่งเหนือ/ใต้ฐาน)          │                                     │
├───────────┴───────────────────────────┴─────────────────────────────────────┤
│ STATUSBAR: ข้อมูลเมื่อ 3 วิ ▸ สด | London ▸ active | runtime 4h 12m            │
└──────────────────────────────────────────────────────────────────────────────┘
```

- สีเดียวที่อนุญาตในหน้านี้: bull/bear บนราคา+Δ (คู่ ▲▼ เสมอ), accent บน gauge, warn บน "รอสัญญาณ"
- `Model M1/M5` ที่เดิมใช้สีม่วง (`--purple`) → เปลี่ยนเป็น `--muted`/`--accent` (ตัดสีชมพู/ม่วงรุ้ง)
- **Gauge ความมั่นใจ = เส้นสี `--accent` เสมอ** ทิศทางแสดงด้วย badge ▲BUY/▼SELL แยกต่างหาก
- **Stale indicator:** ถ้า polling ล้มเหลว/ค้าง > 2 รอบ → badge "ข้อมูลค้าง +Ns" สี warn
  บน statusbar และหัว panel ที่กระทบ (ฝั่ง client จับเวลาจาก response ล่าสุดเอง)

**มือถือ (แบบย่อ):**
```
[Topbar: Brand | ราคา | LIVE]
[ชาร์ตเต็มกว้าง]
[แถบเลื่อนแนวนอน: Gauges | Mini Setup]
[KPI strip แนวนอนเลื่อนได้]
[Equity | Feed — ซ้อนกันแนวตั้ง]
[Statusbar ล่างสุด]
Sidebar → ปุ่ม hamburger แบบ drawer, ปิดเมื่อเลือกแท็บ
```

### 5.2 ศูนย์สัญญาณ (Signal Center) — รวมเดิม tab `ml` + `setup`

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● ML Signals ] [ Rule-Based 11-Checklist ]   ← sub-tabs       │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  ●สัญญาณ  │ ┌ ML SIGNALS (sub-tab 1) ───────────────────────────────────────┐ │
│ ▼ผลงาน    │ │ ช่องกรอง: [ทั้งหมด|BUY|SELL|รอ]  [ช่วงเวลา ▾]                   │ │
│  ผลงาน    │ │ ┌────┬─────┬────┬──────┬──────┬──────┬──────┬────┬──────────┐  │ │
│  ประวัติ  │ │ │เวลา│ราคา │ทิศ │Entry │ SL   │ TP1/2│Prob │R:R │สถานะ/ผล  │  │ │
│           │ │ └────┴─────┴────┴──────┴──────┴──────┴──────┴────┴──────────┘  │ │
│           │ │ ทิศ: "▲ BUY" badge bull / "▼ SELL" badge bear / "○ รอ" warn     │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ RULE-BASED (sub-tab 2) ───────────────────────────────────────┐ │
│           │ │ 11-Checklist card: แต่ละข้อ = ผ่าน ✓(bull)/ไม่ผ่าน ✕(bear)/รอ(warn)│ │
│           │ │ + Confluence สรุป + Tick-Touch Research (ตาราง)                │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- ตารางสัญญาณ: คอลัมน์ตัวเลขทั้งหมด mono, จัดชดขวา, เรียงใหม่ล่าสุดบนสุด
- **Entry/SL/TP จากข้อมูลจริง:** Entry มีใน `/api/signals` (`entry_price`); ชุด Entry/SL/TP1/TP2 ครบ
  ใน `/api/signals/markers` (ตารางใน DB มี `sl_price/tp1_price/tp2_price`) — ใช้ markers เป็นแหล่งข้อมูล
  ของคอลัมน์ SL/TP โดยไม่ต้องเพิ่ม endpoint ใหม่
- ห้ามใช้สีม่วง ML แยกอีก — ML กับ RB ใช้ semantic ชุดเดียวกัน (แยกด้วย sub-tab ไม่ใช่สี)
- Badge ทิศทางทุกจุดต้องมี ▲/▼/○ คู่สี (ห้ามสีอย่างเดียว)

**มือถือ (แบบย่อ):**
```
[Topbar]
[sub-tab ML | Rule-Based]
[ชิปกรอง เลื่อนแนวนอน]
[การ์ดสัญญาณรายแถว: เวลา/ทิศ badge | Entry·SL·TP | Prob | ผล]
```


### 5.3 ผลงาน & บันทึก (Performance) — รวมเดิม tab `journal` + `cfd`

> **เปลี่ยนจากชื่อเดิม "บริหารความเสี่ยง (Risk/Monitor)"** เพราะยังไม่มีข้อมูล exposure /
> daily loss limit จริง — หน้านี้แสดง "ผลที่เกิดขึ้นแล้ว" ไม่ใช่ "ควบคุมความเสี่ยงสด"

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● Equity & P&L ] [ CFD Paper Trade ] [ Backtest ]  ← sub-tabs │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  สัญญาณ   │ KPI strip (mono, คู่เครื่องหมายเสมอ):                            │
│ ▼ผลงาน    │   P&L รวม +1,240 (bull) · Winrate 61% (+2.1, bull) · จำนวนเทรด 87│
│  ●ผลงาน   ├─────────────────────────────────────────────────────────────────┤
│  ประวัติ  │ ┌ EQUITY CURVE ─────────────────────────────────────────────────┐ │
│           │ │ เส้นสีเดียว (--accent) + ระบายพื้นที่: เหนือเส้นฐาน fill --bull-dim│ │
│           │ │ (baseline = ทุนเริ่มต้น) ใต้เส้นฐาน fill --bear-dim — ห้ามเปลี่ยน │ │
│           │ │ สีเส้นตามช่วงขึ้น/ลง (เส้น 1 สี = อ่านแนวโน้มโดยรวมได้ ไม่หลอกตา) │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ TRADE LOG ───────────────────────────────────┬─ JOURNAL P&L ──┐ │
│           │ │ เวลา | ทิศ(▲/▼) | Entry/SL/TP | R:R | ผล(Δ$)  │ รายวัน/รายสัปดาห์│ │
│           │ └──────────────────────────────────────────────┴────────────────┘ │
│           │ ┌ CFD PAPER TRADE (sub-tab 2) · เปิด/ปิด position ตามสัญญาณจริง    │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- ตัวเลขกำไร = `--bull` คู่ **+**, ขาดทุน = `--bear` คู่ **−**, ศูนย์/ยังไม่ปิด = `--muted` — ไม่มีสีอื่น
- **ตัด "Drawdown % แยกสี" เดิมออกจาก KPI** (คำนวณได้จาก equity curve ให้แสดงเป็น min marker บนชาร์ตพอ)
- Journal + CFD รวมหน้าเดียว ตัดการซ้ำซ้อนของ equity chart (แสดงที่เดียว แชร์ `shared/lib/equityData.js`)
- ทุก panel มี stale badge เหมือน 5.1 เมื่อ polling ค้าง

**มือถือ (แบบย่อ):**
```
[Topbar]
[KPI strip เลื่อนแนวนอน]
[Equity chart เต็มกว้าง]
[Trade log → การ์ดรายเทรด (ไม่ใช่ตารางแนวนอน)]
[sub-tab: Equity | Paper | Backtest]
```

### 5.4 ประวัติ & แจ้งเตือน (Log/Alert) — tab รวม notifications + tick-touch

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● ประวัติสัญญาณ ] [ Tick-Touch Research ]   ← sub-tabs         │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  สัญญาณ   │ ┌ ประวัติสัญญาณ & แจ้งเตือน (sub-tab 1) ─────────────────────────┐ │
│ ▼ผลงาน    │ │ เวลา | ชนิดสัญญาณ (ML/Setup) | ทิศ(▲/▼) | ข้อความที่ส่ง          │ │
│  ผลงาน    │ │ (อ่านจากประวัติ signal ใน DB — ไม่มีสถานะส่งจริง ดู Section 7)  │ │
│  ●ประวัติ  │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ TICK-TOUCH RESEARCH (sub-tab 2) ──────────────────────────────┐ │
│           │ │ ตาราง event ที่ราคาแตะ zone (mono, เวลา UTC) จาก /api/ticktouch/stats │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- **ตัด "สถานะส่ง (สำเร็จ/ล้มเหลว/retry)" และ "System Log" ออกจาก wireframe** — backend ยิง Telegram
  แล้วเก็บผลลง stdout log เท่านั้น ไม่มีตาราง/endpoint บันทึกสถานะการส่ง และไม่มี endpoint อ่าน system log
  → ย้ายไปเป็น "ข้อเสนอ backend" (Section 7) — **ห้ามแสดงข้อมูลปลอม/หลอก**
- หน้านี้เป็น "ห้องเครื่อง" — ไม่มีสัญญาณเปิดใหม่ปน ใช้ API เดิมทั้งหมด (ไม่แตะ API shape)

**มือถือ (แบบย่อ):**
```
[Topbar]
[sub-tab ประวัติ | Tick-Touch]
[รายการแบบ card/แถว คั่นด้วยวันที่]
```

---

## 6. การทำ mapping สี → ความหมาย (ใช้ตรวจทุกหน้าก่อน merge)

| ความหมาย | Token | ที่เจอได้ |
|---|---|---|
| ขาขึ้น/ซื้อ/กำไร/ผ่าน/สำเร็จ | `--bull` + `--bull-dim` | ราคา ▲, BUY badge, TP hit, alert สำเร็จ |
| ขาลง/ขาย/ขาดทุน/ไม่ผ่าน/ล้มเหลว | `--bear` + `--bear-dim` | ราคา ▼, SELL badge, SL hit, error |
| รอ/ก้ำกึ่ง/คำเตือน/neutral | `--warn` + `--warn-dim` | "รอสัญญาณ", prob กลาง, retry |
| interactive/selected/CTA | `--accent` | active nav, sub-tab ปัจจุบัน, ปุ่มหลัก, **เส้น gauge ความมั่นใจ, เส้น equity curve** |
| ✂️ ตัดออก | `--purple`, `--cyan`, สีม่วง ML | เดิมใช้แยก ML — จะแทนด้วย muted/accent |

- **กฎบังคับทุกหน้า:** สี bull/bear ต้องมีคู่ +/−, ▲▼ หรือไอคอนเสมอ (ห้ามสีอย่างเดียว — ดูหลักการข้อ 5)
- `--dim` ห้ามใช้กับข้อความ (ใช้เฉพาะเส้น/ขอบ/ตกแต่ง — ดูหมายเหตุใน Section 2)

## 7. ตารางข้อมูลจริง: ช่องใน wireframe → endpoint ที่มีจริง (ตรวจแล้วจาก `backend/api/routes/`)

**Endpoints ที่มีอยู่จริงทั้งหมด:** `/api/symbol`, `/api/symbols`, `/api/candles`, `/api/watchlist`,
`/api/prices`, `/api/ml/signals`, `/api/ml/stats`, `/api/ml/stats/by_timeframe`, `/api/ml/latest`,
`/api/signals`, `/api/signals/markers`, `/api/ticktouch/stats`, `/api/stats`, `/api/stats/by_timeframe`,
`/api/setup/latest`, `/api/setup/latest-all`, `/api/setup/history`, `/api/journal` (+`/stats`, `/settings`,
`/report`, `/export`), `/api/models`, `/api/cfd/backtest`, `/api/cfd/paper` — **ไม่มี WebSocket, ไม่มี /health**

| ช่องใน wireframe | endpoint จริง | เช็ก |
|---|---|---|
| ราคาสด + Δ (topbar, watchlist) | `GET /api/prices` | ✅ มีจริง |
| ชาร์ต candles / multi-TF | `GET /api/candles` | ✅ |
| Gauge prob ML | `GET /api/ml/latest` | ✅ |
| 11-Checklist / mini setup | `GET /api/setup/latest`, `/api/setup/latest-all` | ✅ |
| ตาราง ML signals (+Entry) | `GET /api/ml/signals` (`entry_price` มีจริง) | ✅ |
| ตาราง Setup signals + history | `GET /api/signals`, `/api/setup/history` | ✅ |
| **คอลัมน์ SL/TP1/TP2** | `GET /api/signals/markers` (มี `sl_price/tp1_price/tp2_price`) | ✅ ใช้ endpoint นี้เสริม |
| Winrate / stats / by timeframe | `GET /api/stats`, `/api/ml/stats*` | ✅ |
| Equity curve / Journal P&L | `GET /api/journal`, `/api/journal/stats`, `/api/journal/report` | ✅ |
| CFD paper / backtest | `GET /api/cfd/paper`, `/api/cfd/backtest` | ✅ |
| Tick-Touch Research | `GET /api/ticktouch/stats` | ✅ |
| Model info (M1/M5) | `GET /api/models` | ✅ |
| Stale/Data-Age badge | คำนวณฝั่ง client จากเวลา response ล่าสุดของ polling (ไม่ต้อง endpoint) | ✅ client-side |
| Live/Phantom mode badge (topbar) | **❌ ไม่มี endpoint บอกโหมด** | ⛔ → ข้อเสนอ backend |
| Latency (topbar เดิม) | **❌ ไม่มี** | ⛔ ตัดออก → ข้อเสนอ backend |
| WAL status (statusbar เดิม) | **❌ ไม่มี** | ⛔ ตัดออก → ข้อเสนอ backend |
| Bot runtime (statusbar) | **❌ ไม่มี** | ⛔ ตัดออก → ข้อเสนอ backend |
| WebSocket Feed | **❌ ไม่มี WS — ระบบใช้ polling 5 วิ** | ⛔ ตัดออก ใช้ Data-Age แทน |
| สถานะส่ง Telegram (สำเร็จ/ล้มเหลว/retry) | **❌ ไม่มี — notifier พิมพ์ผลลง stdout เท่านั้น** | ⛔ → ข้อเสนอ backend |
| System Log viewer | **❌ ไม่มี endpoint อ่าน log** | ⛔ → ข้อเสนอ backend |
| Market session (London/NY) | คำนวณฝั่ง client จากเวลา UTC ปัจจุบัน (มีอยู่แล้วใน `headerStatus.js`) | ✅ client-side |

> **ห้ามใส่ข้อมูลปลอม:** ช่องไหนตารางระบุ ⛔ ต้องไม่ปรากฏใน UI จนกว่าจะมี endpoint จริง

### ข้อเสนอ backend (ไม่ทำใน Phase C — ต้องขออนุมัติแยก เพราะแตะ API shape ข้อ 5 ของกฎเหล็ก)

1. `GET /api/health` — รวม uptime, engine mode (live/phantom), WAL status, feed latency ล่าสุด
2. ตาราง `notification_log` (signal_id, channel, ok, ts) + `GET /api/notifications` — เพื่อแสดงสถานะส่งจริง
3. `GET /api/system_log?tail=N` — อ่าน log ล่าสุด (ต้องกัน auth + size limit)

## 8. แผน Implement (ทำหลังผู้ใช้ยืนยันรอบสองเท่านั้น — ทีละก้อน, commit ทีละก้อน)

| ลำดับ | งาน | ขอบเขต | ตรวจ |
|---|---|---|---|
| C-1 | ฟอนต์ self-host: `vendor/fonts/*.woff2` + `@font-face` + tokens (body = Plex Sans Thai) + `--dim` ใช้เฉพาะเส้น | `styles/`, `vendor/` | pytest + build |
| C-2 | Sidebar ใหม่ (4 รายการ/2 กลุ่ม) + sub-tab logic + stale badge — badge โหมด LIVE/PHANTOM ทำเฉพาะเมื่อมีแหล่งข้อมูลจริง (Section 7 ⛔ → รอ /api/health จึงใส่) | `app/`, `status-bar/` | ลงหน้าจริง |
| C-3 | Dashboard (5.1) — gauge = accent + badge ทิศทางแยก, ตัด emoji/m่วง, equity เส้นเดียว+fill | `overview, chart, gauges, watchlist` | screenshot เทียบ |
| C-4 | Signal Center (5.2) — รวม `ml+setup`, ตารางเพิ่ม Entry/SL/TP (จาก markers), badge ▲▼ | `ml-signals, setup-signals` | screenshot เทียบ |
| C-5 | ผลงาน & บันทึก (5.3) — รวม `journal+cfd`, KPI คู่ +/-, equity fill เหนือ/ใต้ฐาน | `journal, cfd` | screenshot เทียบ |
| C-6 | ประวัติ & แจ้งเตือน (5.4) — รวม notifications + tick-touch (ไม่มีสถานะส่ง/ไม่มี system log) | `notifications, setup-signals` | screenshot เทียบ |
| C-7 | Responsive + mobile drawer ทั้ง 4 หน้า (ตาม wireframe มือถือ) | `styles/responsive.css` | test:visual |
| C-8 | Refresh เฉพาะแท็บ/sub-tab ที่เปิดดู + หยุดเมื่อแท็บเบราว์เซอร์ไม่ active (`document.hidden`) | `app/refreshLoop.js` | รูปแบบข้อมูล/ช่วง refresh ที่ได้ต้องเหมือนเดิมเมื่อหน้า active |
| C-9 | npm run check + test:visual + rebuild dist → commit ทีละก้อนตลอด | — | บังคับทุกขั้น |

**เงื่อนไขที่ยังมีผล:** ห้าม push main · ห้ามแตะ `executor/` · ห้ามแก้ API shape ·
pytest + เทียบ screenshot ทุกก้อน · ทำทีละก้อน commit ทีละก้อน

**Approval gate:** ยังไม่แก้ `frontend/src/**` จนกว่าผู้ใช้จะยืนยันเอกสารฉบับแก้นี้ (รอบสอง)

