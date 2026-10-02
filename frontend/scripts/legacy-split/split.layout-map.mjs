// split.layout-map.mjs — แผนที่ CSS + HTML ของ index.html เดิม → ไฟล์ใหม่ (Phase A, move-only)

// CSS (บรรทัด 15–556 ใน <style>) — ช่วงต่อเนื่อง เรียงตามลำดับเดิม → cascade เหมือนเดิมทุกกฎ
export const CSS_FILES = [
  { file: 'styles/tokens.css', range: [15, 28], desc: 'design tokens (สี/ฟอนต์) — แหล่งความจริงเดียว' },
  { file: 'styles/global.css', range: [29, 42], desc: 'reset + body + scrollbar + .mono' },
  { file: 'features/status-bar/topbar.css', range: [43, 87], desc: 'แถบบน (brand/ราคา/สถิติ/logout)' },
  { file: 'app/layout.css', range: [88, 103], desc: 'shell: sidebar + content' },
  { file: 'shared/ui/cards.css', range: [104, 136], desc: 'KPI cards + panels' },
  { file: 'features/chart/chart-base.css', range: [137, 185], desc: 'กราฟพื้นฐาน + legend' },
  { file: 'features/overview/terminal-layout.css', range: [186, 194], desc: 'grid 3 คอลัมน์ของแท็บภาพรวม' },
  { file: 'features/watchlist/watchlist.css', range: [195, 220], desc: 'watchlist' },
  { file: 'features/chart/chart-panel.css', range: [221, 287], desc: 'แผงกราฟ + legend bar + panes + toolbar' },
  { file: 'features/overview/side-col.css', range: [288, 290], desc: 'คอลัมน์ขวาของแท็บภาพรวม' },
  { file: 'features/status-bar/statusbar.css', range: [291, 301], desc: 'แถบสถานะล่าง' },
  { file: 'features/chart/chart-fullscreen.css', range: [302, 306], desc: 'โหมดกราฟเต็มจอ' },
  { file: 'features/gauges/gauges.css', range: [307, 322], desc: 'Probability gauge' },
  { file: 'shared/ui/tables.css', range: [323, 342], desc: 'ตาราง + pill + empty state' },
  { file: 'features/setup-signals/setup-guide.css', range: [343, 396], desc: 'การ์ด/แถว Setup + tier' },
  { file: 'features/ml-signals/feed.css', range: [397, 412], desc: 'ฟีดสัญญาณ + hi-badge' },
  { file: 'features/cfd/open-trades.css', range: [413, 415], desc: 'grid ของ open trades' },
  { file: 'styles/responsive.css', range: [416, 479], desc: 'responsive ทุกหน้า (tablet/mobile)' },
  { file: 'shared/ui/report-layout.css', range: [480, 545], desc: 'คลาส j-* (hero/section/settings) ใช้ร่วม ML/Setup/Journal/CFD' },
  { file: 'features/overview/overview-bottom.css', range: [546, 556], desc: 'แถบสถิติ + equity/ฟีด ล่างของภาพรวม' },
];

// HTML partials — ซ้อนกันได้ (ช่วงลูกต้องอยู่ในช่วงแม่) → แทนด้วย <!-- @include … -->
export const HTML_PARTIALS = [
  { file: 'features/status-bar/topbar.html', range: [561, 584] },
  { file: 'app/sidebar.html', range: [589, 602] },
  { file: 'features/overview/view.html', range: [607, 720] },
  { file: 'features/watchlist/view.html', range: [610, 614] },
  { file: 'features/chart/view.html', range: [616, 684] },
  { file: 'features/gauges/view.html', range: [688, 691] },
  { file: 'features/setup-signals/mini-panel.html', range: [692, 695] },
  { file: 'features/ml-signals/view.html', range: [722, 787] },
  { file: 'features/setup-signals/view.html', range: [789, 882] },
  { file: 'features/journal/view.html', range: [884, 1019] },
  { file: 'features/cfd/view.html', range: [1021, 1114] },
  { file: 'features/status-bar/statusbar.html', range: [1119, 1130] },
];

export const STYLE_BLOCK = [14, 557]; // <style> … </style> เดิม → แทนด้วย <script type="module" src="/src/main.js">
