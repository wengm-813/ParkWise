const $ = (id) => document.getElementById(id);
const escapeHTML = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let loading = false;
function updateClock(){ $('clock').textContent = new Date().toLocaleTimeString('zh-TW', {hour12:false}); }
setInterval(updateClock,1000); updateClock();

function showToast(message, ok){
 const el=$('toast'); el.className=`toast ${ok?'success':'error'}`; el.textContent=message;
}
function drawSpots(spots, zone){
 const el=$(`zone${zone}`); el.innerHTML='';
 for(const slot of spots.filter(s=>s.zone===zone)){
  const box=document.createElement('div');
  box.className=`parking-slot ${slot.occupied?'taken':'available'}`;
  box.title=slot.occupied?`${slot.id} · ${slot.plate}`:`${slot.id} · 可停車`;
  const symbol=document.createElement('span'); symbol.className='slot-icon'; symbol.textContent=slot.occupied?'🚘':'P';
  const number=document.createElement('strong'); number.textContent=slot.id;
  const state=document.createElement('small'); state.textContent=slot.occupied?slot.plate:'空位';
  box.append(symbol,number,state); el.appendChild(box);
 }
}
function drawEvents(events){
 const el=$('eventList');
 if(!events.length){el.innerHTML='<div class="empty-state">目前尚無車輛進出紀錄</div>';return;}
 el.innerHTML=events.map(e=>`<div class="event-item"><div class="event-symbol ${e.kind==='entry'?'event-in':'event-out'}">${e.kind==='entry'?'↗':'↙'}</div><div class="event-details"><strong>${escapeHTML(e.plate)}</strong><span>${e.kind==='entry'?'車輛入場':'車輛離場'} · ${escapeHTML(e.spot)} ${e.kind==='exit'?'· NT$ '+escapeHTML(e.fee):''}</span></div><span class="event-time">${escapeHTML(e.time)}</span></div>`).join('');
}
async function refresh(){
 if(loading)return; loading=true;
 try{
  const res=await fetch('/api/status',{cache:'no-store'}); if(!res.ok)throw Error(`HTTP ${res.status}`);
  const d=await res.json();
  $('capacity').textContent=d.capacity; $('free').textContent=d.free; $('occupied').textContent=d.occupied;
  $('revenue').textContent=`NT$ ${d.metrics.total_revenue??0}`;
  $('zoneAFree').textContent=d.zones.A.free; $('zoneBFree').textContent=d.zones.B.free;
  $('zoneABarText').textContent=`${d.zones.A.free} / ${d.zones.A.capacity}`;
  $('zoneBBarText').textContent=`${d.zones.B.free} / ${d.zones.B.capacity}`;
  $('occupiedLabel').textContent=`${d.occupied} / ${d.capacity}`;
  $('totalEntries').textContent=`${d.metrics.total_entries??0} 台`;
  $('totalExits').textContent=`${d.metrics.total_exits??0} 台`;
  $('fullDenied').textContent=`${d.metrics.full_denied??0} 次`;
  const percent=Math.round(100*d.occupied/d.capacity);
  $('usagePercent').textContent=`${percent}%`;
  $('donut').style.background=`conic-gradient(#10a889 0 ${percent}%, #e7eff1 ${percent}% 100%)`;
  drawSpots(d.spots,'A'); drawSpots(d.spots,'B'); drawEvents(d.events);
 }catch(err){$('connectionState').textContent='讀取資料失敗：'+err.message;}
 finally{loading=false;}
}
async function submitAction(path, plate, zone){
 try{
  const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plate,zone})});
  const data=await res.json(); showToast(data.message||data.code,!!data.ok);
  await refresh();return data.ok;
 }catch(err){showToast('連線失敗：'+err.message,false);return false;}
}
$('enterForm').addEventListener('submit',async e=>{
 e.preventDefault(); const btn=$('enterButton');btn.disabled=true;
 const ok=await submitAction('/api/enter',$('enterPlate').value.trim().toUpperCase(),$('enterZone').value);
 if(ok)$('enterPlate').value=''; btn.disabled=false;
});
$('exitForm').addEventListener('submit',async e=>{
 e.preventDefault(); const btn=$('exitButton');btn.disabled=true;
 const ok=await submitAction('/api/exit',$('exitPlate').value.trim().toUpperCase());
 if(ok)$('exitPlate').value='';btn.disabled=false;
});
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
 const isEnter=button.dataset.tab==='enter';
 document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b===button));
 $('enterForm').classList.toggle('hidden',!isEnter);
 $('exitForm').classList.toggle('hidden',isEnter);
 $('toast').className='toast hidden';
}));
function liveUpdates(){
 const stream=new EventSource('/api/live');
 stream.onopen=()=>{$('connectionState').textContent='即時同步已連接';};
 stream.onmessage=()=>refresh();
 stream.onerror=()=>{$('connectionState').textContent='即時連線重試中（仍會定期刷新）';};
}
liveUpdates(); refresh(); setInterval(refresh,5000);
