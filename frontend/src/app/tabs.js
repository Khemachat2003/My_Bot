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
