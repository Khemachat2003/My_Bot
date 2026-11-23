// กราฟ Equity Curve เต็มในแท็บ Journal — Phase C-5 (design_system 5.1): mirror รูปแบบ C-3 ทุกค่า
// เส้นเดียวสี accent + baseline series (fill เหนือฐาน bull / ใต้ฐาน bear, สร้าง series ใหม่เมื่อฐานเปลี่ยน)
// — ตัด createPriceLine เส้นฐานเดิม 2 เส้น (baseline series วาดเส้นฐานเอง) — ไม่แตะ logic ข้อมูล (_buildEqData)
//
// C-18 (pro investor upgrade — ตามผู้ใช้ขอ):
//   · ประวัติทั้งหมดเป็น default + ปุ่มเลือกช่วงย้อนหลัง วันนี้ / 7 วัน / 1 เดือน / 3 เดือน / ทั้งหมด
//   · baseline = ทุน "ต้นช่วง" (carry-in) → fill เขียว/แดง = ±จากต้นช่วงที่เลือก ไม่ใช่ตอนเปิดพอร์ต
//   · chips สถิติคิดตามช่วงที่เลือก (มูลค่าล่าสุด · ±P&L · ±% · จำนวนเทรด)
//   · hover crosshair อ่านค่าตามเส้น (วันที่ · มูลค่า · ±จากต้นช่วง) — แบบแพลตฟอร์มเทรด
//   · เลิก fitContent ทุกรอบ refresh (เดิมเด้งกลับทุก 5 วิ และ "การย่อกราฟเพี้ยน" ตามที่ผู้ใช้เจอ)
//     → fit เฉพาะ: ข้อมูลมาครั้งแรก (0→n) หรือผู้ใช้กดเปลี่ยนช่วงเอง (refit) — รอบ refresh รักษา zoom/pan

import { _buildEqData, _eqRangeStart, _eqSlice } from '../../shared/lib/equityData.js';
import { pnlText } from '../../shared/lib/pnlText.js';

const ACCENT='#4C8DFF', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';
const RANGE_LABEL={today:'วันนี้','7d':'7 วัน','30d':'1 เดือน','90d':'3 เดือน',all:'ทั้งหมด'};

let lwEqFullChart=null, lwEqFullSeries=null, lwEqFullSeries2=null;
let lwEqFullBase=null, lwEqFullBase2=null; // base ปัจจุบันของแต่ละ series (เปลี่ยน → สร้างใหม่)
let _eqFullRange='all';                     // ช่วงที่เลือกอยู่ (default = ประวัติทั้งหมด)
let _eqFullPayload=null;                    // cache payload ล่าสุด → กดปุ่มช่วงแล้ว redraw ได้ทันทีไม่ต้องรอ fetch
let _eqFullPrevN=0;                         // จำจำนวนเทรดรอบก่อน → fit เฉพาะ 0→n
let _eqFullBound=false;                     // ผูกปุ่มช่วงครั้งเดียว
function _bindEqRange(){
  if(_eqFullBound) return;
  const wrap=document.getElementById('eqRangeBtns'); if(!wrap) return;
  _eqFullBound=true;
  wrap.addEventListener('click',e=>{
    const btn=e.target.closest('[data-eqrange]'); if(!btn) return;
    if(_eqFullRange===btn.dataset.eqrange) return;
    _eqFullRange=btn.dataset.eqrange;
    wrap.querySelectorAll('[data-eqrange]').forEach(b=>b.classList.toggle('active',b===btn));
    if(_eqFullPayload) drawEquityFull(_eqFullPayload,true);   // ผู้ใช้กดเอง → fit ช่วงใหม่
  });
}
function drawEquityFull(payload, refit){
  const el=document.getElementById('equityFullChart'); if(!el) return;
  _eqFullPayload=payload||_eqFullPayload;
  _bindEqRange();
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  const emptyEl=document.getElementById('eqEmptyFull');
  const statsEl=document.getElementById('eqStatsFull');
  // ── C-18: ตัดตามช่วงที่เลือก + carry-in ต้นช่วงเป็นฐาน baseline ──
  const fromTs=_eqRangeStart(_eqFullRange);
  const oS=_eqSlice(b.optPts,fromTs), cS=_eqSlice(b.cfdPts,fromTs);
  const hasData=oS.n+cS.n>0;
  const optBase=oS.carry!=null?oS.carry:b.optCapitalBase;
  const cfdBase=cS.carry!=null?cS.carry:b.cfdBase;
  if(emptyEl) emptyEl.style.display=hasData?'none':'block';
  if(!window.LightweightCharts) return;
  if(!lwEqFullChart){
    lwEqFullChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732'},
      // C-18: ช่วงสั้น (วันนี้/7 วัน) ต้องเห็นเวลาในแกน ไม่ใช่วันที่เดียวกันทั้งแกน
      timeScale:{borderColor:'#232732',rightOffset:2,timeVisible:true,secondsVisible:false},
    });
    window.addEventListener('resize',()=>{ if(lwEqFullChart&&el.clientWidth>0) lwEqFullChart.applyOptions({width:el.clientWidth}); });
  }
  // สร้าง baseline series ใหม่เมื่อยังไม่มี หรือ base (ต้นช่วง) เปลี่ยน — baseline series วาดเส้นฐานเอง
  const mkSeries=(existing,curBase,prevBase,priceFmt)=>{
    if(existing&&prevBase===(curBase||0)) return existing;
    if(existing) lwEqFullChart.removeSeries(existing);
    return lwEqFullChart.addBaselineSeries({
      baseValue:{type:'price',price:curBase||0},
      lineColor:ACCENT, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM,
      topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM,
      bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:false, priceFormat:priceFmt,
    });
  };
  if(cS.n){
    lwEqFullSeries=mkSeries(lwEqFullSeries,cfdBase,lwEqFullBase,{type:'custom',formatter:p=>'$'+fmt(p)});
    lwEqFullBase=cfdBase||0;
  }
  if(oS.n){
    lwEqFullSeries2=mkSeries(lwEqFullSeries2,optBase,lwEqFullBase2,{type:'custom',formatter:p=>fmt(p)+' '+cur});
    lwEqFullBase2=optBase||0;
  }
  if(lwEqFullSeries) lwEqFullSeries.setData(cS.n?cS.pts:[]);
  if(lwEqFullSeries2) lwEqFullSeries2.setData(oS.n?oS.pts:[]);
  lwEqFullChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  // C-18: fit เฉพาะข้อมูลมาครั้งแรก (0→n) หรือผู้ใช้กดเปลี่ยนช่วงเอง — รอบ refresh รักษา zoom/pan
  if(hasData&&(refit||_eqFullPrevN===0)) lwEqFullChart.timeScale().fitContent();
  _eqFullPrevN=oS.n+cS.n;
  // ── C-18: hover crosshair อ่านค่า — วันที่ · มูลค่า · ±จากต้นช่วง (ผูกครั้งเดียว) ──
  if(!lwEqFullChart.__eqHoverBound){
    lwEqFullChart.__eqHoverBound=true;
    lwEqFullChart.subscribeCrosshairMove(param=>{
      const hEl=document.getElementById('eqHoverFull'); if(!hEl) return;
      if(!param||param.time==null){ hEl.innerHTML=''; return; }
      const d=new Date(param.time*1000);
      const dTxt=d.toLocaleString('th-TH',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
      const parts=[];
      const read=(ser,base,unit)=>{
        const pt=ser?param.seriesData.get(ser):null;
        if(!pt||pt.value==null) return;
        const pnl=pt.value-base;
        const cls=pnl>0?'eq-up':(pnl<0?'eq-dn':'');
        parts.push(`<span class="${cls}">${unit==='cfd'?'CFD':'Option'} <b>${unit==='cfd'?'$':''}${fmt(pt.value)}${unit==='cfd'?'':' '+cur}</b> (${pnlText(pnl,{digits:0})})</span>`);
      };
      read(lwEqFullSeries,lwEqFullBase||0,'cfd');
      read(lwEqFullSeries2,lwEqFullBase2||0,'opt');
      hEl.innerHTML=parts.length?`<span class="eq-h-time">${dTxt}</span>${parts.join('<span style="color:var(--border)"> · </span>')}`:'';
    });
  }
  if(statsEl){
    // chips: P&L คู่เครื่องหมาย + ศูนย์ไม่ติด eq-up (5.3) — C-18: คิดตามช่วงที่เลือก
    const chipPnl=(pnl,base)=>{
      const pct=(pnl/Math.max(base||1,1)*100).toFixed(1);
      if(pnl>0) return `<span class="eq-up">(${pnlText(pnl,{digits:0})} · +${pct}%)</span>`;
      if(pnl<0) return `<span class="eq-dn">(${pnlText(pnl,{digits:0})} · ${pct}%)</span>`;
      return `<span>(${pnlText(pnl,{digits:0})})</span>`;
    };
    const chips=[`<span class="eq-scope">${RANGE_LABEL[_eqFullRange]||'ทั้งหมด'}</span>`];
    if(cS.n){
      const lastV=cS.pts[cS.pts.length-1].value, pnl=lastV-cfdBase;
      chips.push(`CFD <b>$${fmt(lastV)}</b> ${chipPnl(pnl,cfdBase)} · ${cS.n} เทรด`);
    }
    if(oS.n){
      const lastV=oS.pts[oS.pts.length-1].value, pnl=lastV-optBase;
      chips.push(`Option <b>${fmt(lastV)} ${cur}</b> ${chipPnl(pnl,optBase)} · ${oS.n} เทรด`);
    }
    if(chips.length===1) chips.push('ช่วงนี้ยังไม่มีเทรดที่จบแล้ว — ลองเลือกช่วงกว้างขึ้น');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquityFull };
