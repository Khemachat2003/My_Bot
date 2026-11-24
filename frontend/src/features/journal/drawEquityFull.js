// กราฟ Equity Curve เต็มในแท็บ Journal — C-18/C-19/C-20
// Phase C-5 (design_system 5.1): mirror รูปแบบ C-3 — ไม่แตะ logic ข้อมูล (_buildEqData)
//
// C-18: ประวัติทั้งหมดเป็น default + ปุ่มช่วงย้อนหลัง วันนี้ / 7 วัน / 1 เดือน / 3 เดือน / ทั้งหมด
//        baseline = ทุน "ต้นช่วง" (carry-in) → fill เขียว/แดง = ±จากต้นช่วง · hover อ่านค่า · ไม่เด้ง zoom
// C-19: clamp มุมมองรอบข้อมูลจริง (ไม่มีช่องว่าง) + crosshair TradingView + ป้ายมูลค่าล่าสุด + resize observer
// C-20 (แก้จากสกรีนช็อตผู้ใช้ — สเกลปนหน่วย USD/THB ทำให้กราฟแบน อ่านไม่รู้เรื่อง):
//   · โหมด "ผลตอบแทน %" (default) = ทั้งสองเส้น normalize เป็น % จากต้นช่วง (เส้นฐาน 0%)
//     → เทียบข้ามหน่วยได้จริง เห็นทันทีว่าใครบวก/ลบเท่าไหร่ (มาตรฐานแอปพอร์ตมืออาชีพ)
//   · โหมด "มูลค่า" = มูลค่าจริง: CFD แกนขวา ($) / Option แกนซ้าย (THB) — แยกสเกล+หน่วยชัดเจน
//   · % ในชิปใช้ทุนต้นช่วงเป็นฐาน (เดิม capital≈1 THB → -30600% ที่ผู้ใช้เจอ) + guard ฐานเล็ก/ติดลบ
//   · โหมดจำใน localStorage ใช้ร่วมกับกราฟหน้าภาพรวม

import { _buildEqData, _eqBindClamp, _eqBindResize, _eqGetMode, _eqPctFmt, _eqPctOf, _eqPctPts, _eqRangeStart, _eqSetLast, _eqSetMode, _eqSlice } from '../../shared/lib/equityData.js';
import { pnlText } from '../../shared/lib/pnlText.js';

const CFD_COLOR='#4C8DFF', OPT_COLOR='#9C6FE0', DIM='#4C5566';
const BULL_FILL1='rgba(22,199,132,0.22)', BULL_FILL2='rgba(22,199,132,0.03)';
const BEAR_FILL1='rgba(240,70,92,0.03)',  BEAR_FILL2='rgba(240,70,92,0.22)';
const RANGE_LABEL={today:'วันนี้','7d':'7 วัน','30d':'1 เดือน','90d':'3 เดือน',all:'ทั้งหมด'};

let lwEqFullChart=null, lwEqFullSeries=null, lwEqFullSeries2=null;
let _eqFullCfgKey='';      // mode+base ที่สร้าง series อยู่ (เปลี่ยน → rebuild series)
let _eqFullRange='all';    // ช่วงที่เลือกอยู่ (default = ประวัติทั้งหมด)
let _eqFullPayload=null;   // cache payload → กดปุ่มช่วง/โหมดแล้ว redraw ได้ทันทีไม่ต้องรอ fetch
let _eqFullPrevN=0;        // จำจำนวนจุดรอบก่อน → fit เฉพาะ 0→n
let _eqFullBound=false;    // ผูกปุ่มครั้งเดียว
function _bindEqCtrl(){
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
  const mw=document.getElementById('eqModeBtns');
  if(mw){
    // sync ปุ่มโหมดกับค่าที่จำไว้ (default pct) ก่อนผูก event
    const cur=_eqGetMode();
    mw.querySelectorAll('[data-eqmode]').forEach(b=>b.classList.toggle('active',b.dataset.eqmode===cur));
    mw.addEventListener('click',e=>{
      const btn=e.target.closest('[data-eqmode]'); if(!btn) return;
      _eqSetMode(btn.dataset.eqmode);
      mw.querySelectorAll('[data-eqmode]').forEach(b=>b.classList.toggle('active',b===btn));
      // ล้าง cfgKey → บังคับสร้าง series ใหม่ตามโหมด แล้ว fit ให้เห็นภาพรวมทันที
      _eqFullCfgKey='';
      if(_eqFullPayload) drawEquityFull(_eqFullPayload,true);
    });
  }
}
// สร้าง series ตามโหมด: pct = CFD baseline ฐาน 0% + Option line (สอง fill ทับกันจะรก) ·
// value = CFD baseline 'right' ($) + Option baseline 'left' (THB) — แยกสเกลกัน
function _eqFullMkSeries(mode,cfdBase,optBase,cur,fmt){
  if(lwEqFullSeries){ try{ lwEqFullChart.removeSeries(lwEqFullSeries); }catch(e){} lwEqFullSeries=null; }
  if(lwEqFullSeries2){ try{ lwEqFullChart.removeSeries(lwEqFullSeries2); }catch(e){} lwEqFullSeries2=null; }
  const baseFmt={type:'custom',formatter:_eqPctFmt};
  if(mode==='pct'){
    lwEqFullSeries=lwEqFullChart.addBaselineSeries({
      baseValue:{type:'price',price:0},
      lineColor:CFD_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:true, priceFormat:baseFmt,
    });
    lwEqFullSeries2=lwEqFullChart.addLineSeries({
      color:OPT_COLOR, lineWidth:2, priceLineVisible:false, lastValueVisible:true, priceFormat:baseFmt,
    });
  } else {
    lwEqFullSeries=lwEqFullChart.addBaselineSeries({
      baseValue:{type:'price',price:cfdBase||0}, priceScaleId:'right',
      lineColor:CFD_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:BULL_FILL1, topFillColor2:BULL_FILL2,
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:BEAR_FILL1, bottomFillColor2:BEAR_FILL2,
      priceLineVisible:false, lastValueVisible:true, priceFormat:{type:'custom',formatter:p=>'$'+fmt(p)},
    });
    lwEqFullSeries2=lwEqFullChart.addBaselineSeries({
      baseValue:{type:'price',price:optBase||0}, priceScaleId:'left',
      lineColor:OPT_COLOR, lineWidth:2,
      topLineColor:DIM, topLineColor1:DIM, topFillColor1:'rgba(156,111,224,.18)', topFillColor2:'rgba(156,111,224,.03)',
      bottomLineColor:DIM, bottomLineColor1:DIM, bottomFillColor1:'rgba(0,0,0,0)', bottomFillColor2:'rgba(156,111,224,.16)',
      priceLineVisible:false, lastValueVisible:true, priceFormat:{type:'custom',formatter:p=>fmt(p)+' '+cur},
    });
  }
}
function drawEquityFull(payload, refit){
  const el=document.getElementById('equityFullChart'); if(!el) return;
  _eqFullPayload=payload||_eqFullPayload;
  _bindEqCtrl();
  const b=_buildEqData(payload&&payload.opt, payload&&payload.cfd);
  const cur=(payload&&payload.opt&&payload.opt.cur)||'THB';
  const fmt=p=>Number(p).toLocaleString('th-TH',{maximumFractionDigits:0});
  const emptyEl=document.getElementById('eqEmptyFull');
  const statsEl=document.getElementById('eqStatsFull');
  // ── C-18: ตัดตามช่วงที่เลือก + carry-in ต้นช่วงเป็นฐาน ──
  const fromTs=_eqRangeStart(_eqFullRange);
  const oS=_eqSlice(b.optPts,fromTs), cS=_eqSlice(b.cfdPts,fromTs);
  const mode=_eqGetMode();
  const isPct=mode==='pct';
  const optBase=oS.carry!=null?oS.carry:b.optCapitalBase;
  const cfdBase=cS.carry!=null?cS.carry:b.cfdBase;
  // ── C-20: ชุดข้อมูลตามโหมด ──
  const cData=isPct?_eqPctPts(cS.pts,cfdBase):cS.pts;
  const oData=isPct?_eqPctPts(oS.pts,optBase):oS.pts;
  const hasData=cData.length+oData.length>0;
  if(emptyEl) emptyEl.style.display=hasData?'none':'block';
  if(!window.LightweightCharts) return;
  if(!lwEqFullChart){
    lwEqFullChart=LightweightCharts.createChart(el,{
      height:el.clientHeight||260, width:el.clientWidth||300,
      layout:{background:{color:'transparent'},textColor:'#838B9C',fontFamily:'IBM Plex Mono, monospace'},
      grid:{vertLines:{color:'#1A1D27'},horzLines:{color:'#1A1D27'}},
      rightPriceScale:{borderColor:'#232732',minimumWidth:64},
      leftPriceScale:{visible:false,borderColor:'#232732',minimumWidth:64},
      timeScale:{borderColor:'#232732',rightOffset:6,timeVisible:true,secondsVisible:false},
      crosshair:{
        mode:LightweightCharts.CrosshairMode.Normal,
        vertLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
        horzLine:{color:'rgba(76,141,255,.55)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#2962FF'},
      },
      handleScroll:{mouseWheel:true,pressedMouseMove:true,horizTouchDrag:true,vertTouchDrag:false,kineticScroll:{touch:true,mouse:false}},
      handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true,axisDoubleClickReset:true},
    });
    _eqBindClamp(lwEqFullChart);
    _eqBindResize(lwEqFullChart, el);   // C-20: canvas พอดี container เสมอ (ป้ายแกนไม่ถูกตัด)
  }
  // C-19: จำนวนจุดรวม (union เวลา CFD+Option) → ขอบเขตข้อมูลจริงของ clamp
  const unionTs=new Set();
  cData.forEach(p=>unionTs.add(p.time));
  oData.forEach(p=>unionTs.add(p.time));
  _eqSetLast(lwEqFullChart, unionTs.size);
  // C-20: สร้าง/สร้างใหม่ series เมื่อโหมดหรือฐานเปลี่ยน
  const cfgKey=mode+'|'+cfdBase+'|'+optBase+'|'+cur;
  if(cfgKey!==_eqFullCfgKey){
    _eqFullMkSeries(mode,cfdBase,optBase,cur,fmt);
    _eqFullCfgKey=cfgKey;
  }
  lwEqFullChart.applyOptions({leftPriceScale:{visible:mode==='value'}});
  lwEqFullSeries&&lwEqFullSeries.setData(cData);
  lwEqFullSeries2&&lwEqFullSeries2.setData(oData);
  lwEqFullChart.applyOptions({width:el.clientWidth||300,height:el.clientHeight||260});
  // C-18: fit เฉพาะข้อมูลมาครั้งแรก (0→n) หรือผู้ใช้กดเปลี่ยนช่วง/โหมดเอง
  if(hasData&&(refit||_eqFullPrevN===0)) lwEqFullChart.timeScale().fitContent();
  _eqFullPrevN=cData.length+oData.length;
  // ── C-19/C-20: hover อ่านค่า — pct: %+มูลค่าจริง · value: มูลค่าจริง (ผูกครั้งเดียว) ──
  if(!lwEqFullChart.__eqHoverBound){
    lwEqFullChart.__eqHoverBound=true;
    lwEqFullChart.subscribeCrosshairMove(param=>{
      const hEl=document.getElementById('eqHoverFull'); if(!hEl) return;
      if(!param||param.time==null){ hEl.innerHTML=''; return; }
      const dTxt=new Date(param.time*1000).toLocaleString('th-TH',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
      const modeNow=_eqGetMode();
      const rows=[];
      const read=(ser,map,absBase,unit)=>{
        const pt=ser?param.seriesData.get(ser):null;
        if(!pt||pt.value==null) return;
        const label=unit==='cfd'?`<b style="color:${CFD_COLOR}">CFD</b>`:`<b style="color:${OPT_COLOR}">Option</b>`;
        if(modeNow==='pct'){
          const cls=pt.value>0?'eq-up':(pt.value<0?'eq-dn':'');
          let absTxt='';
          const abs=map.get(param.time);
          if(abs!=null){
            const pnl=abs-absBase;
            absTxt=` <span class="h-abs">(${unit==='cfd'?'$':''}${fmt(abs)}${unit==='cfd'?'':' '+cur} · ${pnl>=0?'+':''}${fmt(pnl)})</span>`;
          }
          rows.push(`${label} <span class="${cls}">${_eqPctFmt(pt.value)}</span>${absTxt}`);
        } else {
          const pnl=pt.value-absBase;
          const cls=pnl>0?'eq-up':(pnl<0?'eq-dn':'');
          rows.push(`${label} <span class="${cls}">${unit==='cfd'?'$':''}${fmt(pt.value)}${unit==='cfd'?'':' '+cur} (${pnl>=0?'+':''}${fmt(pnl)})</span>`);
        }
      };
      read(lwEqFullSeries,new Map(cS.pts.map(p=>[p.time,p.value])),cfdBase,'cfd');
      read(lwEqFullSeries2,new Map(oS.pts.map(p=>[p.time,p.value])),optBase,'opt');
      hEl.innerHTML=rows.length?`<span class="eq-h-time">${dTxt}</span>${rows.join('<span style="color:var(--border)"> · </span>')}`:'';
    });
  }
  if(statsEl){
    // C-20: ชิปสถิติ — ป้ายชื่อเส้นติดสีเส้นจริง · % ใช้ฐานต้นช่วง + guard ฐานเล็ก/ติดลบ (ไม่โชว์ % เพี้ยน)
    const chipPnl=(pnl,base)=>{
      const pc=_eqPctOf(pnl,base);
      const pctTxt=pc!=null?` · ${pc>0?'+':''}${pc.toFixed(1)}%`:'';
      if(pnl>0) return `<span class="eq-up">(${pnlText(pnl,{digits:0})}${pctTxt})</span>`;
      if(pnl<0) return `<span class="eq-dn">(${pnlText(pnl,{digits:0})}${pctTxt})</span>`;
      return `<span>(0)</span>`;
    };
    const chips=[`<span class="eq-scope">${RANGE_LABEL[_eqFullRange]||'ทั้งหมด'}</span>`];
    if(cS.n){
      const lastV=cS.pts[cS.pts.length-1].value, pnl=lastV-cfdBase;
      chips.push(`<b style="color:${CFD_COLOR}">CFD</b> $${fmt(lastV)} ${chipPnl(pnl,cfdBase)} · ${cS.n} เทรด`);
    }
    if(oS.n){
      const lastV=oS.pts[oS.pts.length-1].value, pnl=lastV-optBase;
      chips.push(`<b style="color:${OPT_COLOR}">Option</b> ${fmt(lastV)} ${cur} ${chipPnl(pnl,optBase)} · ${oS.n} เทรด`);
    }
    if(chips.length===1) chips.push('ช่วงนี้ยังไม่มีเทรดที่จบแล้ว — ลองเลือกช่วงกว้างขึ้น');
    statsEl.innerHTML=chips.join('<span class="eq-sep">|</span>');
  }
}


export { drawEquityFull };
