// แจ้งเตือนสัญญาณ Setup ใหม่ (toast + Web Notification) — /api/signals?limit=5
// ย้ายจาก index.html เดิม (_archive/index.legacy.html) บรรทัด 1135–1146, 1164–1183 แบบ move-only

import { fetchJSON } from '../../shared/api/client.js';
import { showToast } from '../../shared/ui/toast.js';

// ── Web Notification: แจ้งเตือนเมื่อมีสัญญาณใหม่ ──
let _lastSignalId = 0;
let _notifGranted = false;

function requestNotifPermission(){
  if(!('Notification' in window)) return;
  if(Notification.permission === 'granted'){ _notifGranted = true; return; }
  if(Notification.permission !== 'denied'){
    Notification.requestPermission().then(p => { _notifGranted = (p === 'granted'); });
  }
}

async function checkNewSignals(){
  try {
    const rows = await fetchJSON('/api/signals?limit=5');
    if(!rows.length) return;
    const latest = rows[0];
    const id = latest.id || 0;
    if(_lastSignalId === 0){ _lastSignalId = id; return; }
    if(id > _lastSignalId){
      _lastSignalId = id;
      const src = latest.importance === 1 ? 'IMP1' : latest.importance === 2 ? 'IMP2' : 'RBF';
      const sym = (latest.symbol||'XAUUSD').replace('frx','');
      const msg = `${src} ${latest.direction} ${sym} @ ${latest.entry_price?.toFixed(2) || '–'} [${latest.tier||''}]`;
      showToast(msg, latest.direction);
      if(_notifGranted && Notification.permission === 'granted'){
        new Notification('Signal Alert', { body: msg, icon: '/favicon.ico' });
      }
    }
  } catch(e){}
}


export { checkNewSignals, requestNotifPermission };
