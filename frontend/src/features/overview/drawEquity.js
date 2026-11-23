// กราฟ Equity Curve ในแท็บภาพรวม — C-18: เจาะจง "วันนี้" (เที่ยงคืนท้องถิ่น)
// ประวัติทั้งหมด + เลือกช่วงย้อนหลังอยู่ที่แท็บผลงาน&บันทึก (#equityFullChart)
// Phase C-3 (design_system 5.1): เส้นเดียวสี --accent + fill เหนือฐาน --bull-dim / ใต้ฐาน --bear-dim
// C-18: baseline = ทุน "ตอนเริ่มวัน" (carry-in เมื่อวาน) → fill เขียว/แดง = บวก/ลบของวันนี้
// C-18: เลิก fitContent ทุกรอบ refresh — fit เฉพาะตอนข้อมูลวันนี้มาถึงครั้งแรก (0→n)
// C-19 (pro premium): clamp มุมมองรอบข้อมูลจริง (เหมือนกราฟราคาหลัก — เลื่อนแล้วไม่หลุดเข้าช่องว่าง)
//   + crosshair แบบ TradingView (เส้นประฟ้า + ป้ายแกน) + lastValueVisible ป้ายมูลค่าล่าสุดบนแกนขวา
//   + hover อ่านค่า (#eqHoverOv) + ปัดมือถือแนวตั้ง = สกรอลล์หน้า ไม่ขยับแกนราคา

import { _buildEqData, _eqBindClamp, _eqRangeStart, _eqSetLast, _eqSlice } from '../../shared/lib/equityData.js';

const ACCENT='#4C8DFF', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';

let lwEqChart=null, lwEqSeries=null, lwEqSeries2=null;
let lwEqBase=null, lwEqBase2=null; // base ปัจจุบันของแต่ละ series (เปลี่ยน → สร้างใหม่)
let _eqOvPrevN=0;                  // จำจำนวนเทรดวันนี้รอบก่อน → fit เฉพาะ 0→n
function drawEquity(payload){
  const el=document.getElementById('equityChart'); if(!el) return;
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const statsEl=document.getElementById('eqStatsOv');
  const emptyEl=document.getElementById('eqEmptyOv');
  if(!window.LightweightCharts) return;
  if(!lwEqChart){
    lwEqChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732'},
      // C-18: มุมมอง "วันนี้" ต้องเห็นเวลาในแกน (ไม่ใช่แค่วันที่ซ้ำกันทั้งแกน)
      timeScale:{borderColor:'#232732',rightOffset:2,timeVisible:true,secondsVisible:false},
      // C-19: crosshair พรีเมียมแบบ TradingView — เส้นประฟ้าจาง + ป้ายแกนสี accent
      crosshair:{
        mode:LightweightCharts.CrosshairMode.Normal,
        vertLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
        horzLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
      },
      // C-19: มือถือ — ปัดแนวตั้ง = สกรอลล์หน้าเว็บ (ไม่ขยับแกนราคา) · ปัดแนวนอนมีแรงเฉื่อน
      handleScroll:{mouseWheel:true,pressedMouseMove:true,horizTouchDrag:true,vertTouchDrag:false,kineticScroll:{touch:true,mouse:false}},
      handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true,axisDoubleClickReset:true},
    });
    _eqBindClamp(lwEqChart);   // C-19: เลื่อน/ซูม อยู่กับข้อมูลจริงเสมอ ไม่มีช่องว่าง
    window.addEventListener('resize',()=>{ if(lwEqChart&&el.clientWidth>0) lwEqChart.applyOptions({width:el.clientWidth}); });
  }
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  // ── C-18: ตัดเฉพาะวันนี้ + carry-in เป็นฐาน (บวก/ลบของวันนี้) ──
  const fromTs=_eqRangeStart('today');
  const oS=_eqSlice(b.optPts,fromTs), cS=_eqSlice(b.cfdPts,fromTs);
  const hasToday=oS.n+cS.n>0;
  const optDayBase=oS.carry!=null?oS.carry:b.optCapitalBase;
  const cfdDayBase=cS.carry!=null?cS.carry:b.cfdBase;
  // C-19: จำนวนจุดรวม (union เวลา CFD+Option) → ขอบเขตข้อมูลจริงของ clamp
  const unionTs=new Set();
  cS.pts.forEach(p=>unionTs.add(p.time));
  oS.pts.forEach(p=>unionTs.add(p.time));
  _eqSetLast(lwEqChart, unionTs.size);
  // สร้าง baseline series ใหม่เมื่อยังไม่มี หรือ base เปลี่ยน (เช่นข้ามวัน → carry เปลี่ยน)
  const mkSeries=(existing,curBase,prevBase,priceFmt)=>{
    if(existing&&prevBase===(curBase||0)) return existing;
    if(existing) lwEqChart.removeSeries(existing);
    return lwEqChart.addBaselineSeries({
      baseValue:{type:'price',price:curBase||0},
      lineColor:ACCENT, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM,
      topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM,
      bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      // C-19: ป้ายมูลค่าล่าสุดบนแกนขวา (เดิมปิด) — pro investor เห็นตัวเลขเด้งตลอด
      priceLineVisible:false, lastValueVisible:true, priceFormat:priceFmt,
    });
  };
  if(cS.n){
    lwEqSeries=mkSeries(lwEqSeries,cfdDayBase,lwEqBase,{type:'custom',formatter:p=>'$'+fmt(p)});
    lwEqBase=cfdDayBase||0;
  }
  if(oS.n){
    lwEqSeries2=mkSeries(lwEqSeries2,optDayBase,lwEqBase2,{type:'custom',formatter:p=>fmt(p)+' '+cur});
    lwEqBase2=optDayBase||0;
  }
  if(lwEqSeries) lwEqSeries.setData(cS.n?cS.pts:[]);
  if(lwEqSeries2) lwEqSeries2.setData(oS.n?oS.pts:[]);
  lwEqChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  // C-18: fit เฉพาะตอนข้อมูลวันนี้มาถึงครั้งแรก (0→n) — รอบถัดไปรักษา zoom/pan ผู้ใช้
  if(hasToday&&_eqOvPrevN===0) lwEqChart.timeScale().fitContent();
  _eqOvPrevN=oS.n+cS.n;
  // ── C-19: hover อ่านค่าตามเส้น (ผูกครั้งเดียว) — วันที่ · มูลค่า · ±จากทุนต้นวัน ──
  if(!lwEqChart.__eqHoverBound){
    lwEqChart.__eqHoverBound=true;
    lwEqChart.subscribeCrosshairMove(param=>{
      const hEl=document.getElementById('eqHoverOv'); if(!hEl) return;
      if(!param||param.time==null){ hEl.innerHTML=''; return; }
      const dTxt=new Date(param.time*1000).toLocaleString('th-TH',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
      const parts=[];
      const read=(ser,base,unit)=>{
        const pt=ser?param.seriesData.get(ser):null;
        if(!pt||pt.value==null) return;
        const pnl=pt.value-base;
        const cls=pnl>0?'eq-up':(pnl<0?'eq-dn':'');
        const val=unit==='cfd'?('$'+fmt(pt.value)):(fmt(pt.value)+' '+cur);
        parts.push(`<span class="${cls}">${unit==='cfd'?'CFD':'Option'} <b>${val}</b> (${pnl>=0?'+':''}${fmt(pnl)})</span>`);
      };
      read(lwEqSeries,lwEqBase||0,'cfd');
      read(lwEqSeries2,lwEqBase2||0,'opt');
      hEl.innerHTML=parts.length?`<span class="eq-h-time">${dTxt}</span>${parts.join('<span style="color:var(--border)"> · </span>')}`:'';
    });
  }
  if(emptyEl) emptyEl.style.display=hasToday?'none':'block';
  if(statsEl){
    // chips ขอบเขต "วันนี้" — P&L นับจากทุนตอนเริ่มวัน (carry-in) ไม่ใช่ทุนตั้งต้นตอนเปิดพอร์ต
    const pnlChip=(pnl,base)=>{
      if(pnl>0) return `<span class="eq-up">(+${fmt(pnl)} · +${(pnl/Math.max(base,1)*100).toFixed(1)}%)</span>`;
      if(pnl<0) return `<span class="eq-dn">(${fmt(pnl)} · ${(pnl/Math.max(base,1)*100).toFixed(1)}%)</span>`;
      return `<span>(0)</span>`;
    };
    const chips=['<span class="eq-scope">วันนี้</span>'];
    if(cS.n){
      const lastV=cS.pts[cS.pts.length-1].value, pnl=lastV-cfdDayBase;
      chips.push(`CFD <b>$${fmt(lastV)}</b> ${pnlChip(pnl,cfdDayBase)} · ${cS.n} เทรด`);
    }
    if(oS.n){
      const lastV=oS.pts[oS.pts.length-1].value, pnl=lastV-optDayBase;
      chips.push(`Option <b>${fmt(lastV)} ${cur}</b> ${pnlChip(pnl,optDayBase)} · ${oS.n} เทรด`);
    }
    if(chips.length===1) chips.push('ยังไม่มีเทรดที่จบวันนี้ — ดูประวัติทั้งหมดที่แท็บผลงาน&บันทึก');
    statsEl.innerHTML=chips.join('<span style="color:var(--border)"> | </span>');
  }
}


export { drawEquity };
