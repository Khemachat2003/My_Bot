# XAUUSD Terminal — Redesign Brief (แนบพร้อม trading-terminal-style-reference.html)

## สำคัญที่สุด: วิธีใช้เอกสารนี้
`index.html` ปัจจุบันมี JS ผูกกับ element ID เฉพาะเจาะจงทั่วทั้งไฟล์ (2,700+ บรรทัด, `fetchJSON`, `render*` functions หลายสิบตัว) **ห้ามเขียนไฟล์ใหม่ทั้งหมด** ให้แก้แบบ:
1. แทนที่ค่าใน `:root{...}` (บรรทัด ~10-18) ด้วยชุดตัวแปรใหม่ด้านล่าง
2. ไล่ grep หา selector ที่อ้างสีเก่าโดยตรง (ไม่ผ่านตัวแปร) แล้วแก้ตามตารางแมปด้านล่าง
3. โครงสร้าง HTML/section/id ทั้งหมดคงเดิม แก้แค่ CSS + nav markup เท่าที่ระบุ
4. ทดสอบว่าทุกปุ่ม/ทุก tab ยังทำงานเหมือนเดิมหลังแก้ (เพราะ `nav-btn[data-tab=...]` ใช้ JS toggle `display:none` อยู่)

ไฟล์ `trading-terminal-style-reference.html` คือตัวอย่างภาษาออกแบบใหม่ที่ apply กับ layout จำลอง (ไม่ใช่ของจริง 2,700 บรรทัด) — เอาไว้ดู token สี/font/spacing เป็นหลัก

---

## ทำไมต้องเปลี่ยน
ของเดิมมีปัญหาที่ทำให้ดูเหมือน "AI สร้าง dashboard" มากกว่า "terminal มืออาชีพจริง":
1. **สี accent 6 สี** (cyan/green/blue/purple/yellow/red) ใช้ไล่สีแบบสุ่มตาม panel เพื่อความหลากหลาย ไม่ได้สื่อความหมายอะไรจริง — terminal จริง (Bloomberg, Eikon, TradingView Pro) ใช้สีน้อยและทุกสีมีความหมายตายตัว
2. **glow/shadow สี + gradient พื้นหลัง** ที่ logo, badge, topbar — เป็น cliché ของ dashboard ที่ AI generate ซ้ำกันมาก
3. **emoji ในหัวข้อ** (📈📊🤖⚙️🔬 ฯลฯ 12 จุด) — terminal มืออาชีพไม่ใช้ emoji เป็น label
4. **nav แถวเดียวราบ ไม่มีหมวดหมู่** — ผสมของที่ต้อง monitor สด (ภาพรวม/ML/Rule-Based) กับของที่เป็นรายงานย้อนหลัง (Journal/CFD) ไว้ระดับเดียวกันหมด ทำให้ผู้ใช้ต้องนึกเองว่าอะไรคือของสด อะไรคือรายงาน

## หลักการใหม่
สี = ความหมาย, ไม่ใช่การตกแต่ง เหลือแค่ 4 สีที่มีหน้าที่ตายตัว:
- **bull (เขียว)** = กำไร/ขึ้น/ชนะ เท่านั้น
- **bear (แดง)** = ขาดทุน/ลง/แพ้ เท่านั้น
- **warn (เหลืองอำพัน)** = รอดำเนินการ/ก้ำกึ่ง เท่านั้น
- **accent (น้ำเงิน)** = สถานะ interactive เดียว (active nav, ปุ่มหลัก, ลิงก์) ใช้แทนที่ cyan/purple/blue เดิมทั้งหมด

ห้ามใช้สี accent/warn/bull/bear ไปตกแต่ง panel header แบบสุ่มอีก — ถ้า panel ไม่มีความหมาย bull/bear/warn ให้ใช้ accent-bar เส้นเดียวสีเดียวกันทุก panel (ดูตัวอย่างใน reference file, `.accent-bar`)

---

## ตาราง mapping ตัวแปรสี (เอาไปแทนใน `:root`)

| ตัวแปรเดิม | ค่าเดิม | ตัวแปรใหม่ | ค่าใหม่ | หมายเหตุ |
|---|---|---|---|---|
| `--bg` | `#06090f` | `--bg` | `#0A0C10` | พื้นหลังหลัก ตัดพวก radial-gradient ประดับออกจาก `body` |
| `--panel`,`--panel2`,`--card` | ต่างเฉด | `--surface`,`--surface-alt` | `#12151C`,`#171B24` | รวมเหลือ 2 ระดับพอ ไม่ต้องไล่เฉด 3 ชั้น |
| `--border`,`--border2` | `#1a2440`,`#263259` | `--border` | `#232732` | เหลือค่าเดียว |
| `--text` | `#e8eefb` | `--text` | `#EDEFF3` | ใกล้เคียงเดิม |
| `--muted`,`--dim` | เดิม | `--muted`,`--dim` | `#838B9C`,`#4C5566` | คงไว้ 2 ระดับ |
| `--green` | `#22c98a` | `--bull` | `#16C784` | **แปลว่ากำไร/ขึ้นเท่านั้น** ห้ามใช้ตกแต่ง |
| `--red` | `#f6465d` | `--bear` | `#F0465C` | **แปลว่าขาดทุน/ลงเท่านั้น** |
| `--yellow` | `#f0b90b` | `--warn` | `#E8A33D` | **แปลว่ารอ/ก้ำกึ่งเท่านั้น** |
| `--blue`,`--cyan`,`--purple` | 3 สี | `--accent` | `#4C8DFF` | **รวม 3 สีเป็นสีเดียว** ใช้เฉพาะ interactive/active state |

### จุดที่ต้อง grep แล้วแก้ตาม (สีเดิมถูกอ้างตรงๆ ไม่ผ่านตัวแปร)
- `.kpi.cyan/.blue/.purple/.yellow` → รวมเป็น class เดียว ไม่ต้องมีสี per-card แบบสุ่ม เว้นแต่ card นั้นสื่อ bull/bear/warn จริง
- `.val.cyan/.blue/.purple` → เปลี่ยนเป็น `.val.bull/.bear/.warn` ตามความหมายจริงของตัวเลขนั้น ไม่ใช่เปลี่ยนชื่อเฉยๆ (ต้องดูทีละจุดว่าตัวเลขนั้นคืออะไร)
- `.panel h3 .ph.cyan/.green/.blue/.purple/.red` (สีจุดหน้า header panel) → เปลี่ยนทั้งหมดเป็น `.accent-bar` เส้นเดียวสี `--accent` แบบเดียวกันทุก panel (ดู reference)
- `.nav-btn[data-tab=...] .ndot` (จุดสีต่าง panel ต่อ tab) → เอาออก แล้วใช้การจัดกลุ่ม nav แทน (ดูหัวข้อถัดไป)
- ทุกจุดที่มี `box-shadow:0 0 Npx rgba(...)` เพื่อทำ glow → ลบทิ้งทั้งหมด เหลือแค่ `box-shadow` แบบเรียบสำหรับความลึกเบาๆ ถ้าจำเป็น (เช่น `0 1px 2px rgba(0,0,0,.3)`) ไม่ใช่ glow สี
- `radial-gradient(...)` บน `body` → ลบออก ใช้พื้นสีเรียบ `var(--bg)`
- emoji ทั้งหมดในหัวข้อ (`📈📊🤖⚙️🔬🟢📅`) → ลบออก ใช้ label ข้อความล้วน ถ้าต้องการ indicator ให้ใช้ `.accent-bar` แทน

---

## จัดหมวดหมู่ nav ใหม่ (ตอบโจทย์ "monitor ง่าย จัดหมวดหมู่ง่าย")

เปลี่ยนจาก nav แถวเดียว 5 ปุ่ม เป็น sidebar 2 กลุ่ม (โครงสร้าง section id เดิมทั้งหมดไม่ต้องเปลี่ยน แค่ครอบด้วย grouping ใหม่):

**กลุ่ม "มอนิเตอร์สด"** (ของที่ต้องดูแบบ real-time)
- ภาพรวม → `#tab-overview`
- สัญญาณ ML → `#tab-ml`
- Rule-Based → `#tab-setup`

**กลุ่ม "รายงานย้อนหลัง"** (ของที่วิเคราะห์ผลที่ผ่านมา)
- Journal / P&L → `#tab-journal`
- CFD Backtest → `#tab-cfd`

Logic การ toggle `display:none/block` ของแต่ละ section ใช้โค้ดเดิมได้เลย แค่เปลี่ยน markup ของตัว nav จากแถวปุ่มเป็น sidebar ตามโครงสร้างใน `trading-terminal-style-reference.html` (`.sidebar`, `.nav-group`, `.nav-item`) แล้ว bind `onclick` เดิมเข้ากับ `.nav-item` แทน `.nav-btn`

ถ้าจอเล็ก/แท็บเล็ต ให้ยุบ sidebar เป็น dropdown หรือ bottom bar 2 กลุ่มแทน ไม่ต้องพยายามยัด sidebar แนวตั้งบนมือถือ

---

## Typography
เปลี่ยนจาก system font (`Segoe UI`) ที่ไม่มีคาแรกเตอร์ เป็น:
- **หัวข้อ/แบรนด์**: Archivo (น้ำหนัก 600-700) — ให้ความรู้สึกหนักแน่นแบบ terminal การเงิน ไม่ใช่ sans ทั่วไป
- **เนื้อหา/label**: IBM Plex Sans
- **ตัวเลข/ราคา/เวลา**: IBM Plex Mono (แทน `Cascadia Mono`/`SF Mono` เดิม) — ให้ tabular figures ชัดเจน อ่านตัวเลขเรียงคอลัมน์ง่ายกว่า

ตัวแปร `--num` เดิมเปลี่ยนเป็น `--font-mono: 'IBM Plex Mono', ui-monospace, monospace;` ใส่ Google Fonts link เพิ่มในหัว `<head>`

---

## สิ่งที่ไม่ต้องแตะ
- Logic การดึงข้อมูล (`fetchJSON`, `refreshAll`, `render*` ทั้งหมด) — เปลี่ยนแค่การ "แสดงผล" สีตามความหมาย ไม่เปลี่ยนว่าเงื่อนไขไหน trigger สีอะไร (bull/bear/warn logic เดิมถูกต้องอยู่แล้ว แค่เปลี่ยนชื่อตัวแปรสีให้สื่อความหมาย)
- โครงสร้างตาราง/id/class ของ data element ทั้งหมด — เปลี่ยนแค่ CSS ไม่เปลี่ยน id ที่ JS query อยู่
- จำนวน tab/section เดิม — แค่จัดกลุ่มใหม่ ไม่ลบของเดิม

## ลำดับแนะนำให้ opencode ทำ
1. แทนค่า `:root` ทั้งหมดตามตาราง + เพิ่ม Google Fonts link
2. ลบ radial-gradient บน body และ box-shadow glow ทุกจุด
3. ลบ emoji ทั้งหมด แทนด้วยข้อความ/accent-bar
4. รวม `.kpi.cyan/blue/purple` และ `.val.cyan/blue/purple` ให้เหลือ bull/bear/warn/neutral ตามความหมายจริงทีละจุด
5. เปลี่ยน `.panel h3 .ph.*` เป็น `.accent-bar` เดียว
6. Refactor nav จากแถวปุ่มเป็น sidebar 2 กลุ่มตามโครงสร้างใหม่ (bind event handler เดิม)
7. เทสทุก tab ว่า toggle ถูกต้อง, เทสทุกค่าสีว่ายังสื่อความหมายถูก (win=เขียว, loss=แดง) หลังเปลี่ยนตัวแปร
