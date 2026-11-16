// CFD Backtest — /api/cfd/backtest
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3285–3362 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';
import { pnlColor, pnlText, wrColor } from '../../shared/lib/pnlText.js';

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
    document.getElementById('cfdSummary').innerHTML='<div style="color:var(--bear);">Error: '+e.message+'</div>';
  }
}
function renderCFDSummary(d){
  const el=document.getElementById('cfdSummary');
  const p=d.params;
  // C-8 redesign: 3 hero cards (ภาษาเดียวกับ Journal j-hero-card) — TP1/TP2/ความเสี่ยง
  const wr1=`var(--${wrColor(d.tp1.wr,54.95)})`, wr2=`var(--${wrColor(d.tp2.wr,40)})`;
  el.innerHTML=`
    <div class="j-hero-card wr">
      <div class="jh-lbl">TP1 · R:R 1:2</div>
      <div class="jh-val" style="color:var(--${pnlColor(d.tp1.pnl)})">${pnlText(d.tp1.pnl,{fixed:true,digits:2,prefix:'$'})}</div>
      <div class="jh-sub">WR <b style="color:${wr1}">${d.tp1.wr}%</b> · ${d.tp1.total} ไม้</div>
    </div>
    <div class="j-hero-card wr">
      <div class="jh-lbl">TP2 · R:R 1:3</div>
      <div class="jh-val" style="color:var(--${pnlColor(d.tp2.pnl)})">${pnlText(d.tp2.pnl,{fixed:true,digits:2,prefix:'$'})}</div>
      <div class="jh-sub">WR <b style="color:${wr2}">${d.tp2.wr}%</b> · ${d.tp2.total} ไม้</div>
    </div>
    <div class="j-hero-card bal">
      <div class="jh-lbl">ความเสี่ยง / ไม้</div>
      <div class="jh-val">$${p.risk_per_trade}</div>
      <div class="jh-sub">Lot <b>${p.lot_size}</b> · สัญญาณ <b>${d.total}</b> ไม้</div>
    </div>`;
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
        <td>${t1.total}</td><td style="color:var(--${wrColor(t1.wr,54.95)})">${t1.wr}%</td>
        <td style="color:var(--${pnlColor(t1.pnl)})">${pnlText(t1.pnl,{fixed:true,digits:2,prefix:'$'})}</td>
        <td>${t2.total}</td><td style="color:var(--${wrColor(t2.wr,40)})">${t2.wr}%</td>
        <td style="color:var(--${pnlColor(t2.pnl)})">${pnlText(t2.pnl,{fixed:true,digits:2,prefix:'$'})}</td>
      </tr>`;
    }
  }
  // total rows
  html+=`<tr style="border-top:2px solid var(--border);font-weight:700;">
    <td colspan="2">TOTAL</td>
    <td>${d.tp1.total}</td><td style="color:var(--${wrColor(d.tp1.wr,54.95)})">${d.tp1.wr}%</td>
    <td style="color:var(--${pnlColor(d.tp1.pnl)})">${pnlText(d.tp1.pnl,{fixed:true,digits:2,prefix:'$'})}</td>
    <td>${d.tp2.total}</td><td style="color:var(--${wrColor(d.tp2.wr,40)})">${d.tp2.wr}%</td>
    <td style="color:var(--${pnlColor(d.tp2.pnl)})">${pnlText(d.tp2.pnl,{fixed:true,digits:2,prefix:'$'})}</td>
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
    <td style="color:${t.tp1==='WIN'?'var(--bull)':'var(--bear)'}">${t.tp1}</td>
    <td style="color:${t.tp2==='WIN'?'var(--bull)':'var(--bear)'}">${t.tp2}</td>
    <td style="color:var(--${pnlColor(t.pnl1)})">${pnlText(t.pnl1,{fixed:true,digits:2,prefix:'$'})}</td>
    <td style="color:var(--${pnlColor(t.pnl2)})">${pnlText(t.pnl2,{fixed:true,digits:2,prefix:'$'})}</td>
  </tr>`).join('');
}


// แทน onclick="runCFDBacktest()" เดิมบนปุ่ม Run Backtest
document.getElementById('btnRunCfdBacktest')?.addEventListener('click', () => runCFDBacktest());
