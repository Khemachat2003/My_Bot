// สลับแท็บจาก sidebar (data-tab → section#tab-*)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1940–1950 แบบ move-only

/* ═══════ TABS ═══════ */
document.querySelectorAll('.nav-item').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.nav-item').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.content section').forEach(s=>s.style.display='none');
    btn.classList.add('active');
    document.getElementById('tab-'+btn.dataset.tab).style.display='block';
    window.dispatchEvent(new Event('resize'));
  });
});
