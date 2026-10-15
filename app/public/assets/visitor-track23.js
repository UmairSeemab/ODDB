/* Only an allowlisted page name is sent. No queries, entity searches, referrers or IDs. */
(()=>{'use strict';if(window.__oddbVisitor23)return;window.__oddbVisitor23=true;
if(navigator.doNotTrack==='1'||navigator.globalPrivacyControl===true)return;
const page=location.pathname.split('/').pop()||'index.php';
if(!['index.php','explore.php','statistics.php','documentation.php','data.php','contact.php'].includes(page))return;
function send(){if(document.visibilityState!=='visible')return;
document.removeEventListener('visibilitychange',send);
fetch('api/visitors23.php',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page}),credentials:'omit',referrerPolicy:'no-referrer',keepalive:true}).then(r=>{if(r.ok)window.dispatchEvent(new Event('oddb-visit23-recorded'));}).catch(()=>{});}
if(document.visibilityState==='visible')send();else document.addEventListener('visibilitychange',send);
})();
