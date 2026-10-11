/* ODDB evidence filters v0.7.8. Visibility only; no evidence ranking or graph deletion. */
(() => {
 'use strict';
 const get=id=>document.getElementById(id),MISSING={sources:'missing::source',classes:'missing::class',statuses:'missing::status'};
 const TRIAL=new Set(['disease_trial','drug_trial']);
 const GROUPS=[['sources','Source'],['classes','Class'],['statuses','Status']];
 let state=empty(),cache=new Map(),metadata=null,lastError='',pending=false,serial=0,timer=null,lastKey='',failedKey='',running=null,lastCounts=null;
 function empty(){return {version:1,sources:[],classes:[],statuses:[],hideDisconnected:false};}
 const clean=v=>v===null||v===undefined?'':String(v).trim().replace(/\s+/g,' ');
 function normalise(raw){
  if(raw===undefined||raw===null)return empty();
  if(typeof raw!=='object'||Array.isArray(raw)||raw.version!==1)throw new Error('The saved evidence filters have an unsupported format.');
  const out=empty();
  for(const [group] of GROUPS){const values=raw[group]??[];if(!Array.isArray(values)||values.length>100)throw new Error('An evidence filter may contain at most 100 selected values.');
   for(const value of values){const prefix=group==='sources'?['source::']:group==='classes'?['evidence_class::','evidence_strength_class::']:['status::'];if(typeof value!=='string'||value.length>512||/[\u0000-\u001f]/.test(value)||!(value===MISSING[group]||prefix.some(p=>value.startsWith(p)&&value.length>p.length)))throw new Error('A saved evidence filter value is invalid.');}
   out[group]=[...new Set(values)].sort();
  }out.hideDisconnected=raw.hideDisconnected===true;return out;
 }
 function snapshot(){return normalise(state);}
 function active(s=state){return s.sources.length+s.classes.length+s.statuses.length>0;}
 function primary(d){return Array.isArray(d.evidence_rows)&&d.evidence_rows.length>0;}
 function provenance(d){return Array.isArray(d.provenance_rows)&&d.provenance_rows.length>0;}
 function records(d){
  const isPrimary=primary(d),isProvenance=!isPrimary&&provenance(d),rows=isPrimary?d.evidence_rows:isProvenance?d.provenance_rows:[d];
  return rows.map(record=>{
   const source=isPrimary||isProvenance?clean(record.source_name??record.source):clean(d.source_name??d.evidence_sources);
   const sources=source?(!isPrimary&&!isProvenance?source.split('|').map(clean).filter(Boolean):[source]).map(v=>'source::'+v):[MISSING.sources];
   const classes=[];
   for(const field of ['evidence_class','evidence_strength_class']){const value=clean(record[field]);if(value)classes.push(field+'::'+value);if(isPrimary){const shared=clean(d[field]);if(shared&&!classes.includes(field+'::'+shared))classes.push(field+'::'+shared);}}
   return {record,sources,classes:classes.length?classes:[MISSING.classes]};
  });
 }
 function trialStatus(d){const v=clean(d.overall_status);return v?'status::'+v:MISSING.statuses;}
 function rowMatch(row,s){return (!s.sources.length||s.sources.some(v=>row.sources.includes(v)))&&(!s.classes.length||s.classes.some(v=>row.classes.includes(v)));}
 function matches(d,raw=state){const s=raw;if(!active(s))return true;if(TRIAL.has(d.type)&&s.statuses.length&&!s.statuses.includes(trialStatus(d)))return false;return records(d).some(row=>rowMatch(row,s));}
 function matchingRecords(d,s=state){if(TRIAL.has(d.type)&&s.statuses.length&&!s.statuses.includes(trialStatus(d)))return [];return records(d).filter(row=>rowMatch(row,s)).map(row=>row.record);}
 function requiresRecord(type,s){return !!(s.sources.length||s.classes.length||(s.statuses.length&&TRIAL.has(type)));}
 function recordSignature(d){return JSON.stringify([d.source_name,d.evidence_sources,d.evidence_class,d.evidence_strength_class,d.overall_status,d.evidence_rows,d.provenance_rows]);}
 function keyOf(d){return JSON.stringify([d.id,d.type,d.source,d.target]);}
 function label(key){if(key.startsWith('missing::'))return 'Not recorded';const i=key.indexOf('::'),field=key.slice(0,i),v=key.slice(i+2);return field==='evidence_class'?'Recorded · '+v:field==='evidence_strength_class'?'Strength · '+v:v;}
 function describe(raw=state){const s=normalise(raw),parts=[];for(const [key,title] of [['sources','Sources'],['classes','Classes'],['statuses','Trial status']])if(s[key].length)parts.push(`${title}: ${s[key].map(label).join(', ')}`);if(active(s)&&s.hideDisconnected)parts.push('Disconnected entities hidden, with pinned, selected and seed entities retained');return parts.length?parts.join(' | '):'No evidence filters';}
 function available(data){const sets={sources:new Set(),classes:new Set(),statuses:new Set()};for(const d of data){for(const row of records(d)){row.sources.forEach(v=>sets.sources.add(v));row.classes.forEach(v=>sets.classes.add(v));}if(TRIAL.has(d.type))sets.statuses.add(trialStatus(d));}return sets;}
 function validateState(raw,data){const next=normalise(raw),sets=available(data),issues=[];for(const [group] of GROUPS)for(const v of next[group])if(!sets[group].has(v))issues.push({kind:'evidence_filter',id:label(v),status:'unavailable',reason:'This saved filter value is not recorded in the validated graph. It remains selected and can exclude connections until you reset it.'});return {state:next,issues};}
 function seed(response,fromRestore=false){if(!Array.isArray(response?.edges))return;for(const d of response.edges){const live=cy?.$id(d.id);cache.set(d.id,{key:keyOf(d),liveSignature:recordSignature(!fromRestore&&live?.length?live.data():d),data:d});}if(response.metadata)metadata={...response.metadata};if(!fromRestore)window.ODDBDrugComparison?.seed(response);}
 function restore(raw){state=normalise(raw);}
 function known(edge){const hit=cache.get(edge.id());return hit&&hit.key===keyOf(edge.data())&&hit.liveSignature===recordSignature(edge.data())?hit.data:null;}
 function passes(edge,s){const d=known(edge);return d?matches(d,s):!requiresRecord(edge.data('type'),s);}
 function counts(base){const total=base.length,visible=base.filter(e=>passes(e,state)).length,excluded={};for(const [group] of GROUPS){const single=empty();single[group]=state[group];excluded[group]=base.filter(e=>!passes(e,single)).length;}return {before:total,shown:visible,hidden:total-visible,excluded,unverified:base.filter(e=>!known(e)).length};}
 function catalog(base,group){const found=new Map();for(const edge of base){const d=known(edge);if(!d)continue;const values=new Set();if(group==='statuses'){if(TRIAL.has(d.type))values.add(trialStatus(d));}else for(const row of records(d))row[group].forEach(v=>values.add(v));for(const v of values)found.set(v,(found.get(v)||0)+1);}for(const v of state[group])if(!found.has(v))found.set(v,0);return [...found].map(([key,count])=>({key,count,label:label(key)})).sort((a,b)=>Number(state[group].includes(b.key))-Number(state[group].includes(a.key))||a.label.localeCompare(b.label)||a.key.localeCompare(b.key));}
 function render(base){
  if(!get('evidenceFilterCounts'))return;
  const c=counts(base);lastCounts=c;get('evidenceFilterCounts').textContent=`${c.shown} of ${c.before} layer-visible relationships shown · ${c.hidden} excluded. Source alone excludes ${c.excluded.sources}. Class alone excludes ${c.excluded.classes}. Trial status alone excludes ${c.excluded.statuses}. Each group count applies that filter alone.`;
  const badge=get('wbEvidenceBadge');if(badge){badge.hidden=!active();badge.textContent=`${c.hidden} excluded`;}
  const status=get('evidenceValidationStatus');status.classList.toggle('has-error',!!lastError);
  status.textContent=pending?'Checking current database evidence… New matching connections wait for validation.':lastError?`Evidence refresh failed: ${lastError}${metadata?' Previously checked records remain available.':''}`:metadata?`Evidence checked ${metadata.validated_at}. Release: ${metadata.release_id||'Not configured'}.${c.unverified?` ${c.unverified} relationship(s) could not be verified for filtering.`:''}`:'Evidence options appear after database validation.';
  get('evidenceRefresh').disabled=pending;get('evidenceHideDisconnected').checked=state.hideDisconnected;
  const focused=document.activeElement,focusKey=focused?.dataset?.efKey,focusGroup=focused?.dataset?.efGroup;
  for(const [group,cap] of GROUPS){const box=get(`evidence${cap}Options`),scroll=box.scrollTop,query=get(`evidence${cap}Search`).value.trim().toLocaleLowerCase(),rows=catalog(base,group).filter(row=>row.label.toLocaleLowerCase().includes(query));box.replaceChildren();
   for(const row of rows.slice(0,150)){const labelEl=document.createElement('label');labelEl.className='ef-option';const input=document.createElement('input');input.type='checkbox';input.checked=state[group].includes(row.key);input.dataset.efKey=row.key;input.dataset.efGroup=group;input.onchange=()=>{const next=snapshot();next[group]=input.checked?[...next[group],row.key]:next[group].filter(v=>v!==row.key);change(next,`Changed ${group} evidence filter`);};const title=document.createElement('span');title.textContent=row.label+(row.count===0?' (unavailable)':'');const count=document.createElement('small');count.textContent=String(row.count);labelEl.append(input,title,count);box.append(labelEl);if(focusKey===row.key&&focusGroup===group)input.focus();}
   if(!rows.length){const p=document.createElement('p');p.className='ef-empty';p.textContent=pending?'Loading evidence options…':'No matching recorded values in the current graph.';box.append(p);}box.scrollTop=scroll;get(`evidence${cap}Count`).textContent=rows.length>150?`${rows.length} values. Showing first 150. Use search to narrow the list.`:'Counts are relationships before evidence filters.';
  }
 }
 function graphRefs(){return {nodes:cy.nodes().map(e=>({type:e.data('type'),entity_id:e.data('entity_id')})),edges:cy.edges().map(e=>({id:e.id(),type:e.data('type'),source:e.data('source'),target:e.data('target')}))};}
 function fingerprint(refs){return JSON.stringify({recordData:cy.edges().map(e=>{const d=e.data();return [d.id,d.source_name,d.evidence_sources,d.evidence_class,d.evidence_strength_class,d.overall_status,d.evidence_rows,d.provenance_rows];}).sort((a,b)=>a[0].localeCompare(b[0])),nodes:[...refs.nodes].sort((a,b)=>(a.type+'::'+a.entity_id).localeCompare(b.type+'::'+b.entity_id)),edges:[...refs.edges].sort((a,b)=>a.id.localeCompare(b.id))});}
 function schedule(){if(!cy)return;const refs=graphRefs(),key=fingerprint(refs);if(key===lastKey||key===failedKey)return;clearTimeout(timer);if(!refs.nodes.length){serial++;lastKey=key;cache.clear();metadata=null;pending=false;lastError='';return;}timer=setTimeout(()=>refresh(false).catch(()=>{}),180);}
 async function refresh(force=true){
  clearTimeout(timer);if(!cy)return null;const refs=graphRefs(),key=fingerprint(refs);if(!refs.nodes.length)return null;
  if(running&&key===running.key)return running.promise;
  if(!force&&key===lastKey)return null;
  const token=++serial;pending=true;lastError='';apply(false);
  const promise=(async()=>{try{
   const response=await window.ODDBAnalysis.request('session_validate.php',{}, {body:refs,label:'Checking evidence filters',quiet:true,timeout:120000});
   if(token!==serial||key!==fingerprint(graphRefs())){if(token===serial){pending=false;schedule();}return null;}
   if(!Array.isArray(response.edges)||!Array.isArray(response.nodes)||!response.metadata?.validated_at)throw new Error('The evidence validation response is incomplete.');
   cache=new Map();seed(response);lastKey=key;failedKey='';lastError='';return response;
  }catch(error){if(token===serial){lastError=error.message;failedKey=key;}throw error;}finally{if(token===serial){pending=false;running=null;apply(false);}}})();running={key,promise};return promise;
 }
 function apply(auto=true){
  if(!cy)return;cy.elements().removeClass('evidence-hidden');const base=cy.edges().filter(e=>!e.hasClass('layer-hidden'));
  if(active())base.forEach(e=>{if(!passes(e,state))e.addClass('evidence-hidden');});
  if(active()&&state.hideDisconnected){const endpoints=new Set();base.filter(e=>!e.hasClass('evidence-hidden')).forEach(e=>{endpoints.add(e.data('source'));endpoints.add(e.data('target'));});cy.nodes().forEach(node=>{if(!node.hasClass('layer-hidden')&&!endpoints.has(node.id())&&!pinnedNodes.has(node.id())&&!selectedGraphNodes.has(node.id())&&!(node.data('type')==='disease'&&selectedDiseases.has(node.data('entity_id')))&&node.data('seed')!==1)node.addClass('evidence-hidden');});}
  render(base);refreshNetworkSummary();window.ODDBDrugComparison?.sync();if(auto)schedule();
 }
 function change(raw,title='Changed evidence filters'){const next=normalise(raw);if(JSON.stringify(next)===JSON.stringify(state))return;const before=snapshotGraphState();state=next;applyLayerVisibility(true);commitHistory(before,title);}
 function exportCollection(collection,nodes,edges,raw=state){const s=normalise(raw);let kept=collection.filter(e=>e.isNode()?nodes.has(e.id()):edges.has(e.id())&&matches(edges.get(e.id()),s));if(active(s)&&s.hideDisconnected){const linked=new Set();kept.edges().forEach(e=>{linked.add(e.data('source'));linked.add(e.data('target'));});kept=kept.filter(e=>e.isEdge()||linked.has(e.id())||pinnedNodes.has(e.id())||selectedGraphNodes.has(e.id())||(e.data('type')==='disease'&&selectedDiseases.has(e.data('entity_id')))||e.data('seed')===1);}const ids=new Set(kept.nodes().map(e=>e.id()));return kept.filter(e=>e.isNode()||(ids.has(e.data('source'))&&ids.has(e.data('target'))));}
 function exportInfo(){return {filters:snapshot(),description:describe(),validation:metadata?{...metadata}:null,counts:lastCounts?JSON.parse(JSON.stringify(lastCounts)):null};}
 function init(){if(!get('wbEvidencePanel'))return;get('evidenceReset').onclick=()=>change(empty(),'Reset evidence filters');get('evidenceRefresh').onclick=()=>refresh(true).catch(()=>{});get('evidenceHideDisconnected').onchange=()=>{const next=snapshot();next.hideDisconnected=get('evidenceHideDisconnected').checked;change(next);};for(const [,cap] of GROUPS)get(`evidence${cap}Search`).oninput=()=>{if(cy)render(cy.edges().filter(e=>!e.hasClass('layer-hidden')));};apply();}
 window.ODDBEvidence={edgeData:d=>cache.get(d.id)?.key===keyOf(d)&&cache.get(d.id)?.liveSignature===recordSignature(d)?cache.get(d.id).data:d,normalise,snapshot,active,matches,matchingRecords,records,validateState,seed,restore,apply,refresh,describe,exportCollection,exportInfo};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
