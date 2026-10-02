// CFD Backtest — /api/cfd/backtest
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3285–3362 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';

async function runCFDBacktest(){
  const cap=document.getElementById('cfdCapital').value;
  const sl=document.getElementById('cfdSL').value;
  const tp1=document.getElementById('cfdTP1').value;
  const tp2=document.getElementById('cfdTP2').value;
  const spread=document.getElementById('cfdSpread').value;
  const risk=document.getElementById('cfdRisk').value/100;
  const stype=document.getElementById('cfdSignalType').value;
  const q=new URLSearchParams({capital:cap,sl_pips:sl,tp1_pips:tp1,tp2_pips:tp2,
    spread_pips:spread,risk_pct:risk,signal_type:stype});
  try{
    const s=document.getElementById('cfdSummary');
    s.innerHTML='<div style="color:var(--muted);font-size:11px;">กำลังคำนวณ...</div>';
    const data=await fetchJSON('/api/cfd/backtest?'+q);
    renderCFDSummary(data);
    renderCFDCompare(data);
    renderCFDTrades(data);
  }catch(e){
    document.getElementById('cfdSummary').innerHTML='<div style="color:var(--red);">Error: '+e.message+'</div>';
  }
}
function renderCFDSummary(d){
  const el=document.getElementById('cfdSummary');
  const p=d.params;
  const items=[
    {label:'Signals',val:d.total,color:'var(--text)'},
    {label:'Lot Size',val:p.lot_size,color:'var(--cyan)'},
    {label:'Risk/Trade',val:'$'+p.risk_per_trade,color:'var(--yellow)'},
    {label:'TP1 WR',val:d.tp1.wr+'%',color:d.tp1.wr>=54.95?'var(--green)':'var(--red)'},
    {label:'TP1 P&L',val:'$'+d.tp1.pnl.toFixed(2),color:d.tp1.pnl>=0?'var(--green)':'var(--red)'},
    {label:'TP2 WR',val:d.tp2.wr+'%',color:d.tp2.wr>=40?'var(--green)':'var(--red)'},
    {label:'TP2 P&L',val:'$'+d.tp2.pnl.toFixed(2),color:d.tp2.pnl>=0?'var(--green)':'var(--red)'},
  ];
  el.innerHTML=items.map(i=>`<div class="j-card"><div class="j-card-label">${i.label}</div><div class="val" style="color:${i.color};font-size:16px;font-weight:800;">${i.val}</div></div>`).join('');
}
function renderCFDCompare(d){
  const tbody=document.querySelector('#cfdCompareTable tbody');
  let html='';
  const all=['SETUP','ML'];
  for(const sys of all){
    const sd=d.by_type[sys]; if(!sd) continue;
    for(const dir of ['CALL','PUT']){
      const key=sys+'_'+dir;
      const td=d.by_type_dir[key]; if(!td) continue;
      const t1=td.tp1,t2=td.tp2;
      html+=`<tr>
        <td>${sys}</td><td class="${dir==='CALL'?'dir-call':'dir-put'}">${dir}</td>
        <td>${t1.total}</td><td style="color:${t1.wr>=54.95?'var(--green)':'var(--red)'}">${t1.wr}%</td>
        <td style="color:${t1.pnl>=0?'var(--green)':'var(--red)'}">$${t1.pnl.toFixed(2)}</td>
        <td>${t2.total}</td><td style="color:${t2.wr>=40?'var(--green)':'var(--red)'}">${t2.wr}%</td>
        <td style="color:${t2.pnl>=0?'var(--green)':'var(--red)'}">$${t2.pnl.toFixed(2)}</td>
      </tr>`;
    }
  }
  // total rows
  html+=`<tr style="border-top:2px solid var(--border);font-weight:700;">
    <td colspan="2">TOTAL</td>
    <td>${d.tp1.total}</td><td style="color:${d.tp1.wr>=54.95?'var(--green)':'var(--red)'}">${d.tp1.wr}%</td>
    <td style="color:${d.tp1.pnl>=0?'var(--green)':'var(--red)'}">$${d.tp1.pnl.toFixed(2)}</td>
    <td>${d.tp2.total}</td><td style="color:${d.tp2.wr>=40?'var(--green)':'var(--red)'}">${d.tp2.wr}%</td>
    <td style="color:${d.tp2.pnl>=0?'var(--green)':'var(--red)'}">$${d.tp2.pnl.toFixed(2)}</td>
  </tr>`;
  tbody.innerHTML=html;
}
function renderCFDTrades(d){
  const tbody=document.querySelector('#cfdTradeTable tbody');
  const trades=d.trades.slice(-100).reverse();
  tbody.innerHTML=trades.map((t,i)=>`<tr>
    <td>${t.id}</td><td>${t.sys}</td>
    <td class="${t.dir==='CALL'?'dir-call':'dir-put'}">${t.dir}</td>
    <td>${t.entry}</td>
    <td style="color:${t.tp1==='WIN'?'var(--green)':'var(--red)'}">${t.tp1}</td>
    <td style="color:${t.tp2==='WIN'?'var(--green)':'var(--red)'}">${t.tp2}</td>
    <td style="color:${t.pnl1>=0?'var(--green)':'var(--red)'}">$${t.pnl1.toFixed(2)}</td>
    <td style="color:${t.pnl2>=0?'var(--green)':'var(--red)'}">$${t.pnl2.toFixed(2)}</td>
  </tr>`).join('');
}


// แทน onclick="runCFDBacktest()" เดิมบนปุ่ม Run Backtest
document.getElementById('btnRunCfdBacktest')?.addEventListener('click', () => runCFDBacktest());
