/* ODDB filter-aware drug comparison v0.7.9. Loaded graph evidence only. */
(() => {
 'use strict';
 const get=id=>document.getElementById(id),E=()=>window.ODDBEvidence;
 const xml=v=>String(v??'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&apos;');
 const clean=v=>v===null||v===undefined?'':String(v).trim(),unique=items=>[...new Set(items.filter(Boolean))].sort((a,b)=>a.localeCompare(b)),clone=v=>JSON.parse(JSON.stringify(v));
 const DRUG=/^drug::[A-Za-z0-9:._-]+$/,DISEASE=/^disease::[A-Za-z0-9:._-]+$/;
 const TYPES={direct_disease_drug:'Direct therapeutic evidence',drug_target:'Molecular target',target_overlap_only:'Target-overlap discovery',drug_trial:'Trial investigation',drug_report:'Clinical report link'};
 const EXPORTS=['drugComparisonCSV','drugComparisonEvidenceCSV','drugComparisonSVG','drugComparisonPrint'];
 let state=empty(),validated=null,validatedKey='',model=null,pending=false,serial=0,lastError='',pickerKey='',viewKey='';
 function empty(){return {version:1,drugIds:[],diseaseId:''};}
 function normalise(raw){
  if(raw===undefined||raw===null)return empty();
  if(typeof raw!=='object'||Array.isArray(raw)||raw.version!==1||!Array.isArray(raw.drugIds)||raw.drugIds.length>5||raw.drugIds.some(id=>typeof id!=='string'||id.length>180||!DRUG.test(id))||new Set(raw.drugIds).size!==raw.drugIds.length||typeof raw.diseaseId!=='string'||raw.diseaseId.length>180||(raw.diseaseId!==''&&!DISEASE.test(raw.diseaseId)))throw new Error('The saved drug comparison selection is invalid.');
  return {version:1,drugIds:[...raw.drugIds],diseaseId:raw.diseaseId};
 }
 function snapshot(){return normalise(state);}
 function restore(raw){state=normalise(raw);serial++;pending=false;lastError='';if(raw===undefined||raw===null){validated=null;validatedKey='';}model=null;viewKey='';pickerKey='';}
 function seed(response){if(!Array.isArray(response?.nodes)||!Array.isArray(response?.edges)||!response.metadata?.validated_at)return;validated=response;validatedKey=graphKey();lastError='';viewKey='';sync();}
 function validateState(raw,nodes){const s=normalise(raw),ids=new Set(nodes.map(n=>n.id)),issues=[];for(const id of [...s.drugIds,...(s.diseaseId?[s.diseaseId]:[])])if(!ids.has(id))issues.push({kind:'drug_comparison',id,status:'unavailable',reason:'This saved comparison entity is absent from the validated graph. It remains selected so you can review or remove it.'});return {state:s,issues};}
 function graphData(){return {nodes:cy.nodes().map(n=>({data:{...n.data()},layerHidden:n.hasClass('layer-hidden')})),edges:cy.edges().map(e=>({data:{...e.data()},layerHidden:e.hasClass('layer-hidden')})),layerVisibility:{...layerVisibility}};}
 function graphKey(graph=graphData()){return JSON.stringify({nodes:graph.nodes.map(n=>n.data).sort((a,b)=>a.id.localeCompare(b.id)),edges:graph.edges.map(e=>e.data).sort((a,b)=>a.id.localeCompare(b.id))});}
 function refLinks(record,node){
  const links=[],pmids=unique(clean(record.pmid).split(/[|;,\s]+/).filter(v=>/^\d+$/.test(v)));
  for(const p of pmids)links.push({label:'PMID '+p,url:'https://pubmed.ncbi.nlm.nih.gov/'+p+'/'});
  for(const doi of unique(clean(record.doi).split(/\s*\|\s*/).filter(v=>/^10\.\d{4,9}\/\S+$/i.test(v))))links.push({label:'DOI '+doi,url:'https://doi.org/'+encodeURIComponent(doi)});
  for(const value of unique([clean(record.nct_id),clean(node?.nct_id),clean(node?.label),clean(node?.entity_id),clean(record.source_id)]))if(/^NCT\d{8}$/i.test(value))links.push({label:value.toUpperCase(),url:'https://clinicaltrials.gov/study/'+value.toUpperCase()});
  return [...new Map(links.map(l=>[l.url,l])).values()];
 }
 function buildModel(response,graph,raw,filters){
  const selection=normalise(raw),s=E().normalise(filters),liveNodes=new Map(graph.nodes.map(n=>[n.data.id,n])),liveEdges=new Map(graph.edges.map(e=>[e.data.id,e])),nodes=new Map(response.nodes.map(n=>[n.id,n]));
  const allowed=response.edges.filter(d=>{const live=liveEdges.get(d.id);return live&&!live.layerHidden&&live.data.type===d.type&&live.data.source===d.source&&live.data.target===d.target&&nodes.has(d.source)&&nodes.has(d.target)&&liveNodes.has(d.source)&&liveNodes.has(d.target)&&!liveNodes.get(d.source).layerHidden&&!liveNodes.get(d.target).layerHidden&&E().matches(d,s);});
  const diseaseName=id=>nodes.get(id)?.label||id,scope=selection.diseaseId,scopeOK=!scope||(nodes.has(scope)&&liveNodes.has(scope));
  const issues=[...(Array.isArray(response.issues)?response.issues:[]),...validateState(selection,response.nodes).issues];
  const contextTrials=new Set(allowed.filter(e=>e.type==='disease_trial'&&e.source===scope).map(e=>e.target)),contextReports=new Set(allowed.filter(e=>e.type==='disease_report'&&e.source===scope).map(e=>e.target));
  const evidence=[];
  const columns=selection.drugIds.map(id=>{
   const node=nodes.get(id),present=!!(node&&liveNodes.has(id)),available=present&&scopeOK;
   const all=available?allowed.filter(e=>e.source===id||e.target===id):[];
   const grouped={direct:[],targets:[],overlap:[],trials:[],reports:[]};
   for(const d of all){if(d.type==='direct_disease_drug'&&d.target===id&&(!scope||d.source===scope))grouped.direct.push(d);else if(d.type==='drug_target'&&d.source===id)grouped.targets.push(d);else if(d.type==='target_overlap_only'&&d.target===id&&(!scope||d.source===scope))grouped.overlap.push(d);else if(d.type==='drug_trial'&&d.source===id&&(!scope||contextTrials.has(d.target)))grouped.trials.push(d);else if(d.type==='drug_report'&&d.source===id&&(!scope||contextReports.has(d.target)))grouped.reports.push(d);}
   const relevant=Object.values(grouped).flat(),rows=[];
   for(const d of relevant){
    const target=nodes.get(d.target),source=nodes.get(d.source);
    for(const record of E().matchingRecords(d,s)){
     const primary=Array.isArray(d.evidence_rows)&&d.evidence_rows.length>0,row={drug_id:node.entity_id,drug_label:node.label,relationship_id:d.id,relationship_type:d.type,category:TYPES[d.type],source_entity_id:d.source,source_entity_label:source?.label||d.source,target_entity_id:d.target,target_entity_label:target?.label||d.target,source_name:clean(record.source_name??(record===d?d.source_name??d.evidence_sources:record.source)),source_record_id:clean(record.source_id),pmid:clean(record.pmid),doi:clean(record.doi),evidence_class:clean(record.evidence_class),evidence_strength_class:clean(record.evidence_strength_class),association_evidence_class:primary?clean(d.evidence_class):'',association_evidence_strength_class:primary?clean(d.evidence_strength_class):'',evidence_subtype:clean(record.evidence_subtype),evidence_status:clean(record.evidence_status),overall_status:clean(d.overall_status),phase:clean(d.phase),action_type:clean(record.action_type??d.action_type),mechanism_of_action:clean(record.mechanism_of_action??d.mechanism_of_action),links:refLinks(record,target)};
     rows.push(row);evidence.push(row);
    }
   }
   const targetNodes=unique(grouped.targets.map(e=>e.target)).map(key=>nodes.get(key)),trialNodes=unique(grouped.trials.map(e=>e.target));
   const directRows=rows.filter(r=>r.relationship_type==='direct_disease_drug');
   const recorded=unique(directRows.map(r=>r.evidence_class).concat(directRows.map(r=>r.association_evidence_class))),strength=unique(directRows.map(r=>r.evidence_strength_class).concat(directRows.map(r=>r.association_evidence_strength_class)));
   const statuses=unique(grouped.trials.map(e=>clean(e.overall_status)||'Not recorded')),phases=unique(grouped.trials.map(e=>clean(e.phase)||'Not recorded'));
   return {id,entityId:node?.entity_id||id.slice(6),label:node?.label||id,available,present,hidden:!!liveNodes.get(id)?.layerHidden,stage:available?(clean(node.subtitle)||'Not recorded'):'Unavailable',direct:grouped.direct.length,directDiseases:unique(grouped.direct.map(e=>diseaseName(e.source))),directRecords:directRows.length,recorded,strength,sources:unique(rows.map(r=>r.source_name||'Not recorded')),directSources:unique(directRows.map(r=>r.source_name||'Not recorded')),targets:targetNodes.map(n=>n.label||n.id),sharedTargets:[],overlap:grouped.overlap.length,overlapDiseases:unique(grouped.overlap.map(e=>diseaseName(e.source))),trials:trialNodes.length,trialLabels:trialNodes.map(key=>nodes.get(key)?.label||key),statuses,phases,reports:unique(grouped.reports.map(e=>e.target)).length,reportLabels:unique(grouped.reports.map(e=>nodes.get(e.target)?.label||e.target)),records:rows,targetIds:targetNodes.map(n=>n.id)};
  });
  const targetCounts=new Map();for(const c of columns)for(const id of c.targetIds)targetCounts.set(id,(targetCounts.get(id)||0)+1);
  for(const c of columns)c.sharedTargets=c.targetIds.filter(id=>targetCounts.get(id)>1).map(id=>nodes.get(id)?.label||id);
  return {version:'0.7.9',createdAt:new Date().toISOString(),scope:'Validated, filter-matching, layer-visible relationships loaded in the graph',context:scope?diseaseName(scope):'All loaded diseases',selection,filters:s,layerVisibility:graph.layerVisibility?clone(graph.layerVisibility):null,filterDescription:E().describe(s),metadata:{...response.metadata},issues,columns,evidence};
 }
 const list=values=>values.length?values.join('; '):'Not recorded';
 function tableRows(m){
  const count=(c,n,details)=>c.available?[String(n),...(details?.length?[list(details)]:[])]:['Unavailable'];
  return [
   {section:'Drug information'},
   {label:'Recorded maximum clinical stage',values:m.columns.map(c=>[c.stage])},
   {section:'Direct therapeutic evidence'},
   {label:'Loaded direct relationships',values:m.columns.map(c=>count(c,c.direct,c.directDiseases))},
   {label:'Matching direct evidence records',values:m.columns.map(c=>count(c,c.directRecords))},
   {label:'Recorded evidence classes',values:m.columns.map(c=>[c.available?list(c.recorded):'Unavailable'])},
   {label:'Recorded evidence strength',values:m.columns.map(c=>[c.available?list(c.strength):'Unavailable'])},
   {label:'Direct evidence sources',values:m.columns.map(c=>[c.available?list(c.directSources):'Unavailable'])},
   {section:'Molecular targets and discovery'},
   {label:'Loaded molecular targets (disease independent)',values:m.columns.map(c=>count(c,c.targets.length,c.targets))},
   {label:'Targets shared by compared drugs',values:m.columns.map(c=>count(c,c.sharedTargets.length,c.sharedTargets))},
   {label:'Target-overlap relationships (discovery only)',values:m.columns.map(c=>count(c,c.overlap,c.overlapDiseases))},
   {section:'Clinical investigation and reports'},
   {label:'Distinct loaded trial entities',values:m.columns.map(c=>count(c,c.trials,c.trialLabels))},
   {label:'Recorded trial status',values:m.columns.map(c=>[c.available?list(c.statuses):'Unavailable'])},
   {label:'Recorded trial phase',values:m.columns.map(c=>[c.available?list(c.phases):'Unavailable'])},
   {label:'Distinct loaded report entities',values:m.columns.map(c=>count(c,c.reports,c.reportLabels))},
   {section:'Provenance'},
   {label:'All matching sources',values:m.columns.map(c=>[c.available?list(c.sources):'Unavailable'])}
  ];
 }
 function tableHTML(m){return '<table class="dc-table"><caption class="visually-hidden">Drug comparison using current loaded graph evidence</caption><thead><tr><th scope="col">Evidence category</th>'+m.columns.map(c=>`<th scope="col">${xml(c.label)}<small>${xml(c.entityId)}${c.hidden?' · Hidden layer':''}</small></th>`).join('')+'</tr></thead><tbody>'+tableRows(m).map(row=>row.section?`<tr class="dc-section"><th colspan="${m.columns.length+1}">${xml(row.section)}</th></tr>`:`<tr><th scope="row">${xml(row.label)}</th>${row.values.map(v=>'<td>'+v.map((text,i)=>i===0&&v.length>1?`<strong>${xml(text)}</strong>`:`<p>${xml(text)}</p>`).join('')+'</td>').join('')}</tr>`).join('')+'</tbody></table>';}
 function detailHTML(m,limit=Infinity){return m.columns.map(c=>`<details><summary>${xml(c.label)} · ${c.records.length} matching provenance record(s)</summary>${c.records.length?'<ol class="dc-evidence-list">'+c.records.slice(0,limit).map(r=>`<li><strong>${xml(r.category)}</strong> · ${xml(r.source_entity_label)} → ${xml(r.target_entity_label)}<br>${xml(r.source_name||'Source not recorded')}${r.source_record_id?' · '+xml(r.source_record_id):''}<br>${xml(unique([r.evidence_class,r.evidence_strength_class,r.association_evidence_class,r.association_evidence_strength_class]).join(' · ')||'Class not recorded')}${r.overall_status?' · '+xml(r.overall_status):''}${r.links.length?'<br>'+r.links.map(l=>`<a href="${xml(l.url)}" target="_blank" rel="noopener noreferrer">${xml(l.label)}</a>`).join(' · '):''}</li>`).join('')+'</ol>':'<p>No matching provenance records in this loaded scope.</p>'}${c.records.length>limit?'<p>Showing first '+limit+' records. Download Evidence CSV for the complete table.</p>':''}</details>`).join('');}
 function issueHTML(m,limit=Infinity){return '<details><summary>Graph validation issues · '+m.issues.length+'</summary><ul>'+m.issues.slice(0,limit).map(issue=>'<li>'+xml([issue.kind,issue.id,issue.status,issue.reason].filter(Boolean).join(' · '))+'</li>').join('')+'</ul></details>';}
 function metadataRows(m){return {disease_context:m.context,evidence_filters:JSON.stringify(m.filters),evidence_filters_description:m.filterDescription,layer_visibility:JSON.stringify(m.layerVisibility),validation_issue_count:m.issues.length,data_release:m.metadata.release_id||'Not configured',validated_at:m.metadata.validated_at||'',graph_checksum:m.metadata.graph_checksum||'',scope:m.scope};}
 const csvValue=v=>{let s=String(v??'');if(/^[\s\u0000-\u001f]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
 function csv(rows,keys){return '\ufeff'+[keys.map(csvValue).join(','),...rows.map(row=>keys.map(key=>csvValue(row[key])).join(','))].join('\r\n')+'\r\n';}
 function summaryCSV(m){const rows=tableRows(m).filter(r=>!r.section).map(r=>({evidence_category:r.label,...Object.fromEntries(m.columns.map((c,i)=>[c.entityId+' '+c.label,r.values[i].join(' | ')])),...metadataRows(m)}));return csv(rows,Object.keys(rows[0]));}
 function evidenceCSV(m){const metadata=metadataRows(m),keys=['record_type','drug_id','drug_label','relationship_id','relationship_type','category','source_entity_id','source_entity_label','target_entity_id','target_entity_label','source_name','source_record_id','pmid','doi','evidence_class','evidence_strength_class','association_evidence_class','association_evidence_strength_class','evidence_subtype','evidence_status','overall_status','phase','action_type','mechanism_of_action','record_links',...Object.keys(metadata)];const rows=m.evidence.map(r=>({...r,record_type:'provenance',record_links:r.links.map(l=>l.url).join(' | '),...metadata}));if(!rows.length)rows.push({record_type:'scope_metadata',category:'No matching provenance records in loaded scope',...metadata});return csv(rows,keys);}
 function printableHTML(m){return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ODDB drug comparison</title><style>body{font:11pt Arial,sans-serif;color:#1e293b;margin:24px}h1{font-size:18pt}.meta{font-size:9pt;line-height:1.5;overflow-wrap:anywhere}.dc-table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:9pt}.dc-table th,.dc-table td{border:1px solid #cbd5e1;padding:7px;vertical-align:top;text-align:left;overflow-wrap:anywhere}.dc-table th{background:#eff4fa}.dc-table thead small{display:block;font-weight:400}.dc-table .dc-section th{background:#dfe9f4}.dc-table p{margin:2px 0}.visually-hidden{position:absolute;clip:rect(0,0,0,0)}details{margin:15px 0}summary{font-weight:bold}li{margin:8px 0;overflow-wrap:anywhere}a{color:#164e8a}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}@media print{body{margin:0}details>ol,details>p{display:block}details{break-inside:auto}.print-help{display:none}}</style></head><body><h1>ODDB drug comparison</h1><p class="print-help">Print this page or use your browser’s Save as PDF.</p><p class="meta">'+xml(m.context)+'<br>'+xml(m.scope)+'<br>'+xml(m.filterDescription)+'<br>Release: '+xml(m.metadata.release_id||'Not configured')+' · Validated: '+xml(m.metadata.validated_at)+'</p>'+tableHTML(m)+'<p class="meta">Counts describe loaded relationships. Zero does not establish absence from ODDB. Clinical stage is drug-level information. Target overlap, trials and report links remain separate from direct therapeutic evidence.</p><h2>Matching provenance</h2>'+(detailHTML(m)+(m.issues.length?issueHTML(m):'')).replaceAll('<details>','<details open>')+'</body></html>';}
 function wrap(text,chars){const lines=[];for(const paragraph of String(text).split('\n')){let line='';for(let word of paragraph.split(/\s+/)){while(word.length>chars){if(line){lines.push(line);line='';}lines.push(word.slice(0,chars));word=word.slice(chars);}if(!word)continue;if((line+' '+word).trim().length>chars){lines.push(line);line=word;}else line=(line+' '+word).trim();}lines.push(line);}return lines;}
 function svgDocument(m){
  const W=1060,pad=20,labelW=190,colW=(W-pad*2-labelW)/m.columns.length,font=12,lineH=17,parts=[];
  const text=(lines,x,y,color='#243750',size=font)=>lines.map((line,i)=>`<text x="${x}" y="${y+i*lineH}" font-family="monospace" font-size="${size}" fill="${color}">${xml(line)}</text>`).join('');
  parts.push(text(['ODDB drug comparison'],pad,32,'#183554',20));
  const header=wrap('Context: '+m.context+' | '+m.filterDescription,136);let y=55;parts.push(text(header,pad,y));y+=header.length*lineH+8;
  const meta=wrap('Release: '+(m.metadata.release_id||'Not configured')+' | Validated: '+m.metadata.validated_at,136);parts.push(text(meta,pad,y,'#53647b'));y+=meta.length*lineH+13;
  const heads=[wrap('Evidence category',24),...m.columns.map(c=>wrap(c.label+'\n'+c.entityId,Math.floor((colW-16)/7.3)))],hh=Math.max(...heads.map(x=>x.length))*lineH+16;
  parts.push(`<rect x="${pad}" y="${y}" width="${W-2*pad}" height="${hh}" fill="#e6eff9"/>`);heads.forEach((lines,i)=>parts.push(text(lines,pad+(i?labelW+(i-1)*colW:0)+8,y+18)));y+=hh;
  for(const row of tableRows(m)){
   if(row.section){parts.push(`<rect x="${pad}" y="${y}" width="${W-2*pad}" height="27" fill="#eef3f8"/>`);parts.push(text([row.section],pad+8,y+18,'#3e5674'));y+=27;continue;}
   const cells=[wrap(row.label,24),...row.values.map(v=>{const all=wrap(v.join('\n'),Math.floor((colW-16)/7.3));return all.length>8?[...all.slice(0,7),'… See comparison CSV']:all;})],h=Math.max(...cells.map(l=>l.length))*lineH+16;
   parts.push(`<rect x="${pad}" y="${y}" width="${W-pad*2}" height="${h}" fill="#fff" stroke="#d5dfeb"/>`);cells.forEach((lines,i)=>{const x=pad+(i?labelW+(i-1)*colW:0);if(i)parts.push(`<path d="M ${x} ${y} v ${h}" stroke="#e1e8f0"/>`);parts.push(text(lines,x+8,y+18));});y+=h;
  }
  const foot=wrap('Loaded graph evidence only. Zero does not establish absence from ODDB. Clinical stage is drug-level information. Discovery and investigation remain separate from direct therapeutic evidence. Long cells are abbreviated; full values and matching records are embedded in metadata and available in CSV.',136);parts.push(text(foot,pad,y+25,'#53647b'));y+=foot.length*lineH+45;
  return `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="280mm" height="${(y/W*280).toFixed(2)}mm" viewBox="0 0 ${W} ${y}" role="img" aria-labelledby="dcSvgTitle dcSvgDesc"><title id="dcSvgTitle">ODDB drug evidence comparison</title><desc id="dcSvgDesc">${xml(m.context+' | '+m.filterDescription)}</desc><metadata>${xml(JSON.stringify(m))}</metadata><rect width="100%" height="100%" fill="#fff"/>${parts.join('')}</svg>`;
 }
 function change(raw,label='Changed drug comparison'){
  const next=normalise(raw);if(JSON.stringify(next)===JSON.stringify(state))return;const before=snapshotGraphState();state=next;serial++;pending=false;lastError='';viewKey='';sync();commitHistory(before,label);
 }
 function status(text,error=false){if(get('drugComparisonStatus')){get('drugComparisonStatus').textContent=text;get('drugComparisonStatus').classList.toggle('has-error',error);}}
 function renderPicker(){
  const query=get('drugComparisonSearch').value.trim().toLocaleLowerCase(),drugs=cy.nodes().filter(n=>n.data('type')==='drug').map(n=>({...n.data(),hidden:n.hasClass('layer-hidden')||n.hasClass('evidence-hidden')})).sort((a,b)=>Number(state.drugIds.includes(b.id))-Number(state.drugIds.includes(a.id))||a.label.localeCompare(b.label));
  const diseases=cy.nodes().filter(n=>n.data('type')==='disease').map(n=>n.data()).sort((a,b)=>a.label.localeCompare(b.label));
  const key=JSON.stringify([state,query,drugs,diseases,[...selectedGraphNodes.keys()]]);if(key===pickerKey)return;pickerKey=key;
  const found=drugs.filter(d=>(d.label+' '+d.entity_id).toLocaleLowerCase().includes(query)),box=get('drugComparisonOptions'),scroll=box.scrollTop,focused=document.activeElement?.dataset?.dcDrug;box.replaceChildren();
  for(const d of found.slice(0,150)){const label=document.createElement('label');label.className='dc-option';const input=document.createElement('input');input.type='checkbox';input.dataset.dcDrug=d.id;input.checked=state.drugIds.includes(d.id);input.disabled=!input.checked&&state.drugIds.length>=5;input.onchange=()=>change({...snapshot(),drugIds:input.checked?[...state.drugIds,d.id]:state.drugIds.filter(id=>id!==d.id)});const span=document.createElement('span');span.textContent=d.label;const small=document.createElement('small');small.textContent=d.entity_id+(d.hidden?' · Hidden in graph':'');span.append(small);label.append(input,span);box.append(label);if(focused===d.id)input.focus();}box.scrollTop=scroll;
  if(!found.length){const p=document.createElement('p');p.className='dc-empty';p.textContent='No matching loaded drugs. Search and add drugs in Explore first.';box.append(p);}
  get('drugComparisonPickerCount').textContent=state.drugIds.length+' of 5 selected'+(found.length>150?' · Showing 150. Refine your search.':'');
  const context=get('drugComparisonDisease');context.replaceChildren(new Option('All loaded diseases',''));for(const d of diseases)context.append(new Option(d.label,d.id));if(state.diseaseId&&!diseases.some(d=>d.id===state.diseaseId))context.append(new Option(state.diseaseId+' (unavailable)',state.diseaseId));context.value=state.diseaseId;
  const selected=[...selectedGraphNodes.keys()].filter(id=>DRUG.test(id));get('drugComparisonUseSelection').disabled=selected.length<2||selected.length>5;
  const chips=get('drugComparisonChips');chips.replaceChildren();for(const id of state.drugIds){const btn=document.createElement('button');btn.type='button';btn.className='dc-chip';const name=cy.$id(id).data('label')||id;btn.textContent=name+' ×';btn.setAttribute('aria-label','Remove '+name+' from comparison');btn.onclick=()=>change({...snapshot(),drugIds:state.drugIds.filter(key=>key!==id)});chips.append(btn);}
 }
 function sync(){
  if(!cy||!get('wbDrugComparisonPanel'))return;renderPicker();const badge=get('wbDrugComparisonBadge');badge.hidden=!state.drugIds.length;badge.textContent=String(state.drugIds.length);
  get('drugComparisonUpdate').disabled=pending||state.drugIds.length<2;
  const graph=graphData(),currentKey=graphKey(graph),key=JSON.stringify([state,E().snapshot(),graph.layerVisibility,graph.nodes.map(n=>[n.data.id,n.layerHidden]),graph.edges.map(e=>[e.data.id,e.layerHidden]),currentKey,validatedKey,pending,lastError]);
  if(key===viewKey)return;viewKey=key;model=null;EXPORTS.forEach(id=>get(id).disabled=true);get('drugComparisonScope').textContent=E().describe();
  if(pending){status('Checking current database evidence…');get('drugComparisonTable').innerHTML='';get('drugComparisonDetails').innerHTML='';return;}
  if(lastError){status(lastError,true);get('drugComparisonTable').innerHTML='';get('drugComparisonDetails').innerHTML='';return;}
  if(state.drugIds.length<2||!validated||currentKey!==validatedKey){status(state.drugIds.length<2?'Choose 2–5 drugs, then update the comparison.':'The loaded graph changed. Update comparison to check its current evidence.');get('drugComparisonTable').innerHTML='';get('drugComparisonDetails').innerHTML='';return;}
  model=buildModel(validated,graph,state,E().snapshot());get('drugComparisonTable').innerHTML=tableHTML(model);get('drugComparisonDetails').innerHTML=detailHTML(model,100);
  const missing=model.columns.filter(c=>!c.available).length;status(`${model.columns.length} drugs compared · ${model.evidence.length} matching provenance record(s).${missing?' '+missing+' column(s) unavailable.':''}${model.issues.length?' '+model.issues.length+' graph validation issue(s). Unavailable records are omitted.':''}`);
  if(model.issues.length)get('drugComparisonDetails').innerHTML+=issueHTML(model,100);
  get('drugComparisonScope').textContent=`${model.context} · ${model.filterDescription} · Release: ${model.metadata.release_id||'Not configured'} · Checked: ${model.metadata.validated_at}. Disease context restricts direct/overlap links; trials and reports require a matching loaded disease link. Molecular targets remain disease independent.`;
  EXPORTS.forEach(id=>get(id).disabled=false);
 }
 async function update(){
  if(state.drugIds.length<2)throw new Error('Select at least 2 drugs.');const token=++serial,key=graphKey();pending=true;lastError='';viewKey='';sync();
  try{const response=await E().refresh(true);if(token!==serial)return null;if(!response||key!==graphKey())throw new Error('The graph changed during validation. Update comparison again.');if(!response.metadata?.validated_at||!Array.isArray(response.nodes)||!Array.isArray(response.edges))throw new Error('The validation response is incomplete.');validated=response;validatedKey=key;return response;
  }catch(error){if(token===serial){validated=null;validatedKey='';lastError='Comparison could not be updated: '+error.message;}throw error;
  }finally{if(token===serial){pending=false;viewKey='';sync();}}
 }
 async function download(kind){
  const response=await update();sync();if(!response||!model)throw new Error('The comparison changed. Update it again before exporting.');const m=clone(model),spec={summary:['csv','text/csv;charset=utf-8',summaryCSV],evidence:['csv','text/csv;charset=utf-8',evidenceCSV],svg:['svg','image/svg+xml;charset=utf-8',svgDocument],print:['html','text/html;charset=utf-8',printableHTML]}[kind];if(!spec)throw new Error('Unsupported comparison export.');
  const url=URL.createObjectURL(new Blob([spec[2](m)],{type:spec[1]})),a=document.createElement('a');try{a.href=url;a.download='oddb-drug-comparison-'+kind+'-'+new Date().toISOString().slice(0,10)+'.'+spec[0];document.body.append(a);a.click();}finally{a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 }
 function init(){if(!get('wbDrugComparisonPanel'))return;get('drugComparisonSearch').oninput=renderPicker;get('drugComparisonDisease').onchange=()=>change({...snapshot(),diseaseId:get('drugComparisonDisease').value});get('drugComparisonUseSelection').onclick=()=>{const drugIds=[...selectedGraphNodes.keys()].filter(id=>DRUG.test(id));if(drugIds.length>=2&&drugIds.length<=5)change({...snapshot(),drugIds},'Compared selected drugs');};get('drugComparisonClear').onclick=()=>change(empty(),'Cleared drug comparison');get('drugComparisonUpdate').onclick=()=>update().catch(()=>{});for(const [id,kind] of [['drugComparisonCSV','summary'],['drugComparisonEvidenceCSV','evidence'],['drugComparisonSVG','svg'],['drugComparisonPrint','print']])get(id).onclick=()=>download(kind).catch(error=>status(error.message,true));sync();}
 window.ODDBDrugComparison={normalise,snapshot,restore,seed,validateState,sync,update,buildModel,tableRows,tableHTML,summaryCSV,evidenceCSV,svgDocument,printableHTML,refLinks,download};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
