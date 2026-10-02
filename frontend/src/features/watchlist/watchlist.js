// Watchlist ราคาล่าสุด — /api/watchlist
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2688–2726 แบบ move-only

import { refreshPrice } from '../chart/index.js';
import { fetchJSON } from '../../shared/api/client.js';
import { symbolList } from './symbols.js';

const _wlCache={};
function renderWatchlist(){
  const rowsEl=document.getElementById('watchlistRows'); if(!rowsEl) return;
  const cur=document.getElementById('chartSymbol')?.value||'frxXAUUSD';
  const short=s=>s.replace(/^frx/,'').replace(/_/g,'');
  rowsEl.innerHTML=symbolList.map(s=>{
    const c=_wlCache[s.symbol];
    const price=c?c.price:null;
    const chgPct=c?c.chgPct:null;
    const cls=chgPct==null?'flat':(chgPct>=0?'up':'down');
    const active=s.symbol===cur?'active':'';
    return `<div class="wl-row ${active}" data-symbol="${s.symbol}">
      <span><span class="wl-name">${short(s.symbol)}</span><span class="wl-kind">${s.label||''}</span></span>
      <span class="wl-price">${price!=null?price.toFixed(price>=1000?1:(price>=100?2:3)):'–'}</span>
      <span class="wl-chg ${cls}">${chgPct!=null?(chgPct>=0?'+':'')+chgPct.toFixed(2)+'%':''}</span>
    </div>`;
  }).join('');
  rowsEl.querySelectorAll('.wl-row').forEach(row=>{
    row.addEventListener('click',()=>{
      const sel=document.getElementById('chartSymbol'); if(sel) sel.value=row.dataset.symbol;
      rowsEl.querySelectorAll('.wl-row').forEach(r=>r.classList.toggle('active',r===row));
      refreshPrice(true);   // ← user action → โชว์ loading
    });
  });
}
async function refreshWatchlist(){
  renderWatchlist();
  // 1 request ต่อรอบ (เดิมยิง /api/candles 8 ครั้ง = 8 requests ทุก 5 วิ → VPS 1 vCPU ค้าง)
  try{
    const list=symbolList.map(s=>s.symbol).join(',');
    const rows=await fetchJSON('/api/watchlist?symbols='+encodeURIComponent(list));
    if(Array.isArray(rows)) for(const r of rows){
      if(!r||!r.symbol||r.price==null) continue;
      _wlCache[r.symbol]={price:r.price,chgPct:r.chgPct};
    }
  }catch(e){ /* ค้างไว้ที่ราคาเดิม ดีกว่าหายทั้งหมด */ }
  renderWatchlist();
}


export { refreshWatchlist, renderWatchlist };
