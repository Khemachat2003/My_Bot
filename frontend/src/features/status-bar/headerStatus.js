// topbar: สัญญาณ ML M1/M5 (/api/ml/latest) + นาฬิกา UTC + session
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2770–2785, 3243–3248 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';

async function refreshHeaderSignals(){
  try{
    const latest=await fetchJSON('/api/ml/latest');
    const sigEl=(id,g)=>{ const el=document.getElementById(id);
      if(!g) el.textContent='–';
      else {
        const c=(g.confidence||0)*100;
        const col=g.signal==='CALL'?'var(--green)':(g.signal==='PUT'?'var(--red)':'var(--muted)');
        const hi=(g.confidence||0)>0.7?` <span class="hi-badge">★${Math.round(c)}%</span>`:'';
        el.innerHTML=`<span style="color:${col}">${g.signal} ${Math.round(c)}%</span>${hi}`;
      }
    };
    sigEl('hM1',latest['M1']); sigEl('hM5',latest['M5']);
  }catch(e){}
}

function updateClock(){
  document.getElementById('hUtc').textContent=new Date().toISOString().substring(11,19);
  const h=new Date().getUTCHours();
  document.getElementById('hSession').textContent=h>=12&&h<21?'NY':(h>=7&&h<16?'London':(h>=0&&h<8?'Asia':'อื่นๆ'));
}


export { refreshHeaderSignals, updateClock };
