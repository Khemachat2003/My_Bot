// RSI / ADX / Fractal สำหรับ "วาดบนกราฟ" เท่านั้น
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1223, 1246–1308 แบบ move-only
// TODO: ย้ายไป backend — RSI/ADX/Fractal คำนวณซ้ำฝั่งหน้าเว็บเพื่อวาดกราฟ (สูตรอาจไม่ตรง backend/indicators.py)

// ── indicator helpers ──
function rsi(closes, period=14){
  const out=new Array(closes.length).fill(null);
  let g=0,l=0;
  for(let i=1;i<closes.length;i++){
    const ch=closes[i]-closes[i-1];
    if(i===period+1){
      let ag=0,al=0;
      for(let j=1;j<=period;j++){ const d=closes[j]-closes[j-1]; if(d>0)ag+=d; else al-=d; }
      g=ag/period; l=al/period;
    } else if(i>period+1){
      g=(g*(period-1)+Math.max(ch,0))/period;
      l=(l*(period-1)+Math.max(-ch,0))/period;
    } else continue;
    out[i]=l===0?100:100-100/(1+g/l);
  }
  return out;
}
function adx(h,l,c,period=14){
  const n=h.length, tr=new Array(n).fill(0), pdm=new Array(n).fill(0), ndm=new Array(n).fill(0);
  for(let i=1;i<n;i++){
    tr[i]=Math.max(h[i]-l[i],Math.abs(h[i]-c[i-1]),Math.abs(l[i]-c[i-1]));
    const up=h[i]-h[i-1], dn=l[i-1]-l[i];
    pdm[i]=(up>dn&&up>0)?up:0; ndm[i]=(dn>up&&dn>0)?dn:0;
  }
  const atr=new Array(n).fill(null), sp=new Array(n).fill(null), sn=new Array(n).fill(null);
  for(let i=period;i<n;i++){
    if(i===period){ let at=0,ap=0,an=0;
      for(let j=1;j<=period;j++){ at+=tr[j]; ap+=pdm[j]; an+=ndm[j]; }
      atr[i]=at/period; sp[i]=ap/period; sn[i]=an/period;
    } else {
      atr[i]=(atr[i-1]*(period-1)+tr[i])/period;
      sp[i]=(sp[i-1]*(period-1)+pdm[i])/period;
      sn[i]=(sn[i-1]*(period-1)+ndm[i])/period;
    }
  }
  const pdi=new Array(n).fill(null), ndi=new Array(n).fill(null), dx=new Array(n).fill(null);
  for(let i=period;i<n;i++){
    pdi[i]=atr[i]?100*sp[i]/atr[i]:0;
    ndi[i]=atr[i]?100*sn[i]/atr[i]:0;
    dx[i]=(pdi[i]+ndi[i])?100*Math.abs(pdi[i]-ndi[i])/(pdi[i]+ndi[i]):0;
  }
  const adxv=new Array(n).fill(null);
  for(let i=2*period-1;i<n;i++){
    if(i===2*period-1){ let acc=0; for(let j=period;j<=2*period-1;j++) acc+=dx[j]; adxv[i]=acc/period; }
    else adxv[i]=(adxv[i-1]*(period-1)+dx[i])/period;
  }
  return {adx:adxv, pdi, ndi};
}
function fractal(nd, l=7, r=7){
  // fractal: แท่งกลางต้องเป็นยอดสูง/ต่ำสุด โดยแท่งซ้าย l แท่งและขวา r แท่งต่ำ/สูงกว่า (ยอดแท่งที่ 8 ใน 15 แท่ง)
  const out=[];
  for(let i=l;i<nd.length-r;i++){
    let isH=true,isL=true;
    for(let j=i-l;j<=i+r;j++){ if(j===i) continue;
      if(nd[j].h>=nd[i].h) isH=false;
      if(nd[j].l<=nd[i].l) isL=false;
    }
    if(isH) out.push({i,v:nd[i].h,t:'H'});
    else if(isL) out.push({i,v:nd[i].l,t:'L'});
  }
  return out;
}


export { adx, fractal, rsi };
