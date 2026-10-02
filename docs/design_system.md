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
  --dim:         #4C5566;   /* ข้อความเสริม, ขอบเขตที่ไม่ได้โฟกัส */

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

  /* Typography */
  --font-display:'Archivo', -apple-system, sans-serif;
  --font-body:   'IBM Plex Sans', -apple-system, sans-serif;
  --font-mono:   'IBM Plex Mono', 'SF Mono', monospace;

  /* Elevation */
  --shadow-sm:   0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-panel:0 2px 8px rgba(0, 0, 0, 0.4);
}
```

---

## 3. โครงสร้าง Navigation & การจัดกลุ่มเมนู

ปรับโครงสร้าง Sidebar ให้แบ่งเป็น 2 กลุ่มชัดเจน ระหว่าง **Real-time Monitoring** กับ **Historical & Analytical Reports**:

```
[ TOPBAR: Brand Mark | Symbol Box | Live Price (+Chg%) | Engine Health | Latency | Clock UTC ]
─────────────────────────────────────────────────────────────────────────────────────────────
[ SIDEBAR ]                     [ MAIN CONTENT AREA ]
▼ มอนิเตอร์สด (Live Monitor)
  ├── 1. ภาพรวม (Dashboard)       ──> ชาร์ตหลัก Multi-TF, Watchlist, Prob Gauges, Quick Status
  ├── 2. ศูนย์สัญญาณ (Signal Center)─> ML Prob Signals & Rule-Based 11-Checklist & Confluence
▼ วิเคราะห์ & บันทึก (Reports)
  ├── 3. บริหารความเสี่ยง (Risk/Monitor) ─> Equity Curve, CFD Paper Trade, Drawdown, Journal P&L
  └── 4. ประวัติ & แจ้งเตือน (Log/Alert)  ─> Tick-Touch Research, Trade Logs, System Audit
─────────────────────────────────────────────────────────────────────────────────────────────
[ STATUSBAR: DB WAL Status | Market Session (London/NY) | WebSocket Feed | Bot Runtime ]
```

> **หมายเหตุ vs โค้ดปัจจุบัน:** sidebar เดิมมี 5 แท็บ (`overview / ml / setup / journal / cfd`)
> ข้อเสนอใหม่รวม `ml + setup` → **Signal Center** และ `journal + cfd` → **Risk/Monitor**
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
| Gauge | `features/gauges/` | ค่า prob 0-1 ใช้สีตามเกณฑ์เดียวกันทุกหน้า: ≥0.6 bull, 0.4–0.6 warn, <0.4 muted |

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
│ ▼รายงาน   │  └─────────────────────┘ │        legend: O H L C + Δ         │ │
│  ความเสี่ยง│  ┌ PROB GAUGES ────────┐ └────────────────────────────────────┘ │
│  ประวัติ  │  │ ML  ██████░░ 0.62   │ ┌ MINI SETUP ────────────────────────┐ │
│           │  │ RB  ████░░░░ 0.45   │ │ 11-Checklist: 7/11 ผ่าน · Confluence│ │
│           │  └─────────────────────┘ └────────────────────────────────────┘ │
│           ├─────────────────────────────────────────────────────────────────┤
│           │ ML Winrate 61% · ML Margin +2.4 · RB Winrate 58% · Models M1/M5 │
│           ├───────────────────────────┬─────────────────────────────────────┤
│           │ EQUITY CURVE (chart)      │ สัญญาณล่าสุด (feed, scroll)          │
├───────────┴───────────────────────────┴─────────────────────────────────────┤
│ STATUSBAR: WAL ok · London ▸ active · WS ✓ · runtime 4h 12m                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- สีเดียวที่อนุญาตในหน้านี้: bull/bear บนราคา+Δ, accent บน gauge เกณฑ์ผ่าน, warn บน "รอสัญญาณ"
- `Model M1/M5` ที่เดิมใช้สีม่วง (`--purple`) → เปลี่ยนเป็น `--muted`/`--accent` (ตัดสีชมพู/ม่วงรุ้ง)

### 5.2 ศูนย์สัญญาณ (Signal Center) — รวมเดิม tab `ml` + `setup`

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● ML Signals ] [ Rule-Based 11-Checklist ]   ← sub-tabs       │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  ●สัญญาณ  │ ┌ ML SIGNALS (sub-tab 1) ───────────────────────────────────────┐ │
│ ▼รายงาน   │ │ ช่องกรอง: [ทั้งหมด|BUY|SELL|รอ]  [ช่วงเวลา ▾]                   │ │
│  ความเสี่ยง│ │ ┌──────┬──────┬───────┬────────┬────────┬──────┬─────────────┐ │ │
│  ประวัติ  │ │ │เวลา  │ราคา  │ทิศทาง │Prob(ML)│Checklist│R:R   │สถานะ/ผล     │ │ │
│           │ │ └──────┴──────┴───────┴────────┴────────┴──────┴─────────────┘ │ │
│           │ │ ทิศทาง BUY = badge bull / SELL = badge bear / รอ = warn        │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ RULE-BASED (sub-tab 2) ───────────────────────────────────────┐ │
│           │ │ 11-Checklist card: แต่ละข้อ = pass(bull)/fail(bear)/skip(warn) │ │
│           │ │ + Confluence สรุป + Tick-Touch Research (ตาราง)                │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- ตารางสัญญาณ: คอลัมน์ตัวเลขทั้งหมด mono, จัดชดขวา, เรียงใหม่ล่าสุดบนสุด
- ห้ามใช้สีม่วง ML แยกอีก — ML กับ RB ใช้ semantic ชุดเดียวกัน (แยกด้วย sub-tab ไม่ใช่สี)

### 5.3 บริหารความเสี่ยง (Risk/Monitor) — รวมเดิม tab `journal` + `cfd`

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● Equity & P&L ] [ CFD Paper Trade ] [ Backtest ]  ← sub-tabs │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  สัญญาณ   │ KPI strip (mono ตัวเลขใหญ่):                                    │
│ ▼รายงาน   │   Equity Δ  +1,240 · Drawdown 4.2% (bear) · Winrate 61% (bull)  │
│  ●ความเสี่ยง├─────────────────────────────────────────────────────────────────┤
│  ประวัติ  │ ┌ EQUITY CURVE ─────────────────────────────────────────────────┐ │
│           │ │        (เส้นเดียว --bull ตอนขาขึ้น, --bear ตอนวิ่งลง)           │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ TRADE LOG ───────────────────────────────────┬─ JOURNAL P&L ──┐ │
│           │ │ เวลา | ทิศ | entry/TP/SL | R:R | ผล(Δ$)      │ รายวัน/รายสัปดาห์│ │
│           │ └──────────────────────────────────────────────┴────────────────┘ │
│           │ ┌ CFD PAPER TRADE (sub-tab 2) · เปิด/ปิด position ตามสัญญาณจริง    │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- ตัวเลขกำไร = `--bull`, ขาดทุน = `--bear`, ศูนย์/ยังไม่ปิด = `--muted` — ไม่มีสีอื่น
- Journal + CFD รวมหน้าเดียว ตัดการซ้ำซ้อนของ equity chart (แสดงที่เดียว แชร์ `shared/lib/equityData.js`)

### 5.4 ประวัติ & แจ้งเตือน (Log/Alert) — tab ใหม่ รวม notifications + tick-touch + audit

```
┌ TOPBAR ─────────────────────────────────────────────────────────────────────┐
├───────────┬─────────────────────────────────────────────────────────────────┤
│ SIDEBAR   │ [ ● Alerts ] [ Tick-Touch Research ] [ System Log ]  ← sub-tabs │
│  ภาพรวม   ├─────────────────────────────────────────────────────────────────┤
│  สัญญาณ   │ ┌ ALERTS ───────────────────────────────────────────────────────┐ │
│ ▼รายงาน   │ │ 🔔→(ไอคอน tabler) เวลา | ช่องทาง (TG/Dash) | ประเภท | ข้อความ   │ │
│  ความเสี่ยง│ │ สถานะส่ง: สำเร็จ(bull) / ล้มเหลว(bear) / retry(warn)            │ │
│  ●ประวัติ  │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ TICK-TOUCH RESEARCH ──────────────────────────────────────────┐ │
│           │ │ ตาราง event ที่ราคาแตะ zone (mono, timestamp UTC)              │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
│           │ ┌ SYSTEM LOG ───────────────────────────────────────────────────┐ │
│           │ │ runtime/DB/feed events — ข้อความ muted, error = bear          │ │
│           │ └───────────────────────────────────────────────────────────────┘ │
└───────────┴──────────────────────────────────────────────────────────────────┘
```

- หน้านี้เป็น "ห้องเครื่อง" — ไม่มีสัญญาณเทรดปน ข้อมูลทั้งหมดจาก `/api/*` ที่มีอยู่แล้ว (ไม่แตะ API shape)

---

## 6. การทำ mapping สี → ความหมาย (ใช้ตรวจทุกหน้าก่อน merge)

| ความหมาย | Token | ที่เจอได้ |
|---|---|---|
| ขาขึ้น/ซื้อ/กำไร/ผ่าน/สำเร็จ | `--bull` + `--bull-dim` | ราคา ▲, BUY badge, TP hit, alert สำเร็จ |
| ขาลง/ขาย/ขาดทุน/ไม่ผ่าน/ล้มเหลว | `--bear` + `--bear-dim` | ราคา ▼, SELL badge, SL hit, error |
| รอ/ก้ำกึ่ง/คำเตือน/neutral | `--warn` + `--warn-dim` | "รอสัญญาณ", prob กลาง, retry |
| interactive/selected/CTA | `--accent` | active nav, sub-tab ปัจจุบัน, ปุ่มหลัก |
| ✂️ ตัดออก | `--purple`, `--cyan`, สีม่วง ML | เดิมใช้แยก ML — จะแทนด้วย muted/accent |

## 7. แผน Implement (ทำหลังผู้ใช้ยืนยัน wireframe เท่านั้น)

| ลำดับ | งาน | ขอบเขต |
|---|---|---|
| C-1 | อัปเดต `styles/tokens.css` → token set ใหม่ (Section 2) + ลบ purple/cyan | CSS เท่านั้น |
| C-2 | Sidebar ใหม่ (4 รายการ/2 กลุ่ม) + sub-tab logic ใน `app/` | ไม่แตะ feature module ภายใน |
| C-3 | Dashboard (5.1) — จัด layout, แทน emoji, ใส่ accent-bar | `features/overview, chart, gauges, watchlist` |
| C-4 | Signal Center (5.2) — รวม `ml-signals + setup-signals` ลง container เดียว | แค่ layout wrapper |
| C-5 | Risk/Monitor (5.3) — รวม `journal + cfd` + KPI strip | แค่ layout wrapper |
| C-6 | Log/Alert (5.4) — หน้าใหม่จาก `notifications + tick-touch` ที่มีอยู่ | ไม่เพิ่ม endpoint |
| C-7 | npm run check + test:visual + rebuild dist → commit | บังคับทุกขั้น |

**Approval gate:** ยังไม่แก้ไฟล์ใน `frontend/src/**` จนกว่าผู้ใช้กดยืนยัน wireframe 5.1–5.4 แต่ละหน้า (ยืนยันทีละหน้าหรือทั้งชุดก็ได้)

