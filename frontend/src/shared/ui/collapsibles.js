// collapsibles.js — แทน inline onclick เดิม (พับ/ขยาย section) ด้วย event delegation จุดเดียว
//   data-toggle-parent="open"   → เดิม onclick="this.parentElement.classList.toggle('open')"
//   data-toggle-self="expanded" → เดิม onclick="this.classList.toggle('expanded')" (แถว Setup ที่ render ด้วย JS)
// พฤติกรรมเท่าเดิม: คลิกส่วนหัว/แถว → toggle class เดียวกัน (ใช้ได้กับ element ที่สร้างทีหลังด้วย)
document.addEventListener('click', (e) => {
  const target = e.target instanceof Element ? e.target : null;
  if (!target) return;
  const head = target.closest('[data-toggle-parent]');
  if (head && head.parentElement) head.parentElement.classList.toggle(head.getAttribute('data-toggle-parent'));
  const row = target.closest('[data-toggle-self]');
  if (row) row.classList.toggle(row.getAttribute('data-toggle-self'));
});
