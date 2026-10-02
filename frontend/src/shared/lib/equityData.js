// แปลงข้อมูล equity (journal + CFD paper) เป็นจุดกราฟ
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1996–2027 แบบ move-only
// TODO: ย้ายไป backend — ประกอบ equity curve (capital + equity*stake, cumulative pnl ของ CFD, base 5000) ฝั่งหน้าเว็บ

function _eqTS(t){
  if(t==null) return 0;
  if(typeof t==='number') return Math.floor(t);
  const s=String(t);
  const a=Math.floor(new Date(s.replace(' ','T')+'Z').getTime()/1000);
  return (Number.isFinite(a)&&a>0)?a:Math.floor(new Date(s.replace(' ','T')).getTime()/1000);
}

function _uniqueTimesAsc(pts){
  // lightweight-charts ต้องการแกนเวลาเป็นลำดับเพิ่มขึ้นแบบไม่ซ้ำ
  // เทรดที่จบในวินาทีเดียวกัน (burst) → time ซ้ำกัน → กราฟ crash "Value is null"
  let last=0;
  return pts.map(p=>{ const t=p.time; const time=t>last?t:last+1; last=time; return {time, value:p.value}; });
}

function _buildEqData(opt, cfd){
  const optPts=_uniqueTimesAsc(((opt&&opt.points)||[]).map(p=>({
    time:_eqTS(p.t),
    value:Math.round((opt.capital||0)+((p.equity||0)*(opt.stake||1))),
  })).filter(d=>d.time>0));
  let cum=0;
  const cfdPts=_uniqueTimesAsc(((cfd&&cfd.points)||[]).map(p=>{
    cum+=(p.pnl||0);
    return {time:_eqTS(p.exit_time||p.t), value:Math.round((cfd.base||0)+cum)};
  }).filter(d=>d.time>0));
  const optN=optPts.length, cfdN=cfdPts.length;
  const optCapitalBase=(opt&&opt.capital)||0, cfdBase=(cfd&&cfd.base)||0;
  const cfdPnl=cfdN?cfdPts[cfdPts.length-1].value-cfdBase:0;
  const optPnl=optN?optPts[optPts.length-1].value-optCapitalBase:0;
  return {optPts, cfdPts, optN, cfdN, optPnl, cfdPnl, optCapitalBase, cfdBase};
}


export { _buildEqData };
