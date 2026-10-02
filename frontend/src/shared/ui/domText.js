// helper เขียนข้อความ/คลาสลง element
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1951–1955 แบบ move-only

/* ═══════ RENDER ═══════ */
function renderStat(el,val,cls){ if(!el) return; el.textContent=val; el.className='val'+(cls?' '+cls:''); }
function elText(id,v){ const el=document.getElementById(id); if(el) el.textContent=v; return el; }
function elTextCls(id,v,cls){ const el=elText(id,v); if(el) el.className=cls; return el; }


export { elText, elTextCls, renderStat };
