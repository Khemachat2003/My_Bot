// ปุ่มช่วงเวลา, บันทึกตั้งค่า (POST /api/journal/settings), Export (/api/journal/export)
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3250–3284 แบบ move-only

import { refreshJournalMoney, renderPeriodTable } from './moneyReport.js';

document.querySelectorAll('.j-ptab').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.j-ptab').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    renderPeriodTable();
  });
});
document.getElementById('btnSaveSettings').addEventListener('click', async ()=>{
  const st=document.getElementById('settStatus');
  try{
    const res=await fetch('/api/journal/settings',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        capital:parseFloat(document.getElementById('setCapital').value),
        stake:parseFloat(document.getElementById('setStake').value),
        currency:document.getElementById('setCurrency').value,
      })});
    if(res.ok){ st.textContent='บันทึกแล้ว ✓'; await refreshJournalMoney(); }
    else st.textContent='บันทึกไม่สำเร็จ — ตรวจข้อมูล';
  }catch(e){ st.textContent='บันทึกไม่สำเร็จ — connection error'; }
  setTimeout(()=>st.textContent='',3000);
});
document.getElementById('btnExportJ')?.addEventListener('click', ()=>{
  document.getElementById('jSettings').classList.add('open');
  window.scrollTo({top:0,behavior:'smooth'});
});
document.getElementById('btnExport').addEventListener('click', ()=>{
  const s=document.getElementById('expStart').value, e=document.getElementById('expEnd').value;
  const q=new URLSearchParams();
  if(s) q.set('start',s);
  if(e) q.set('end',e);
  const qs=q.toString();
  window.location.href='/api/journal/export'+(qs?'?'+qs:'');
});
