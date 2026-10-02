// แปลงแท่งเทียน + EMA/SMA/BB สำหรับวาด
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2195–2240 แบบ move-only
// TODO: ย้ายไป backend — EMA/SMA/Bollinger คำนวณฝั่งหน้าเว็บเพื่อวาดกราฟ

import { _candleTime } from './lwChartInit.js';

function _normLW(prices){
  return prices.map(d=>({
    time:_candleTime(d),
    open:d.o!=null?d.o:d.open,
    high:d.h!=null?d.h:d.high,
    low:d.l!=null?d.l:d.low,
    close:d.c!=null?d.c:d.close,
    volume:d.v!=null?d.v:d.volume||0,
  })).filter(d=>d.time>0&&d.open!=null);
}

function _emaArr(arr,n,key){
  const out=[]; let prev=null; const k=2/(n+1);
  for(const d of arr){
    const v=d.close;
    if(prev==null) prev=v; else prev=v*k+prev*(1-k);
    out.push({time:d.time,value:prev});
  }
  return out;
}

function _smaArr(arr,n){
  const out=[]; let sum=0;
  for(let i=0;i<arr.length;i++){
    sum+=arr[i].close;
    if(i>=n) sum-=arr[i-n].close;
    if(i>=n-1) out.push({time:arr[i].time,value:sum/n});
  }
  return out;
}

function _bbArr(arr,n,k){
  const u=[],m=[],l=[]; let sum=0,sum2=0;
  for(let i=0;i<arr.length;i++){
    const c=arr[i].close; sum+=c; sum2+=c*c;
    if(i>=n){ const oc=arr[i-n].close; sum-=oc; sum2-=oc*oc; }
    if(i>=n-1){
      const mean=sum/n, variance=Math.max(0,sum2/n-mean*mean), sd=Math.sqrt(variance);
      m.push({time:arr[i].time,value:mean});
      u.push({time:arr[i].time,value:mean+k*sd});
      l.push({time:arr[i].time,value:mean-k*sd});
    }
  }
  return {u,m,l};
}


export { _bbArr, _emaArr, _normLW, _smaArr };
