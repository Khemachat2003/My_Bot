# frontend/ — Dashboard SPA (Vite, ES modules)

## โฟลเดอร์นี้ทำอะไร

หน้าเว็บ monitor ระบบเทรด (กราฟ, watchlist, สัญญาณ ML/Rule-Based, Journal P&L, CFD backtest)
backend (`backend/api.py`) เสิร์ฟหน้า build แล้วจาก `dist/` ที่ URL `/` และ mount `/static` = โฟลเดอร์นี้

## ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| `index.html` | shell จริงที่เสิร์ฟ **หลัง build** (`dist/index.html`) — ใน repo เก็บรุ่น dev (`@include` partials) |
| `vite.config.js` | base `/static/dist/` + plugin ประกอบ `@include` + proxy dev → uvicorn |
| `src/main.js` | จุดเริ่ม: import CSS (ลำดับเดิม) + ทุก module (ลำดับ side-effect เดิม) |
| `src/features/<name>/` | หนึ่งหน้าจอ/หน้าที่: component + api + css + `index.js` (ทางเข้าเดียว) |
| `src/shared/` | `api/client.js` (fetch ที่เดียว), `lib/` (format/indicators), `ui/` (toast/dom/css กลาง) |
| `src/styles/` | `tokens.css` = สี/ฟอนต์ (แหล่งความจริงเดียว), `index.css` = ลำดับ @import ตาม cascade เดิม |
| `src/types/api.d.ts` | TS types ของ `/api/*` (gen จาก OpenAPI — `npm run gen:types` ห้ามแก้มือ) |
| `tests/visual/` | playwright: ภาพ 10 ภาพ + network baseline (`__snapshots__`/fixtures = git-ignored) |
| `scripts/legacy-split/` | สคริปต์แยกไฟล์จาก `index.legacy.html` (อ้างอิงประวัติ/regenerate ได้ — ไม่ต้องแตะต่อ) |

## ข้อควรระวัง

- **ลำดับ import ใน `main.js` และลำดับ `@import` ใน `styles/index.css` = ลำดับโค้ดเดิม**
  การสลับลำดับ = เปลี่ยน cascade/z-index โดยไม่รู้ตัว → ต้องเทียบ screenshot ทุกครั้ง
- ข้าม feature import ได้เฉพาะผ่าน `features/<x>/index.js` — ห้าม `fetch` นอก `shared/api/client.js`
- แก้ `src/**` แล้ว **ต้อง `npm run build` + commit `dist/`** (VPS ไม่มี Node เสิร์ฟ dist ที่ commit ไว้)
- แท็ก/คลาส CSS ส่วนใหญ่ถูก render ด้วย template string ใน JS (`renderXxx`) — หา id ก่อนแก้ view.html
- ห้ามแตะ `vendor/` (ไลบรารีในเครื่อง) และห้ามเปลี่ยนเป็น CDN เฉพาะหน้า (มี fallback jsdelivr อยู่แล้ว)
- ห้าม hard-code ค่าลับ/IP ลง frontend — เรียก `/api/*` เท่านั้น

## คำสั่ง

```bash
npm install        # ครั้งแรก
npm run dev        # dev (ต้องรัน uvicorn backend.api:app --port 8000 คู่ด้วย)
npm run check      # lint + typecheck + test + build
npm run test:visual:baseline   # สร้าง baseline จาก _archive/index.legacy.html (ครั้งเดียว)
npm run test:visual            # เทียบ dist กับ baseline (หลัง build)
```
