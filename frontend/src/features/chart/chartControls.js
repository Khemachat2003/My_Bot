// toolbar กราฟ + วาง/ลบ S/R + เต็มจอ + รายการสัญญาณ
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2449–2611 แบบ move-only

import { lwCandle, lwChart, refreshLWResize } from './lwChartInit.js';
import { showToast } from '../../shared/ui/toast.js';

// ── S/R line ที่ผู้ใช้เพิ่มเอง ──
let _selLines=[];   // เส้น SL/TP ของ trade ที่เลือก
let _userSr=[];     // เส้น S/R ที่ผู้ใช้เพิ่ม
let _addingSr=false;
let _deletingSr=false;   // ← ต้องประกาศ! เดิมอ้างแต่ไม่เคย let — bindLWChart() เรียก _updSrHint() อ่านค่าตรงนี้แล้วระเบิด ReferenceError ก่อนสร้าง sub-pane
let _addingTimer=null;

function _clearPriceLines(){
  if(!lwCandle) return;
  try{ _selLines.forEach(u=>lwCandle.removePriceLine(u)); _selLines=[]; }catch(e){}
}
function _renderLWMarkers(markers){
  // สงวนไว้ (S/R handled ใน bindLWChart)
}

function _renderSrRows(){
  const rowsEl=document.getElementById('lwSrRows'); if(!rowsEl) return;
  rowsEl.innerHTML=_userSr.map((ln,i)=>{
    const price=(ln.price()!=null)?Number(ln.price()).toFixed(ln.price()>1000?1:2):'–';
    return `<div class="lw-trow" data-sr="${i}">
      <span class="dir" style="width:auto;color:#787B86;font-weight:400">S/R</span>
      <span class="sub">${price}</span>
      <button class="sr-del" data-sri="${i}" title="ลบเส้นนี้"><i class="ti ti-trash"></i></button>
    </div>`;
  }).join('') || '<div class="lw-empty">ยังไม่มีเส้น S/R</div>';
  rowsEl.querySelectorAll('.sr-del').forEach(btn=>{
    btn.addEventListener('click',e=>{
      e.stopPropagation();
      const i=Number(btn.dataset.sri);
      try{ if(lwCandle&&lwCandle.removePriceLine) lwCandle.removePriceLine(_userSr[i]); }catch(err){}
      _userSr.splice(i,1);
      _renderSrRows();
    });
  });
}

// ── helper โหมด S/R (ใช้ทั้งจาก toolbar และ subscribeClick) ──
function _updSrHint(){
  const h=document.getElementById('lwModeHint'); if(!h) return;
  h.textContent=_addingSr?'โหมดวางเส้น S/R — คลิกกราฟเพื่อวางเส้นแนวนอน':
                  _deletingSr?'โหมดลบเส้น S/R — คลิกใกล้เส้นที่จะลบ':'';
  h.style.display=(_addingSr||_deletingSr)?'block':'none';
}
function _setSrModeCls(){
  const w=document.getElementById('lwWrap'); if(!w) return;
  w.classList.toggle('adding-sr',!!_addingSr);
}
// ── เก็บเกี่ยวคลิกที่ปุ่มทั้งหมดด้วย event delegation (ไม่พึ่ง chart init — ปุ่มต้องใช้ได้เสมอ) ──
function bindChartToolbar(){
  if(window.__ctBound) return; window.__ctBound=true;
  document.addEventListener('click',e=>{
    const btn=e.target && e.target.closest ? e.target.closest('.chart-toolbar button, #lwSrPanel .sr-clear') : null;
    if(!btn) return;
    const id=btn.id;
    if(id==='addSrR'){
      _addingSr=btn.classList.toggle('active');
      if(_addingSr){ _deletingSr=false; const db=document.getElementById('btnDelSr'); if(db) db.classList.remove('active'); }
      else _setSrModeCls();
      _setSrModeCls();
      const cc=document.getElementById('candleChart'); if(cc) cc.style.cursor=_addingSr?'crosshair':'default';
      _updSrHint();
      return;
    }
    if(id==='btnDelSr'){
      _deletingSr=btn.classList.toggle('active');
      if(_deletingSr){ _addingSr=false; const ab=document.getElementById('addSrR'); if(ab) ab.classList.remove('active'); _setSrModeCls(); }
      const cc=document.getElementById('candleChart'); if(cc) cc.style.cursor=_deletingSr?'pointer':'default';
      _updSrHint();
      return;
    }
    if(id==='btnSrList'){
      const sp=document.getElementById('lwSrPanel');
      if(sp){ sp.style.display=sp.style.display==='none'?'block':'none'; if(sp.style.display==='block') _renderSrRows(); }
      return;
    }
    if(id==='srClearAll'){
      if(!lwCandle){ showToast('กราฟยังโหลดไม่เสร็จ'); return; }
      _userSr.forEach(ln=>{ try{ lwCandle.removePriceLine(ln); }catch(e){} });
      _userSr=[];
      _renderSrRows();
      _updSrHint();
      return;
    }
    if(id==='zoomReset'){
      if(lwChart) lwChart.timeScale().fitContent();
      else showToast('กราฟยังโหลดไม่เสร็จ');
      return;
    }
    if(id==='btnFullscreen'){
      const p=document.getElementById('chartPanel');
      if(document.fullscreenElement){ document.exitFullscreen(); return; }   // ← อยู่ในโหมดเต็มจอแล้ว → ออกแทน
      if(p&&p.requestFullscreen){
        const wrap=document.getElementById('lwWrap'); const prev=wrap&&wrap.style.height;
        if(wrap) wrap.style.height='calc(100vh - 130px)';
        p.requestFullscreen().then(()=>{ setTimeout(v=>refreshLWResize(),80); }).catch(()=>{ if(wrap&&prev) wrap.style.height=prev; });
      }
      return;
    }
    if(id==='btnTradeList'){
      const tl=document.getElementById('lwTradeList');
      if(tl){ const show=tl.style.display==='none'; tl.style.display=show?'block':'none'; if(show) tl.scrollIntoView({block:'nearest',behavior:'smooth'}); }
      return;
    }
  });
  document.addEventListener('fullscreenchange',()=>{
    const fsBtn=document.getElementById('btnFullscreen');
    const fsIcon=fsBtn?.querySelector('i'); const fsLbl=fsBtn?.querySelector('.btn-lbl');
    if(document.fullscreenElement){
      if(fsIcon) fsIcon.className='ti ti-minimize'; if(fsLbl) fsLbl.textContent='ย่อจอ';
    }else{
      if(fsIcon) fsIcon.className='ti ti-maximize'; if(fsLbl) fsLbl.textContent='เต็มจอ';
      const wrap=document.getElementById('lwWrap'); if(wrap) wrap.style.height='';
      refreshLWResize();
    }
  });
}

// ── bind LW chart controls (เฉพาะการคลิกวาง/ลบเส้นบนกราฟ) ──
function bindLWChart(){
  if(!lwChart) return;
  _setSrModeCls(); _updSrHint();
  // click เพื่อวาง / ลบ S/R
  lwChart.subscribeClick(param=>{
    if(!param.point || !lwCandle) return;
    if(_addingSr){
      const p=lwCandle.coordinateToPrice(param.point.y);
      if(p==null) return;
      try{
        const ln=lwCandle.createPriceLine({price:p,color:'#787B86',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dotted,title:'S/R'});
        _userSr.push(ln);
      }catch(e){}
      _addingSr=false;
      const b=document.getElementById('addSrR'); if(b) b.classList.remove('active');
      _setSrModeCls();
      const cc=document.getElementById('candleChart'); if(cc) cc.style.cursor='default';
      _updSrHint();
      const sp=document.getElementById('lwSrPanel');
      if(sp&&sp.style.display==='block') _renderSrRows();
      showToast('เพิ่มเส้น S/R ราคา '+p.toFixed(2));
      return;
    }
    if(_deletingSr){
      const p=lwCandle.coordinateToPrice(param.point.y);
      if(p==null) return;
      let bi=-1,bd=Infinity;
      _userSr.forEach((ln,i)=>{ const lp=ln.price(); if(lp!=null){ const d=Math.abs(lp-p); if(d<bd){bd=d;bi=i;} } });
      if(bi>=0 && bd<=Math.max(p*0.005,0.5)){ // ต้องคลิกห่างจากเส้นไม่เกิน ~0.5% หรือ 0.5 USD
        try{ lwCandle.removePriceLine(_userSr[bi]); }catch(e){}
        _userSr.splice(bi,1);
        showToast('ลบเส้น S/R แล้ว');
      } else showToast('ไม่พบเส้น S/R ใกล้จุดนี้ — คลิกให้ใกล้เส้นมากขึ้น');
      _deletingSr=false;
      const db=document.getElementById('btnDelSr'); if(db) db.classList.remove('active');
      const cc=document.getElementById('candleChart'); if(cc) cc.style.cursor='default';
      _updSrHint();
      const sp=document.getElementById('lwSrPanel');
      if(sp&&sp.style.display==='block') _renderSrRows();
      return;
    }
  });
}



export { _clearPriceLines, _renderLWMarkers, _selLines, bindChartToolbar, bindLWChart };
