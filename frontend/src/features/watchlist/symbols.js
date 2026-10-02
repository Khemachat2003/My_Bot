// รายการสัญลักษณ์ — /api/symbols, /api/symbol
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 2660–2687 แบบ move-only

import { refreshPrice } from '../chart/index.js';
import { fetchJSON } from '../../shared/api/client.js';
import { renderWatchlist } from './watchlist.js';

const WL_SYMBOLS=[
  {symbol:'frxXAUUSD',label:'XAUUSD · ทองคำ'},
  {symbol:'frxEURUSD',label:'EURUSD'},
  {symbol:'frxGBPUSD',label:'GBPUSD'},
  {symbol:'frxUSDJPY',label:'USDJPY'},
  {symbol:'frxAUDUSD',label:'AUDUSD'},
  {symbol:'frxUSDCAD',label:'USDCAD'},
  {symbol:'frxUSDCHF',label:'USDCHF'},
  {symbol:'frxNZDUSD',label:'NZDUSD'},
];
let symbolList=WL_SYMBOLS;
let _symbolsLoaded=true;
async function loadSymbols(){
  try{
    const list=await fetchJSON('/api/symbols');
    if(Array.isArray(list)&&list.length) symbolList=list;
  }catch(e){}
  _symbolsLoaded=true;
  const sel=document.getElementById('chartSymbol');
  if(sel){
    let cur='frxXAUUSD';
    try{ const s=await fetchJSON('/api/symbol'); if(s&&s.symbol) cur=s.symbol; }catch(e){}
    sel.innerHTML=symbolList.map(s=>`<option value="${s.symbol}" ${s.symbol===cur?'selected':''}>${s.label}</option>`).join('');
    sel.addEventListener('change',()=>refreshPrice(true));   // ← user action → โชว์ loading
  }
  renderWatchlist();
}


export { loadSymbols, symbolList };
