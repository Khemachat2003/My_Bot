// mobileCardLabels.js — ใส่ data-label ให้ <td> ทุกตารางโดยอัตโนมัติ (Phase C-7)
//   label อ่านสดจาก <thead> คอลัมน์เดียวกัน (แถวหัวสุดท้าย เผื่อ thead 2 แถว)
//   → CSS ฝั่ง responsive.css เปลี่ยนแถวเป็นการ์ดเฉพาะตาราง .tbl-cards บนจอ ≤768px
//     โดยไม่ต้องแกะ template ใน renderer แม้แต่บรรทัดเดียว
//   re-render ด้วย innerHTML จับด้วย MutationObserver — เซลล์ colspan (empty state) ไม่ใส่ label
//   ตารางใน SKIP_TABLES คงเลื่อนแนวนอน (ตารางเปรียบเทียบหัวกลุ่ม 2 แถว)

const SKIP_TABLES = new Set(['cfdCompareTable']);

function labelTable(table) {
  if (SKIP_TABLES.has(table.id) || !table.tHead || !table.tHead.rows.length) return;
  const labels = [...table.tHead.rows[table.tHead.rows.length - 1].cells]
    .map((th) => th.textContent.trim().replace(/\s+/g, ' '));
  for (const tbody of table.tBodies) {
    for (const tr of tbody.rows) {
      let col = 0;
      for (const td of tr.cells) {
        if (td.colSpan > 1) { // empty state / เซลล์ครอบคอลัมน์ → ไม่มี label
          col += td.colSpan;
          continue;
        }
        td.dataset.label = labels[col] || '';
        col += 1;
      }
    }
  }
}

function labelAll() {
  document.querySelectorAll('table').forEach(labelTable);
}
labelAll();

// renderer ทุกตัว re-render ด้วย tbody.innerHTML = ... → จับเฉพาะ node ที่เพิ่มเข้ามา
const affected = new Set();
new MutationObserver((records) => {
  for (const r of records) {
    for (const n of r.addedNodes) {
      if (!(n instanceof Element)) continue;
      const table = n.tagName === 'TABLE' ? n : n.closest('table');
      if (table) affected.add(table);
    }
  }
  affected.forEach(labelTable);
  affected.clear();
}).observe(document.body, { childList: true, subtree: true });
