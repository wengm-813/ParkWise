const $ = id => document.getElementById(id);
async function load(){
 try{
  const res=await fetch('/api/status',{cache:'no-store'});const d=await res.json();
  $('adminOccupied').textContent=`${d.occupied} / ${d.capacity}`;
  $('adminEntries').textContent=d.metrics.total_entries??0;
  $('adminExits').textContent=d.metrics.total_exits??0;
  $('adminFull').textContent=d.metrics.full_denied??0;
  $('adminDuplicate').textContent=d.metrics.duplicate_denied??0;
  $('adminRevenue').textContent=`NT$ ${d.metrics.total_revenue??0}`;
 }catch(err){$('adminOccupied').textContent='無法連線';}
}
$('resetForm').addEventListener('submit',async e=>{
 e.preventDefault();
 if(!confirm('確定清除所有入場紀錄、營收與事件，並恢復 20 個空位？'))return;
 const tok=$('adminToken').value;
 try{
  const res=await fetch('/api/admin/reset',{method:'POST',headers:{'X-Admin-Token':tok}});
  const data=await res.json();const toast=$('adminToast');
  toast.className=`toast ${data.ok?'success':'error'}`;toast.textContent=data.message;
  if(data.ok){$('adminToken').value='';await load();}
 }catch(err){const el=$('adminToast');el.className='toast error';el.textContent='連線失敗：'+err.message;}
});
load();setInterval(load,5000);
