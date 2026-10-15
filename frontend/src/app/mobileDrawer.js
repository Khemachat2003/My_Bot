// mobileDrawer.js — มือถือ ≤768px: hamburger เปิด/ปิด sidebar แบบ drawer (Phase C-7 — design_system 5.1 มือถือ)
// ปิดเมื่อ: เลือกแท็บ / คลิก scrim / กด Escape / resize ข้าม breakpoint — tabs.js ไม่ถูกแตะ
// CSS อยู่ที่ styles/responsive.css (@media ≤768px) — desktop ≥769px ไม่มีผลใด ๆ

const BREAKPOINT = 768;

const toggle = document.getElementById('navToggle');

// scrim สร้างด้วย JS แล้ว append ท้าย body — ไม่ต้องแก้ index.html
let scrim = document.getElementById('drawerScrim');
if (!scrim) {
  scrim = document.createElement('div');
  scrim.id = 'drawerScrim';
  document.body.appendChild(scrim);
}

const setExpanded = (open) => toggle?.setAttribute('aria-expanded', String(open));
const close = () => {
  document.body.classList.remove('drawer-open');
  setExpanded(false);
};

toggle?.addEventListener('click', () => {
  const open = !document.body.classList.contains('drawer-open');
  document.body.classList.toggle('drawer-open', open);
  setExpanded(open);
});
scrim.addEventListener('click', close);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') close();
});
// เลือกแท็บ → ปิด drawer (ฟัง .nav-item ที่เดียว — tabs.js ยังสลับแท็บตามเดิม)
document.querySelectorAll('.nav-item').forEach((el) => el.addEventListener('click', close));
// resize/rotate ข้าม breakpoint → ปิด (ทั้งขึ้น/ลง กันค้าง .drawer-open บนจอใหญ่)
let lastW = window.innerWidth;
window.addEventListener('resize', () => {
  const w = window.innerWidth;
  if ((w > BREAKPOINT) !== (lastW > BREAKPOINT)) close();
  lastW = w;
});
