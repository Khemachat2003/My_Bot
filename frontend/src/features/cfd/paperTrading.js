// CFD Paper Trading real-time — /api/cfd/paper
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3363–3445 แบบ move-only
// TODO: ย้ายไป backend — progress bar Entry→TP2 ของ open trade คำนวณฝั่งหน้าเว็บ

import { fetchJSON } from '../../shared/api/client.js';
import { fmtHM } from '../../shared/lib/formatTime.js';

async function refreshCFDPaper(){
  try{
    const d=await fetchJSON('/api/cfd/paper');
    renderCFDPaperSummary(d);
    renderCFDPaperTrades(d);
  }catch(e){}
}
function renderCFDPaperSummary(d){
  const el=document.getElementById('cfdPaperSummary');
  if(!el) return;
  const wrColor=d.wr>=54.95?'var(--green)':d.wr>=40?'var(--yellow)':'var(--red)';
  const pnlColor=d.total_pnl>=0?'var(--green)':'var(--red)';
  const items=[
    {label:'Total Trades',val:d.total,color:'var(--text)'},
    {label:'Open',val:d.open,color:'var(--cyan)'},
    {label:'TP1 Hits',val:d.tp1,color:'var(--green)'},
    {label:'TP2 Hits',val:d.tp2,color:'var(--green)'},
    {label:'SL Hits',val:d.sl,color:'var(--red)'},
    {label:'Win Rate',val:d.wr+'%',color:wrColor},
    {label:'Total P&L',val:'$'+d.total_pnl.toFixed(2),color:pnlColor},
  ];
  el.innerHTML=items.map(i=>`<div class="j-card"><div class="j-card-label">${i.label}</div><div class="val" style="color:${i.color};font-size:15px;font-weight:800;">${i.val}</div></div>`).join('');
}
function renderCFDPaperTrades(d){
  const tbody=document.querySelector('#cfdPaperTable tbody');
  if(!tbody) return;
  const trades=d.trades.slice(-50).reverse();
  tbody.innerHTML=trades.map(t=>{
    const rc=t.result==='TP1'||t.result==='TP2'?'var(--green)':t.result==='SL'?'var(--red)':'var(--yellow)';
    return `<tr>
      <td>${t.id}</td>
      <td>${fmtHM(t.entry_time)}</td>
      <td>${t.signal_type}</td>
      <td class="${t.direction==='CALL'?'dir-call':'dir-put'}">${t.direction}</td>
      <td>${t.entry_price?.toFixed(2)}</td>
      <td>${t.sl_price?.toFixed(2)}</td>
      <td>${t.tp1_price?.toFixed(2)}</td>
      <td>${t.tp2_price?.toFixed(2)}</td>
      <td style="color:${rc}">${t.result}</td>
      <td>${t.exit_price?.toFixed(2)??'–'}</td>
      <td>${t.hold_bars??'–'}</td>
      <td style="color:${(t.pnl||0)>=0?'var(--green)':'var(--red)'}">${t.pnl!=null?'$'+t.pnl.toFixed(2):'–'}</td>
    </tr>`;
  }).join('');

  const openDiv=document.getElementById('cfdOpenTrades');
  if(!openDiv) return;
  const open=d.open_trades||[];
  if(!open.length){openDiv.innerHTML='';return;}
  openDiv.innerHTML='<h4 style="color:var(--cyan);font-size:12px;margin-bottom:8px;">OPEN TRADES ('+open.length+')</h4>'+
    open.map(t=>{
      const lp=t.live_price||t.entry_price;
      const pnlCol=(t.unrealized_pnl||0)>=0?'var(--green)':'var(--red)';
      const dirCol=t.direction==='CALL'?'var(--green)':'var(--red)';
      const progress=t.direction==='CALL'
        ? ((lp-t.entry_price)/(t.tp2_price-t.entry_price)*100)
        : ((t.entry_price-lp)/(t.entry_price-t.tp2_price)*100);
      return `<div style="background:var(--bg);border:1px solid ${t.tp1_hit?'var(--yellow)':'var(--border)'};border-radius:8px;padding:10px;margin-bottom:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="color:${dirCol};font-weight:700;">${t.direction} ${t.signal_type} #${t.signal_id} ${t.tp1_hit?'<span style="color:var(--yellow);font-size:10px;">TP1 HIT →</span>':''}</span>
          <span style="color:var(--muted);font-size:11px;">${fmtHM(t.entry_time)}</span>
        </div>
        <div class="open-trade-grid">
          <div><span style="color:var(--muted);">Entry</span><br><b>${t.effective_entry?.toFixed(2)||'?'}</b></div>
          <div><span style="color:var(--cyan);">Live</span><br><b>${lp?.toFixed(2)||'?'}</b></div>
          <div><span style="color:var(--red);">SL (${t.dist_to_sl??'?'})</span><br><b style="color:var(--red)">${t.sl_price?.toFixed(2)}</b></div>
          <div><span style="color:var(--yellow);">TP1 (${t.dist_to_tp1??'?'})</span><br><b style="color:var(--yellow)">${t.tp1_price?.toFixed(2)}</b></div>
          <div><span style="color:var(--green);">TP2 (${t.dist_to_tp2??'?'})</span><br><b style="color:var(--green)">${t.tp2_price?.toFixed(2)}</b></div>
        </div>
        <div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">
          <div>
            <span style="font-size:11px;color:var(--muted);">P&L: </span>
            <span style="font-weight:700;color:${pnlCol}">${t.unrealized_pnl!=null?'$'+t.unrealized_pnl.toFixed(2):'–'}</span>
            <span style="font-size:11px;color:var(--muted);margin-left:8px;">(${t.unrealized_pips??'–'} pips)</span>
          </div>
          <div style="flex:0 1 120px;min-width:60px;height:6px;background:var(--bg2);border-radius:3px;overflow:hidden;">
            <div style="height:100%;width:${Math.min(Math.max(progress||0,0),100)}%;background:${dirCol};border-radius:3px;transition:width 1s;"></div>
          </div>
        </div>
      </div>`;
    }).join('');
}


export { refreshCFDPaper };
