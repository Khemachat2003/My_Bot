// แผง Setup ทุกคู่เงิน — /api/setup/latest-all
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 3042–3082 แบบ move-only

import { _getExpandedSetup, _restoreExpandedSetup, renderSetupCompact } from './setupCards.js';
import { fetchJSON } from '../../shared/api/client.js';

async function refreshSetupMini(){
  try{
    const all=await fetchJSON('/api/setup/latest-all');
    const container=document.getElementById('setupMini');
    if(!container) return;
    const expanded=_getExpandedSetup();
    const order=['frxXAUUSD','frxEURUSD','frxGBPUSD','frxUSDJPY','frxAUDUSD','frxUSDCAD','frxUSDCHF','frxNZDUSD','R_100'];
    const sorted=Object.keys(all).sort((a,b)=>order.indexOf(a)-order.indexOf(b));
    const rows=[];
    for(const sym of sorted){
      const tfs=all[sym];
      const s=tfs['M5']||tfs['M1'];
      if(s) rows.push(renderSetupCompact({...s,symbol:sym}));
    }
    container.innerHTML=rows.length?rows.join(''):`<div class="empty" style="padding:16px;">รอ setup_feed.py ทำงาน</div>`;
    _restoreExpandedSetup(container,expanded);
  }catch(e){}
}

async function refreshSetupAll(){
  try{
    const all=await fetchJSON('/api/setup/latest-all');
    const m1El=document.getElementById('setupAllM1');
    const m5El=document.getElementById('setupAllM5');
    if(!m1El||!m5El) return;
    const expanded1=_getExpandedSetup(), expanded5=_getExpandedSetup();
    const order=['frxXAUUSD','frxEURUSD','frxGBPUSD','frxUSDJPY','frxAUDUSD','frxUSDCAD','frxUSDCHF','frxNZDUSD','R_100'];
    const sorted=Object.keys(all).sort((a,b)=>order.indexOf(a)-order.indexOf(b));
    const m1Cards=[], m5Cards=[];
    for(const sym of sorted){
      const tfs=all[sym];
      if(tfs['M5']) m5Cards.push(renderSetupCompact({...tfs['M5'],symbol:sym}));
      if(tfs['M1']) m1Cards.push(renderSetupCompact({...tfs['M1'],symbol:sym}));
    }
    m1El.innerHTML=m1Cards.length?m1Cards.join(''):`<div class="empty" style="padding:16px;">รอข้อมูล</div>`;
    m5El.innerHTML=m5Cards.length?m5Cards.join(''):`<div class="empty" style="padding:16px;">รอข้อมูล</div>`;
    _restoreExpandedSetup(m1El,expanded1);
    _restoreExpandedSetup(m5El,expanded5);
  }catch(e){}
}


export { refreshSetupAll, refreshSetupMini };
