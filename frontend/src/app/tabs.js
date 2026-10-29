// สลับแท็บจาก sidebar (data-tab → section#tab-*) + sub-tab logic (Phase C-2)
// main tab: .nav-item[data-tab] → section#tab-<name>
// sub-tab:  .subtab[data-subtab] → .subtab-pane[data-pane] ภายใน section เดียวกัน

function activate(el) {
  const section = el.closest('section');
  if (!section) return;
  const name = el.dataset.subtab;
  section.querySelectorAll('.subtab').forEach((b) => b.classList.toggle('active', b === el));
  section.querySelectorAll('.subtab-pane').forEach((p) => {
    p.style.display = p.dataset.pane === name ? 'block' : 'none';
  });
  window.dispatchEvent(new Event('resize'));
}

document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.content section').forEach((s) => { s.style.display = 'none'; });
    btn.classList.add('active');
    const section = document.getElementById('tab-' + btn.dataset.tab);
    if (section) section.style.display = 'block';
    window.dispatchEvent(new Event('resize'));
  });
});

document.querySelectorAll('.subtab').forEach((btn) => {
  btn.addEventListener('click', () => activate(btn));
});

// Phase C-2 fix: ปุ่ม sub-tab ที่ mark active ไว้ใน HTML (pane เริ่มต้นของแต่ละหน้า)
// ยังไม่เคยถูก activate → pane ของมันคง display:none จาก HTML → หน้าว่างจนกว่าจะกด
// สลับไปแท็บอื่นแล้วกลับมา (bug ที่เจอทั้ง ศูนย์สัญญาณ / ผลงาน & บันทึก / ประวัติ & แจ้งเตือน)
// → activate ให้ทุก section ครั้งเดียวตอนโหลด เพื่อให้ pane เริ่มต้นแสดงทันที
document.querySelectorAll('.content section').forEach((section) => {
  const active = section.querySelector('.subtab.active');
  if (active) activate(active);
});
