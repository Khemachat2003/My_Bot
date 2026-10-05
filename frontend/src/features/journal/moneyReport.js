// รายงาน P&L เงินจริง — /api/journal/report
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3123–3190 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';
import { pnlColor, pnlText } from '../../shared/lib/pnlText.js';

let moneyReport=null;
function setKpi(id,val,cls){const el=document.getElementById(id); if(!el)return; el.textContent=val; el.className='val '+(cls||'muted');}
// C-5 (design_system 5.3): P&L คู่เครื่องหมายเสมอ รูปแบบเลขเดิม (th-TH ทศนิยม ≤2) — ศูนย์ไม่มีเครื่องหมาย
function fmtMoney(v,cur){ return pnlText(v,{digits:2,suffix:' '+cur}); }
// ROI ใน sub-line เติม + เมื่อบวก (เลขคงรูปเดิมที่ backend ส่งมา)
function roiTxt(v){ return (v>0?'+':'')+v+'%'; }

async function refreshJournalMoney(){
  try{
    const r=await fetchJSON('/api/journal/report');
    moneyReport=r;
    const cur=r.settings.currency||'THB';
    const active=document.activeElement;
    if(active!==document.getElementById('setCapital')) document.getElementById('setCapital').value=r.settings.capital;
    if(active!==document.getElementById('setStake')) document.getElementById('setStake').value=r.settings.stake;
    if(active!==document.getElementById('setCurrency')) document.getElementById('setCurrency').value=cur;
    const A=r.summary.ALL, ML=r.summary.ML, ST=r.summary.SETUP;
    setKpi('mPnlAll',fmtMoney(A.pnl_money,cur),pnlColor(A.pnl_money));
    document.getElementById('mPnlAllSub').textContent=`${A.n} trades · ${A.wins}W / ${A.losses}L · ROI ${roiTxt(A.roi)}`;
    setKpi('mPnlMl',fmtMoney(ML.pnl_money,cur),pnlColor(ML.pnl_money));
    document.getElementById('jMlN').textContent=ML.n;
    document.getElementById('jMlWr').textContent=ML.n?ML.winrate+'%':'–';
    document.getElementById('mRoiMl').textContent=`ROI ${roiTxt(ML.roi)}`;
    const mlBar=document.getElementById('jMlBar');
    if(mlBar) mlBar.style.width=Math.min(ML.winrate||0,100)+'%';
    setKpi('mPnlSt',fmtMoney(ST.pnl_money,cur),pnlColor(ST.pnl_money));
    document.getElementById('jRbN').textContent=ST.n;
    document.getElementById('jRbWr').textContent=ST.n?ST.winrate+'%':'–';
    document.getElementById('mRoiSt').textContent=`ROI ${roiTxt(ST.roi)}`;
    const rbBar=document.getElementById('jRbBar');
    if(rbBar) rbBar.style.width=Math.min(ST.winrate||0,100)+'%';
    const bal=r.daily.length?r.daily[r.daily.length-1].balance:r.settings.capital;
    document.getElementById('mBalance').textContent=Number(bal).toLocaleString('th-TH',{maximumFractionDigits:2})+' '+cur;
    document.getElementById('mBalanceSub').textContent='ทุน '+Number(r.settings.capital).toLocaleString('th-TH')+' '+cur;
    // CFD Balance
    const cfd=r.cfd_summary||{};
    const cfdBal=cfd.balance!=null?cfd.balance:cfd.capital||5000;
    const cfdPnl=cfd.pnl_money||0;
    const cfdEl=document.getElementById('mCfdBalance');
    if(cfdEl){
      cfdEl.textContent=Number(cfdBal).toLocaleString('th-TH',{maximumFractionDigits:2})+' '+cur;
      cfdEl.style.color='var(--'+pnlColor(cfdPnl)+')'; // C-5 (5.3): ศูนย์/ไม่มีข้อมูล → muted
    }
    const cfdSubEl=document.getElementById('mCfdBalanceSub');
    if(cfdSubEl) cfdSubEl.textContent='ทุน '+Number(cfd.capital||5000).toLocaleString('th-TH')+' '+cur+' · P&L '+pnlText(cfdPnl,{digits:2});
    renderPeriodTable();
  }catch(e){}
}

function renderPeriodTable(){
  if(!moneyReport) return;
  const activeTab = document.querySelector('.j-ptab.active');
  const kind = activeTab ? activeTab.dataset.period : 'daily';
  const rows=moneyReport[kind]||[];
  const cur=moneyReport.settings.currency||'THB';
  const pnl=(v)=>`${v>0?'+':''}${Number(v).toLocaleString('th-TH',{maximumFractionDigits:2})} ${cur}`;
  const body=document.querySelector('#periodTable tbody');
  body.innerHTML=rows.slice().reverse().map(d=>`
    <tr>
      <td class="mono"><b>${d.period}</b></td>
      <td class="mono">${d.ALL.n}</td><td class="mono ${d.ALL.winrate>=50?'dir-call':'dir-put'}">${d.ALL.n?d.ALL.winrate+'%':'–'}</td>
      <td class="mono ${d.ALL.pnl_money>0?'dir-call':(d.ALL.pnl_money<0?'dir-put':'')}">${d.ALL.n?pnl(d.ALL.pnl_money):'–'}</td>
      <td class="mono">${d.ALL.n?d.ALL.roi+'%':'–'}</td>
      <td class="mono">${d.ML.n}</td><td class="mono">${d.ML.n?d.ML.winrate+'%':'–'}</td>
      <td class="mono ${d.ML.pnl_money>0?'dir-call':(d.ML.pnl_money<0?'dir-put':'')}">${d.ML.n?pnl(d.ML.pnl_money):'–'}</td>
      <td class="mono">${d.SETUP.n}</td><td class="mono">${d.SETUP.n?d.SETUP.winrate+'%':'–'}</td>
      <td class="mono ${d.SETUP.pnl_money>0?'dir-call':(d.SETUP.pnl_money<0?'dir-put':'')}">${d.SETUP.n?pnl(d.SETUP.pnl_money):'–'}</td>
      <td class="mono">${Number(d.balance).toLocaleString('th-TH',{maximumFractionDigits:2})}</td>
    </tr>`).join('') || '<tr><td colspan="12" class="empty">ยังไม่มีข้อมูล</td></tr>';
}


export { moneyReport, refreshJournalMoney, renderPeriodTable };
