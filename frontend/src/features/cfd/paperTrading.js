// CFD Paper Trading real-time — /api/cfd/paper
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3363–3445 แบบ move-only
// TODO: ย้ายไป backend — progress bar Entry→TP2 ของ open trade คำนวณฝั่งหน้าเว็บ

import { fetchJSON } from '../../shared/api/client.js';
import { fmtHM } from '../../shared/lib/formatTime.js';
import { pnlColor, pnlText, wrColor } from '../../shared/lib/pnlText.js';

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
  // C-8 redesign: 3 hero cards (ภาษาเดียวกับ Journal) — P&L / WR / Open + sub รวมสถิติที่เหลือ
  el.innerHTML=`
    <div class="j-hero-card pnl">
      <div class="jh-lbl">Total P&L</div>
      <div class="jh-val" style="color:var(--${pnlColor(d.total_pnl)})">${pnlText(d.total_pnl,{fixed:true,digits:2,prefix:'$'})}</div>
      <div class="jh-sub">${d.total} ไม้ · TP1 <b>${d.tp1}</b> · TP2 <b>${d.tp2}</b> · SL <b>${d.sl}</b></div>
    </div>
    <div class="j-hero-card wr">
      <div class="jh-lbl">Win Rate</div>
      <div class="jh-val" style="color:var(--${wrColor(d.wr,54.95,40)})">${d.wr}%</div>
      <div class="jh-sub">เกณฑ์: TP1 ≥54.95% · TP2 ≥40%</div>
    </div>
    <div class="j-hero-card bal">
      <div class="jh-lbl">ตำแหน่งที่เปิดอยู่</div>
      <div class="jh-val" style="color:var(--accent)">${d.open}</div>
      <div class="jh-sub">จากทั้งหมด <b>${d.total}</b> ไม้ (paper real-time)</div>
    </div>`;
}
function renderCFDPaperTrades(d){
  const tbody=document.querySelector('#cfdPaperTable tbody');
  if(!tbody) return;
  const trades=d.trades.slice(-50).reverse();
  tbody.innerHTML=trades.map(t=>{
    const rc=t.result==='TP1'||t.result==='TP2'?'var(--bull)':t.result==='SL'?'var(--bear)':'var(--warn)';
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
      <td style="color:var(--${pnlColor(t.pnl)})">${t.pnl!=null?pnlText(t.pnl,{fixed:true,digits:2,prefix:'$'}):'–'}</td>
    </tr>`;
  }).join('');

  const openDiv=document.getElementById('cfdOpenTrades');
  if(!openDiv) return;
  const open=d.open_trades||[];
  if(!open.length){openDiv.innerHTML='';return;}
  openDiv.innerHTML=`<div class="cfd-tbl-h" style="margin:14px 0 8px;">Open Trades — ${open.length} ตำแหน่ง</div>`+
    open.map(t=>{
      const lp=t.live_price||t.entry_price;
      const pnlCol='var(--'+pnlColor(t.unrealized_pnl)+')'; // ศูนย์/null → muted (5.3)
      const dirCol=t.direction==='CALL'?'var(--bull)':'var(--bear)';
      const progress=t.direction==='CALL'
        ? ((lp-t.entry_price)/(t.tp2_price-t.entry_price)*100)
        : ((t.entry_price-lp)/(t.entry_price-t.tp2_price)*100);
      // ตำแหน่ง TP1 บนแถบ (สัดส่วน entry→tp2 ตามทิศ)
      const tp1pct=t.direction==='CALL'
        ? ((t.tp1_price-t.entry_price)/(t.tp2_price-t.entry_price)*100)
        : ((t.entry_price-t.tp1_price)/(t.entry_price-t.tp2_price)*100);
      return `<div class="ot-card${t.tp1_hit?' ot-tp1hit':''}">
        <div class="ot-head">
          <span class="ot-dir" style="color:${dirCol};">${t.direction==='CALL'?'▲':'▼'} ${t.direction}
            <span class="ot-chip">${t.signal_type} #${t.signal_id}</span>
            ${t.tp1_hit?'<span class="ot-chip warn">TP1 HIT →</span>':''}
          </span>
          <span class="ot-meta">${fmtHM(t.entry_time)}</span>
        </div>
        <div class="open-trade-grid">
          <div><span style="color:var(--muted);">Entry</span><br><b>${t.effective_entry?.toFixed(2)||'?'}</b></div>
          <div><span style="color:var(--accent);">Live</span><br><b>${lp?.toFixed(2)||'?'}</b></div>
          <div><span style="color:var(--bear);">SL (${t.dist_to_sl??'?'})</span><br><b style="color:var(--bear)">${t.sl_price?.toFixed(2)}</b></div>
          <div><span style="color:var(--warn);">TP1 (${t.dist_to_tp1??'?'})</span><br><b style="color:var(--warn)">${t.tp1_price?.toFixed(2)}</b></div>
          <div><span style="color:var(--bull);">TP2 (${t.dist_to_tp2??'?'})</span><br><b style="color:var(--bull)">${t.tp2_price?.toFixed(2)}</b></div>
        </div>
        <div class="ot-foot">
          <div class="ot-pnl">
            <span style="font-size:11px;color:var(--muted);">P&L </span>
            <span style="font-weight:700;color:${pnlCol}">${t.unrealized_pnl!=null?pnlText(t.unrealized_pnl,{fixed:true,digits:2,prefix:'$'}):'–'}</span>
            <span style="font-size:11px;color:var(--muted);margin-left:6px;">(${t.unrealized_pips??'–'} pips)</span>
          </div>
          <div class="ot-prog">
            <span class="tp1mark" style="left:${Math.min(Math.max(tp1pct||0,0),100)}%;"></span>
            <i style="width:${Math.min(Math.max(progress||0,0),100)}%;background:${dirCol};"></i>
          </div>
        </div>
      </div>`;
    }).join('');
}


export { refreshCFDPaper };
