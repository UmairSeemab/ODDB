(() => {
'use strict';

const API='api/release.php';
let payload=null;
let currentCounts=null;
let activeFilter='current';

const fmt=n=>Number(n||0).toLocaleString();
const esc=s=>String(s??'')
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
 .replaceAll('"','&quot;').replaceAll("'","&#039;");

function humanBytes(bytes){
 const n=Number(bytes||0);
 if(!n) return '—';
 const units=['B','KB','MB','GB','TB'];
 let value=n, i=0;
 while(value>=1024 && i<units.length-1){value/=1024;i++}
 const decimals=value>=10||i===0?0:1;
 return `${value.toFixed(decimals)} ${units[i]}`;
}

function releaseLabel(group){
 if(group==='current') return 'Current enrichment';
 if(group==='genetics') return 'Historical genetics core';
 if(group==='clinical') return 'Historical drug & clinical';
 return 'ODDB v1';
}

function renderOverview(){
 const c=currentCounts||{};
 const cards=[
  ['Diseases',c.disease],
  ['Genes',c.gene],
  ['Variants',c.variant],
  ['Drugs',c.drug],
  ['Clinical trials',c.clinical_trial],
  ['Clinical reports',c.clinical_report]
 ];
 document.getElementById('releaseOverview').innerHTML=cards.map(([label,value])=>`
  <div class="metric-card">
   <div class="metric-value">${fmt(value)}</div>
   <div class="metric-label">${esc(label)}</div>
  </div>`).join('');
}

function filteredFiles(){
 const q=document.getElementById('datasetSearch').value.trim().toLowerCase();
 return (payload?.files||[]).filter(file=>{
  if(activeFilter!=='all' && file.group!==activeFilter) return false;
  if(!q) return true;
  return [
   file.label,file.filename,file.description,file.format,file.release_name,file.db_table
  ].some(v=>String(v??'').toLowerCase().includes(q));
 });
}

function renderCatalog(){
 const files=filteredFiles();
 const box=document.getElementById('datasetCatalog');
 const empty=document.getElementById('noDatasets');

 if(!files.length){
  box.innerHTML='';
  empty.classList.remove('d-none');
  return;
 }

 empty.classList.add('d-none');

 box.innerHTML=files.map(file=>{
  const count=file.row_count!==null && file.row_count!==undefined
    ? fmt(file.row_count)
    : '—';

  return `
   <article class="dataset-card">
    <div class="dataset-card-head">
     <span class="dataset-type">${esc(file.format||'file')}</span>
     <span class="small text-secondary">${esc(releaseLabel(file.group))}</span>
    </div>
    <div class="dataset-name">${esc(file.label)}</div>
    <div class="dataset-file">${esc(file.filename)}</div>
    <div class="dataset-description">${esc(file.description||'Frozen ODDB v1 release file.')}</div>
    <div class="dataset-meta">
     <div><span>Rows</span><strong>${count}</strong></div>
     <div><span>Size</span><strong>${humanBytes(file.size_bytes)}</strong></div>
     <div><span>Release</span><strong>${esc(file.release_date||'—')}</strong></div>
     <div><span>Format</span><strong>${esc((file.format||'—').toUpperCase())}</strong></div>
    </div>
    ${file.sha256?`<details class="small mb-2"><summary>SHA256 checksum</summary><code style="overflow-wrap:anywhere">${esc(file.sha256)}</code></details>`:''}
    <div class="dataset-actions">
     <a class="btn btn-primary btn-sm"
        href="download.php?id=${encodeURIComponent(file.id)}">Download</a>
    </div>
   </article>`;
 }).join('');
}

function bind(){
 document.getElementById('datasetSearch').addEventListener('input',renderCatalog);
 document.querySelectorAll('[data-release-filter]').forEach(btn=>{
  btn.addEventListener('click',()=>{
   activeFilter=btn.dataset.releaseFilter;
   document.querySelectorAll('[data-release-filter]').forEach(b=>b.classList.toggle('active',b===btn));
   renderCatalog();
  });
 });
}

async function loadCurrent(){
 try{
  const r=await fetch('api/stats.php',{cache:'no-store'}),d=await r.json();
  if(!r.ok||!d.ok||!d.overview)throw new Error('Current release statistics unavailable');
  const o=d.overview;for(const k of ['diseases','genes','variants','drugs','trials','clinical_reports'])if(!Number.isInteger(o[k])||o[k]<0)throw new Error('Invalid current release counts');
  currentCounts={disease:o.diseases,gene:o.genes,variant:o.variants,drug:o.drugs,clinical_trial:o.trials,clinical_report:o.clinical_reports};
  renderOverview();
 }catch(_){document.getElementById('releaseOverview').innerHTML='<div class="alert alert-danger mb-0">Current release counts are temporarily unavailable. Historical file counts below describe their original snapshots.</div>';}
}
async function loadCatalog(){
 try{
  const r=await fetch(API,{cache:'no-store'}),d=await r.json();
  if(!r.ok||d.ok===false)throw new Error('Historical catalog unavailable');
  payload=d;renderCatalog();const n=(d.files||[]).length;
  const current=(d.files||[]).filter(f=>f.group==='current').length;
  document.getElementById('catalogStatus').textContent=`${fmt(current)} current enrichment files · ${fmt(n-current)} historical files`; 
 }catch(_){document.getElementById('datasetCatalog').innerHTML='';document.getElementById('noDatasets').classList.remove('d-none');document.getElementById('noDatasets').textContent='Historical release catalog is temporarily unavailable.';document.getElementById('catalogStatus').textContent='Historical catalog unavailable';}
}
async function load(){await Promise.allSettled([loadCurrent(),loadCatalog()]);}

document.addEventListener('DOMContentLoaded',()=>{bind();load()});
})();
