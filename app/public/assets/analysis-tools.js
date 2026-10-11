/* ODDB v1 analysis sessions v0.7.6 with publication vector options v0.7.7. */
(() => {
 'use strict';
 const FORMAT='ODDB_ANALYSIS',VERSION=1,MAX_BYTES=16*1024*1024;
 const idOK=id=>typeof id==='string'&&id.length<=180&&/^[A-Za-z0-9:._-]+$/.test(id);
 const finitePoint=p=>p&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.abs(p.x)<=1e7&&Math.abs(p.y)<=1e7;
 const get=id=>document.getElementById(id);
 const clone=v=>JSON.parse(JSON.stringify(v));
 const xml=v=>String(v??'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&apos;');
 const pending=new Map();let serial=0,context=null,lastFailure=null,preview=null,dialog=null,prepareToken=0,applying=false;
 const labels={'taxonomy.php':'Loading filters','browse.php':'Loading diseases','network_multi.php':'Loading network','expand.php':'Expanding connections','entity.php':'Loading evidence details','global_search.php':'Searching ODDB','search.php':'Searching entities','compare.php':'Comparing diseases','pathfinder.php':'Finding evidence paths','entity_node.php':'Loading entity','session_validate.php':'Validating analysis'};
 function feedback(){
  const box=get('analysisFeedback');if(!box)return;
  box.hidden=!pending.size&&!lastFailure;
  get('analysisBusy').textContent=pending.size?`${[...pending.values()].at(-1)}…${pending.size>1?` (${pending.size} requests)`:''}`:'';
  get('analysisBusy').hidden=!pending.size;
  get('analysisError').textContent=lastFailure?.message||'';
  get('analysisRetry').hidden=!lastFailure?.retry||!!pending.size;
  get('analysisDismiss').hidden=!lastFailure;
  box.classList.toggle('has-error',!!lastFailure);
  const card=document.querySelector('.explorer-workbench-card');if(card)card.setAttribute('aria-busy',String(!!pending.size));
 }
 function failure(error,retry=null){lastFailure={message:error?.message||String(error),retry};feedback();}
 async function request(file,params={},options={}){
  const current=context,ticket=++serial,controller=new AbortController();
  pending.set(ticket,options.label||current?.label||labels[file]||'Loading ODDB');feedback();
  const timeout=setTimeout(()=>controller.abort(),options.timeout||60000);
  try{
   const qs=new URLSearchParams();
   if(!options.body)Object.entries(params).forEach(([k,v])=>{if(Array.isArray(v))v=v.join(',');if(v!==''&&v!==null&&v!==undefined)qs.set(k,v);});
   const response=await fetch(`${API}/${file}${qs.size?'?'+qs:''}`,{method:options.body?'POST':'GET',headers:options.body?{'Content-Type':'application/json'}:undefined,body:options.body?JSON.stringify(options.body):undefined,signal:controller.signal,credentials:'same-origin'});
   let data;
   try{data=await response.json();}catch{throw new Error('ODDB could not return these results. Please try again.');}
   if(!response.ok||data?.ok===false)throw new Error(data?.error||`ODDB could not complete this request (HTTP ${response.status}). Please try again.`);
   return data;
  }catch(original){
   const error=original.name==='AbortError'?new Error('ODDB took too long to respond. Retry or use a smaller network.'):original instanceof TypeError?new Error('Cannot connect to ODDB. Check your connection and try again.'):original;
   error.oddbRequestFailure=true;error.retryAction=current?.retry||null;
   if(!options.quiet)failure(error,error.retryAction);
   throw error;
  }finally{clearTimeout(timeout);pending.delete(ticket);feedback();}
 }
 function wrap(fn,label){return function(...args){const previous=context;context={label,retry:()=>wrapped(...args)};try{return fn(...args);}finally{context=previous;}function wrapped(...next){return wrap(fn,label)(...next);}};}
 async function idle(){
  const start=Date.now();while(pending.size){if(Date.now()-start>65000)throw new Error('An ODDB request is still running. Please wait and try again.');await new Promise(r=>setTimeout(r,80));}
 }
 function currentControls(){return {categorySystem,dataMode,selectedCategory,selectedSubtype,selectedDrugPhase,globalSearchType,
    globalQuery:get('globalSearch').value,diseaseQuery:get('diseaseSearch').value,showDirect:get('showDirect').checked,showOverlap:get('showOverlap').checked};}
 function capture(){
  const snapshot=snapshotGraphState();if(!snapshot?.elements?.some(e=>e.group==='nodes'))throw new Error('Add at least one entity before saving an analysis.');
  for(const element of snapshot.elements){const live=cy.$id(element.data.id);element.classes=['path-highlight','comparison-match','comparison-context'].filter(c=>live.hasClass(c));}
  return {format:FORMAT,schema_version:VERSION,application:'ODDB v1',saved_at:new Date().toISOString(),metadata:null,graph:snapshot,
   controls:currentControls(),
   recipes:{comparison:{recompute:!!comparisonData,tab:comparisonActiveTab},path:{recompute:!!pathFinderData,from:pathEndpoints.from?{type:pathEndpoints.from.type,id:pathEndpoints.from.id}:null,to:pathEndpoints.to?{type:pathEndpoints.to.type,id:pathEndpoints.to.id}:null,maxLength:Number(get('pathMaxLength').value||3)}}};
 }
 function parseSession(value){
  if(!value||value.format!==FORMAT||value.schema_version!==VERSION||!Array.isArray(value.graph?.elements))throw new Error('This file is not a supported ODDB analysis session.');
  const elements=value.graph.elements;
  if(elements.length>20000)throw new Error('An analysis can contain at most 5,000 entities and 15,000 relationships.');
  const seen=new Set();let nodes=0,edges=0;
  for(const e of elements){
   const d=e?.data;
   if(!d||!idOK(d.id)||seen.has(d.id))throw new Error('The analysis contains an invalid or duplicate graph identifier.');seen.add(d.id);
   if(e.group==='nodes'){
    nodes++;if(!idOK(d.entity_id)||!['disease','gene','variant','drug','trial','report','locus','consequence'].includes(d.type)||d.id!==`${d.type}::${d.entity_id}`||!finitePoint(e.position))throw new Error('The analysis contains an invalid entity or graph position.');
   }else if(e.group==='edges'){
    edges++;if(!idOK(d.source)||!idOK(d.target)||typeof d.type!=='string')throw new Error('The analysis contains an invalid relationship.');
   }else throw new Error('The analysis contains an unsupported graph element.');
  }
  if(!nodes||nodes>5000||edges>15000)throw new Error('An analysis must contain 1–5,000 entities and at most 15,000 relationships.');
  if(!Number.isFinite(value.graph.zoom)||value.graph.zoom<=0||value.graph.zoom>1000||!finitePoint(value.graph.pan))throw new Error('The saved graph viewport is invalid.');
  for(const key of ['selectedGraphNodes','pinnedNodes','selectedDiseases']){
   const rows=value.graph[key]||[];if(!Array.isArray(rows)||rows.length>5000||rows.some(row=>!Array.isArray(row)||row.length!==2||!idOK(row[0])))throw new Error('The saved selection or pins are invalid.');
  }
  if(!Array.isArray(value.graph.focusKeepIds||[])||(value.graph.focusKeepIds||[]).some(id=>!idOK(id)))throw new Error('The saved focus state is invalid.');
  window.ODDBEvidence?.normalise(value.graph.evidenceFilters);
  window.ODDBDrugComparison?.normalise(value.graph.drugComparison);
  return value;
 }
 function references(session){
  const nodes=new Map();const edges=[];
  for(const e of session.graph.elements){const d=e.data;if(e.group==='nodes')nodes.set(d.id,{type:d.type,entity_id:d.entity_id});else edges.push({id:d.id,type:d.type,source:d.source,target:d.target});}
  for(const [id] of session.graph.selectedDiseases||[])if(idOK(id))nodes.set(`disease::${id}`,{type:'disease',entity_id:id});
  for(const e of [session.recipes?.path?.from,session.recipes?.path?.to])if(e&&['disease','gene','variant','drug'].includes(e.type)&&idOK(e.id))nodes.set(`${e.type}::${e.id}`,{type:e.type,entity_id:e.id});
  if(nodes.size>5000)throw new Error('The combined graph and saved selections exceed 5,000 entities.');
  return {nodes:[...nodes.values()],edges};
 }
 function controlPlan(raw,issues){
  const c=raw||{},system=['anatomy','inheritance'].includes(c.categorySystem)?c.categorySystem:'anatomy',mode=['gene','variant'].includes(c.dataMode)?c.dataMode:'gene';
  const categories=taxonomy?.disease_categories||[],subtypes=mode==='gene'?taxonomy?.gene_categories||[]:taxonomy?.variant_consequences||[];
  const category=categories.some(x=>x.category_system===system&&x.category_id===c.selectedCategory)?c.selectedCategory:'';
  const subtype=subtypes.some(x=>(mode==='gene'?x.gene_category_id:x.consequence_id)===c.selectedSubtype)?c.selectedSubtype:'';
  const phase=(taxonomy?.drug_phases||[]).some(x=>String(x.phase)===String(c.selectedDrugPhase))?String(c.selectedDrugPhase):'';
  for(const [key,value] of [['selectedCategory',category],['selectedSubtype',subtype],['selectedDrugPhase',phase]])if(c[key]&&c[key]!==value)issues.push({kind:'filter',id:String(c[key]),status:'unavailable',reason:'Saved filter is not available in the current database and will be cleared.'});
  return {categorySystem:system,dataMode:mode,selectedCategory:category,selectedSubtype:subtype,selectedDrugPhase:phase,
   globalSearchType:ENTITY_SEARCH_TYPES.includes(c.globalSearchType)?c.globalSearchType:'',globalQuery:typeof c.globalQuery==='string'?c.globalQuery.slice(0,2000):'',diseaseQuery:typeof c.diseaseQuery==='string'?c.diseaseQuery.slice(0,2000):'',showDirect:c.showDirect!==false,showOverlap:c.showOverlap===true};
 }
 function trustedPlan(session,response){
  if(!Array.isArray(response.nodes)||!Array.isArray(response.edges)||!Array.isArray(response.issues))throw new Error('The validation response is incomplete. Your graph was kept unchanged.');
  const freshNodes=new Map(response.nodes.map(d=>[d.id,d])),freshEdges=new Map(response.edges.map(d=>[d.id,d]));
  const graphNodes=new Map(),elements=[];
  for(const old of session.graph.elements){
   const d=old.group==='nodes'?freshNodes.get(old.data.id):freshEdges.get(old.data.id);if(!d)continue;
   const item={group:old.group,data:clone(d)};
   if(old.group==='nodes'){
    item.position={x:old.position.x,y:old.position.y};
    for(const flag of ['seed','expanded','selected_for_expansion'])if(old.data[flag]===1)item.data[flag]=1;
    graphNodes.set(d.id,item.data);
   }
   item.classes=(Array.isArray(old.classes)?old.classes:[]).filter(c=>['path-highlight','comparison-match','comparison-context'].includes(c));elements.push(item);
  }
  const safeElements=elements.filter(e=>e.group==='nodes'||(graphNodes.has(e.data.source)&&graphNodes.has(e.data.target)));
  const mapRows=(rows,map,keyTransform=id=>id)=>(rows||[]).filter(([id])=>map.has(keyTransform(id))).map(([id])=>[id,clone(map.get(keyTransform(id)))]);
  const graph={elements:safeElements,zoom:session.graph.zoom,pan:{...session.graph.pan},
   selectedGraphNodes:mapRows(session.graph.selectedGraphNodes,graphNodes),pinnedNodes:mapRows(session.graph.pinnedNodes,graphNodes),
   selectedDiseases:mapRows(session.graph.selectedDiseases,freshNodes,id=>`disease::${id}`).map(([id,d])=>[id,{...d,disease_id:id,disease_name:d.label}]),
   layerVisibility:Object.fromEntries(Object.keys(LAYER_DEFAULTS).map(k=>[k,session.graph.layerVisibility?.[k]!==false])),
   breadcrumbSteps:['Restored analysis'],focusActive:session.graph.focusActive===true,
   focusKeepIds:(session.graph.focusKeepIds||[]).filter(id=>safeElements.some(e=>e.data.id===id))};
  const filterPlan=window.ODDBEvidence?.validateState(session.graph.evidenceFilters,response.edges);
  if(filterPlan)graph.evidenceFilters=filterPlan.state;
  const comparisonPlan=window.ODDBDrugComparison?.validateState(session.graph.drugComparison,safeElements.filter(e=>e.group==='nodes').map(e=>e.data));
  if(comparisonPlan)graph.drugComparison=comparisonPlan.state;
  const issues=clone(response.issues).concat(filterPlan?.issues||[],comparisonPlan?.issues||[]),controls=controlPlan(session.controls,issues),notes=[];
  const saved=session.metadata?.release_id,current=response.metadata?.release_id;
  if(saved&&current&&saved!==current)notes.push(`Database release differs: saved ${saved}; current ${current}.`);
  else if(!saved||!current)notes.push('The database release is not configured for one or both versions. Records were checked against the current database.');
  if(session.metadata?.graph_checksum&&session.metadata.graph_checksum!==response.metadata?.graph_checksum)notes.push('Record content differs from the saved analysis. Current database labels and evidence will be used.');
  return {session,response,graph,controls,issues,notes,freshNodes};
 }
 function showDialog(mode){
  preview=null;get('analysisDialogTitle').textContent=mode==='save'?'Save analysis':'Restore analysis';get('analysisDialogSummary').textContent='Waiting for current ODDB requests…';
  get('analysisDialogDetails').replaceChildren();get('analysisApply').disabled=true;get('analysisApply').textContent=mode==='save'?'Download validated analysis':'Restore validated analysis';get('analysisReportDownload').hidden=true;
  if(!dialog.open)dialog.showModal();
 }
 function summary(plan){
  const nodes=plan.graph.elements.filter(e=>e.group==='nodes').length,edges=plan.graph.elements.length-nodes;
  get('analysisDialogSummary').textContent=`${nodes} entities and ${edges} relationships validated. ${plan.issues.length} validation issue(s).`;
  const out=get('analysisDialogDetails');out.replaceChildren();
  for(const note of plan.notes){const p=document.createElement('p');p.textContent=note;out.append(p);}
  const release=document.createElement('p');release.textContent=`Current release: ${plan.response.metadata?.release_id||'Not configured'}. Validated: ${plan.response.metadata?.validated_at||'Unknown'}.`;out.append(release);
  if(plan.issues.length){const list=document.createElement('ul');for(const issue of plan.issues.slice(0,200)){const li=document.createElement('li');li.textContent=`${issue.kind} ${issue.id}: ${issue.status}. ${issue.reason}`;list.append(li);}out.append(list);if(plan.issues.length>200){const p=document.createElement('p');p.textContent='Download the report to inspect all remaining items.';out.append(p);}}
  get('analysisApply').disabled=!nodes;get('analysisReportDownload').hidden=false;
 }
 async function prepare(mode,file=null){
  showDialog(mode);const token=++prepareToken;
  try{
   await idle();if(!dialog.open||token!==prepareToken)return;if(!taxonomy)await loadTaxonomy();if(!dialog.open||token!==prepareToken)return;
   let session;
   if(mode==='save')session=capture();else{
    if(file.size>MAX_BYTES)throw new Error('The analysis file exceeds 16 MiB.');
    let value;try{value=JSON.parse(await file.text());}catch{throw new Error('This file does not contain valid JSON.');}
    session=parseSession(value);
   }
   get('analysisDialogSummary').textContent='Checking entities, relationships and evidence against ODDB…';
   const response=await request('session_validate.php',{}, {body:references(session),label:'Validating analysis',timeout:120000,quiet:true});
   if(!dialog.open||token!==prepareToken)return;
   preview={...trustedPlan(session,response),mode};summary(preview);
  }catch(error){if(token!==prepareToken)return;if(dialog.open){get('analysisDialogSummary').textContent=error.message;get('analysisApply').disabled=true;}failure(error,()=>prepare(mode,file));}
 }
 function report(plan){return {application:'ODDB v1',validated_at:plan.response.metadata?.validated_at,metadata:plan.response.metadata,notes:plan.notes,issues:plan.issues,counts:{nodes:plan.graph.elements.filter(e=>e.group==='nodes').length,edges:plan.graph.elements.filter(e=>e.group==='edges').length}};}
 function savePlan(plan){
  const session={format:FORMAT,schema_version:VERSION,application:'ODDB v1',saved_at:new Date().toISOString(),metadata:plan.response.metadata,
   graph:plan.graph,controls:plan.controls,recipes:plan.session.recipes,validation_report:report(plan)};
  const text=JSON.stringify(session,null,2);if(new Blob([text]).size>MAX_BYTES)throw new Error('The saved analysis exceeds 16 MiB. Export a smaller network.');
  downloadBlob(new Blob([text],{type:'application/json;charset=utf-8'}),`oddb-analysis-${new Date().toISOString().slice(0,10)}.json`);
  showNotice('Validated analysis downloaded. Use Restore analysis to continue later.','success',6000);
 }
 function setControls(c){
  categorySystem=c.categorySystem;dataMode=c.dataMode;selectedCategory=c.selectedCategory;selectedSubtype=c.selectedSubtype;selectedDrugPhase=c.selectedDrugPhase;globalSearchType=c.globalSearchType;
  get('globalSearch').value=c.globalQuery;get('diseaseSearch').value=c.diseaseQuery;get('showDirect').checked=c.showDirect;get('showOverlap').checked=c.showOverlap;
  syncModeButtons();renderCategories();renderSubtypes();renderPhases();syncGlobalSearchTypeFilters();get('searchResults').classList.add('d-none');get('globalSearchStatus').textContent='';
 }
 async function restorePlan(plan){
  const before=snapshotGraphState(),oldControls=currentControls(),oldComparison=comparisonData,oldPaths=pathFinderData,oldEndpoints=clone(pathEndpoints),oldTab=comparisonActiveTab,oldMax=get('pathMaxLength').value;
  try{
   setControls(plan.controls);comparisonData=null;pathFinderData=null;pathEndpoints={from:null,to:null};
   window.ODDBEvidence?.seed(plan.response,true);
   restoreGraphState(plan.graph);
   window.ODDBDrugComparison?.seed(plan.response);
   clearComparison();renderPathFinder();syncPathFinderControls();
   for(const element of plan.graph.elements)if(element.classes?.length)cy.$id(element.data.id).addClass(element.classes.join(' '));
   if(!selectedCategory){get('diseaseList').innerHTML='<div class="p-4 text-center text-secondary small">Select a category above.</div>';get('diseaseCount').textContent='Choose a category.';}
   get('detailsPanel').innerHTML='<div class="empty-state"><div class="empty-symbol">◎</div><div class="fw-semibold">Analysis restored</div><div class="small text-secondary">Select a node or relationship to inspect current evidence.</div></div>';
   commitHistory(before,'Restored saved analysis');
  }catch(error){setControls(oldControls);restoreGraphState(before);comparisonData=oldComparison;pathFinderData=oldPaths;pathEndpoints=oldEndpoints;comparisonActiveTab=oldTab;get('pathMaxLength').value=oldMax;renderComparison();renderPathFinder();syncPathFinderControls();throw new Error('The analysis could not be restored. Your previous graph was recovered.');}
  const recipe=plan.session.recipes||{},extra=[];
  const path=recipe.path||{};
  for(const side of ['from','to']){const ref=path[side],d=ref?plan.freshNodes.get(`${ref.type}::${ref.id}`):null;if(d&&PATH_ENDPOINT_TYPES.has(d.type))pathEndpoints[side]={type:d.type,id:d.entity_id,label:d.label,subtitle:d.subtitle};}
  get('pathMaxLength').value=String([1,2,3,4].includes(path.maxLength)?path.maxLength:3);syncPathFinderControls();
  if(recipe.comparison?.recompute&&selectedDiseases.size>=2&&selectedDiseases.size<=5){try{comparisonData=await apiGet('compare.php',{disease_ids:[...selectedDiseases.keys()]});comparisonActiveTab=COMPARISON_TABS.some(x=>x[0]===recipe.comparison.tab)?recipe.comparison.tab:'shared_genes';renderComparison();}catch(e){extra.push('Comparison could not be recomputed: '+e.message);}}
  if(path.recompute&&pathEndpoints.from&&pathEndpoints.to){try{pathFinderData=await apiGet('pathfinder.php',{from_type:pathEndpoints.from.type,from_id:pathEndpoints.from.id,to_type:pathEndpoints.to.type,to_id:pathEndpoints.to.id,max_length:Number(get('pathMaxLength').value),max_paths:10});renderPathFinder();}catch(e){extra.push('Paths could not be recomputed: '+e.message);}}
  const url=new URL(location.href);for(const key of ['type','id','system','mode','category','subtype'])url.searchParams.delete(key);url.searchParams.set('system',categorySystem);url.searchParams.set('mode',dataMode);if(selectedCategory)url.searchParams.set('category',selectedCategory);if(selectedSubtype)url.searchParams.set('subtype',selectedSubtype);history.replaceState(null,'',url);
  showNotice(`Analysis restored with current ODDB evidence.${plan.issues.length?` ${plan.issues.length} validation issue(s). See the validation report.`:''}${extra.length?' '+extra.join(' '):''}`,plan.issues.length||extra.length?'warning':'success',10000);
 }
 // Vector SVG uses current Cytoscape model geometry. Labels remain text elements.
 function num(v){return Number(Number(v).toFixed(3));}
 function style(ele,key,fallback){const v=ele.style(key);return v===undefined||v===null||v===''?fallback:v;}
 function scalar(ele,key,fallback){const v=parseFloat(style(ele,key,fallback));return Number.isFinite(v)?v:fallback;}
 function roundedPolygon(points,radius){
  const corners=points.map((p,i)=>{const prev=points[(i+points.length-1)%points.length],next=points[(i+1)%points.length];const a=Math.hypot(prev.x-p.x,prev.y-p.y),b=Math.hypot(next.x-p.x,next.y-p.y),r=Math.min(radius,a/3,b/3);return {p,before:{x:p.x+(prev.x-p.x)*r/a,y:p.y+(prev.y-p.y)*r/a},after:{x:p.x+(next.x-p.x)*r/b,y:p.y+(next.y-p.y)*r/b}};});
  return `M ${num(corners[0].after.x)} ${num(corners[0].after.y)} `+corners.slice(1).concat(corners[0]).map(c=>`L ${num(c.before.x)} ${num(c.before.y)} Q ${num(c.p.x)} ${num(c.p.y)} ${num(c.after.x)} ${num(c.after.y)}`).join(' ')+' Z';
 }
 function nodeShape(n,attrs,padding=0){
  const p=n.position(),w=n.width()+padding*2,h=n.height()+padding*2,x=p.x-w/2,y=p.y-h/2,shape=style(n,'shape','ellipse');
  if(shape==='ellipse')return `<ellipse cx="${num(p.x)}" cy="${num(p.y)}" rx="${num(w/2)}" ry="${num(h/2)}" ${attrs}/>`;
  if(shape==='round-rectangle'||shape==='rectangle')return `<rect x="${num(x)}" y="${num(y)}" width="${num(w)}" height="${num(h)}" rx="${shape==='round-rectangle'?num(Math.min(w,h)/4):0}" ${attrs}/>`;
  let pts;
  if(shape.includes('diamond'))pts=[{x:p.x,y},{x:x+w,y:p.y},{x:p.x,y:y+h},{x,y:p.y}];
  else if(shape.includes('hexagon'))pts=[{x:x+w*.25,y},{x:x+w*.75,y},{x:x+w,y:p.y},{x:x+w*.75,y:y+h},{x:x+w*.25,y:y+h},{x,y:p.y}];
  else if(shape==='tag')pts=[{x,y},{x:x+w*.75,y},{x:x+w,y:p.y},{x:x+w*.75,y:y+h},{x,y:y+h}];
  else throw new Error(`SVG export does not support the node shape ${shape}.`);
  return shape.startsWith('round-')?`<path d="${roundedPolygon(pts,3)}" ${attrs}/>`:`<polygon points="${pts.map(p=>`${num(p.x)},${num(p.y)}`).join(' ')}" ${attrs}/>`;
 }
 function edgePath(e){
  const a=e.sourceEndpoint(),b=e.targetEndpoint();if(!finitePoint(a)||!finitePoint(b))throw new Error('Graph geometry is not ready. Fit the graph and retry SVG export.');
  let controls=[];try{controls=e.controlPoints()||[];}catch{}
  controls=controls.filter(finitePoint);let path=`M ${num(a.x)} ${num(a.y)}`;
  if(controls.length){controls.forEach((c,i)=>{const end=i===controls.length-1?b:{x:(c.x+controls[i+1].x)/2,y:(c.y+controls[i+1].y)/2};path+=` Q ${num(c.x)} ${num(c.y)} ${num(end.x)} ${num(end.y)}`;});}
  else{let segments=[];try{segments=e.segmentPoints()||[];}catch{};for(const p of segments.filter(finitePoint))path+=` L ${num(p.x)} ${num(p.y)}`;path+=` L ${num(b.x)} ${num(b.y)}`;}
  return path;
 }
 function wrapLabel(label,width,font){
  const ctx=document.createElement('canvas').getContext('2d');ctx.font=font;
  const lines=[];for(const paragraph of String(label).split('\n')){
   let line='';for(const word of paragraph.split(/\s+/)){
    if(ctx.measureText(word).width>width){
     if(line){lines.push(line);line='';}
     for(const char of Array.from(word)){if(line&&ctx.measureText(line+char).width>width){lines.push(line);line='';}line+=char;}
    }else{const next=line?line+' '+word:word;if(line&&ctx.measureText(next).width>width){lines.push(line);line=word;}else line=next;}
   }lines.push(line);
  }return lines;
 }
 function svgDocument(scope,options={}){
  if(!cy)throw new Error('The graph is not ready.');
  let collection=options.collection||(scope==='selected'?selectedElements():visibleElementCollection());
  collection=collection.filter(e=>!e.hasClass('layer-hidden')&&!e.hasClass('evidence-hidden')&&e.visible());
  if(!collection.nodes().length)throw new Error(scope==='selected'?'Select visible graph nodes first.':'There is no visible network to export.');
  const bounds=collection.boundingBox({includeLabels:options.labelSize===undefined,includeOverlays:true});
  let box,w,h;
  if(scope==='viewport'){const z=cy.zoom(),p=cy.pan();w=cy.width();h=cy.height();box={x:-p.x/z,y:-p.y/z,w:w/z,h:h/z};}
  else{box={x:bounds.x1-24,y:bounds.y1-24,w:bounds.w+48,h:bounds.h+48};w=box.w;h=box.h;}
  if(![box.x,box.y,box.w,box.h,w,h].every(Number.isFinite)||w<=0||h<=0)throw new Error('The graph has no valid export dimensions.');
  const definitions=[],edgeParts=[],nodeParts=[];
  const labelBounds=[];
  collection.edges().sort((a,b)=>scalar(a,'z-index',0)-scalar(b,'z-index',0)).forEach((e,i)=>{
   const color=style(e,'line-color','#94a3b8'),width=scalar(e,'width',2),line=style(e,'line-style','solid'),opacity=scalar(e,'opacity',1);
   const dash=line==='dotted'?`${num(width)},${num(width*2)}`:line==='dashed'?`${num(width*4)},${num(width*3)}`:'';
   let marker='';if(style(e,'target-arrow-shape','none')==='triangle'){const name=`arrow${i}`;definitions.push(`<marker id="${name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 10 5 L 0 10 Z" fill="${xml(style(e,'target-arrow-color',color))}"/></marker>`);marker=` marker-end="url(#${name})"`;}
   edgeParts.push(`<g opacity="${num(opacity)}"><title>${xml(e.data('type'))}: ${xml(e.data('id'))}</title><path d="${edgePath(e)}" fill="none" stroke="${xml(color)}" stroke-width="${num(width)}"${dash?` stroke-dasharray="${dash}"`:''}${marker}/></g>`);
  });
  collection.nodes().forEach(n=>{
   const opacity=scalar(n,'opacity',1),fill=style(n,'background-color','#64748b'),border=style(n,'border-color','#fff'),bw=scalar(n,'border-width',2);
   let out=`<g opacity="${num(opacity)}"><title>${xml(n.data('type'))}: ${xml(n.data('entity_id'))}</title>`;
   const underlay=scalar(n,'underlay-opacity',0);if(underlay>0)out+=nodeShape(n,`fill="${xml(style(n,'underlay-color','#fff'))}" fill-opacity="${num(underlay)}" stroke="none"`,scalar(n,'underlay-padding',0));
   out+=nodeShape(n,`fill="${xml(fill)}" fill-opacity="${num(scalar(n,'background-opacity',1))}" stroke="${xml(border)}" stroke-width="${num(bw)}"`);
   const size=options.labelSize??scalar(n,'font-size',10),family=options.fontFamily||style(n,'font-family','Arial, sans-serif'),fontStyle=style(n,'font-style','normal'),weight=style(n,'font-weight','normal');
   const lines=wrapLabel(options.nodeData?.get(n.id())?.label??n.data('label')??'',options.labelWidth??scalar(n,'text-max-width',94),`${fontStyle} ${weight} ${size}px ${family}`),p=n.position(),y=p.y+n.height()/2+scalar(n,'text-margin-y',6)+size;
   if(options.showLabels!==false){
   const ctx=document.createElement('canvas').getContext('2d');ctx.font=`${fontStyle} ${weight} ${size}px ${family}`;
   const width=Math.max(0,...lines.map(line=>ctx.measureText(line).width));labelBounds.push({id:n.id(),x1:p.x-width/2,y1:y-size,x2:p.x+width/2,y2:y+Math.max(0,lines.length-1)*size*1.2+size*.3});
   out+=`<text x="${num(p.x)}" y="${num(y)}" text-anchor="middle"${options.labelHalo?` paint-order="stroke fill" stroke="#ffffff" stroke-width="${num(size*.22)}" stroke-linejoin="round"`:''} font-family="${xml(family)}" font-size="${num(size)}" font-style="${xml(fontStyle)}" font-weight="${xml(weight)}" fill="${xml(style(n,'color','#000'))}" opacity="${num(scalar(n,'text-opacity',1))}">${lines.map((line,i)=>`<tspan x="${num(p.x)}" dy="${i?num(size*1.2):0}">${xml(line)}</tspan>`).join('')}</text>`;
   }
   out+='</g>';
   nodeParts.push(out);
  });
  if(scope!=='viewport'&&options.labelSize!==undefined){
   const x1=Math.min(box.x,...labelBounds.map(b=>b.x1-24)),y1=Math.min(box.y,...labelBounds.map(b=>b.y1-24)),x2=Math.max(box.x+box.w,...labelBounds.map(b=>b.x2+24)),y2=Math.max(box.y+box.h,...labelBounds.map(b=>b.y2+24));
   box={x:x1,y:y1,w:x2-x1,h:y2-y1};w=box.w;h=box.h;
  }
  if(Array.isArray(options.labelBoxes))options.labelBoxes.push(...labelBounds);
  const metadata={application:'ODDB v1',evidence_filters:window.ODDBEvidence?.exportInfo()||null,exported_at:new Date().toISOString(),scope,entities:collection.nodes().map(n=>({id:n.id(),type:n.data('type')})),relationships:collection.edges().map(e=>({id:e.id(),type:e.data('type')}))};
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${num(w)}" height="${num(h)}" viewBox="${num(box.x)} ${num(box.y)} ${num(box.w)} ${num(box.h)}"><title>ODDB v1 evidence network</title><desc>Direct therapeutic evidence, target overlap discovery and clinical associations retain separate relationship types.</desc><metadata>${xml(JSON.stringify(metadata))}</metadata><defs>${definitions.join('')}</defs><rect x="${num(box.x)}" y="${num(box.y)}" width="${num(box.w)}" height="${num(box.h)}" fill="#ffffff"/>${edgeParts.join('')}${nodeParts.join('')}</svg>`;
 }
 async function svgExport(scope){
  try{await new Promise(r=>requestAnimationFrame(r));const svg=svgDocument(scope);downloadBlob(new Blob([svg],{type:'image/svg+xml;charset=utf-8'}),`oddb-explorer-${scope}-network.svg`);showNotice('SVG downloaded with vector shapes and editable text.','success',4500);}catch(e){failure(e,()=>svgExport(scope));}
 }
 function init(){
  dialog=get('analysisDialog');if(!dialog)return;
  get('saveAnalysis').onclick=()=>prepare('save');get('restoreAnalysis').onclick=()=>{get('analysisFile').value='';get('analysisFile').click();};
  get('analysisFile').onchange=()=>{const file=get('analysisFile').files?.[0];if(file)prepare('restore',file);};
  get('analysisCancel').onclick=()=>{if(!applying)dialog.close();};dialog.addEventListener('cancel',event=>{if(applying)event.preventDefault();});dialog.addEventListener('close',()=>{preview=null;prepareToken++;});
  get('analysisApply').onclick=async()=>{
   const plan=preview;if(!plan||applying)return;applying=true;get('analysisCancel').disabled=true;get('analysisApply').disabled=true;
   try{if(plan.mode==='save')savePlan(plan);else{get('analysisDialogSummary').textContent='Restoring validated graph and refreshing analysis results…';await restorePlan(plan);}dialog.close();}catch(e){get('analysisDialogSummary').textContent=e.message;get('analysisApply').disabled=false;failure(e);}finally{applying=false;get('analysisCancel').disabled=false;}
  };
  get('analysisReportDownload').onclick=()=>{if(preview)downloadBlob(new Blob([JSON.stringify(report(preview),null,2)],{type:'application/json;charset=utf-8'}),'oddb-analysis-validation-report.json');};
  get('analysisRetry').onclick=()=>{const retry=lastFailure?.retry;lastFailure=null;feedback();if(retry)Promise.resolve(retry()).catch(e=>failure(e,retry));};get('analysisDismiss').onclick=()=>{lastFailure=null;feedback();};
  document.querySelectorAll('[data-analysis-export]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await svgExport(button.dataset.analysisExport);}finally{button.disabled=false;const menu=button.closest('details');if(menu)menu.open=false;}});
  feedback();
 }
 window.addEventListener('unhandledrejection',event=>{if(event.reason?.oddbRequestFailure){failure(event.reason,event.reason.retryAction);event.preventDefault();}});
 window.ODDBAnalysis={request,parseSession,references,trustedPlan,svgDocument,xml,idle,nodeShape};
 loadTaxonomy=wrap(loadTaxonomy,'Loading filters');loadDiseases=wrap(loadDiseases,'Loading diseases');loadNetwork=wrap(loadNetwork,'Loading network');loadEntity=wrap(loadEntity,'Loading evidence details');
 runGlobalSearch=wrap(runGlobalSearch,'Searching ODDB');searchPathEndpoint=wrap(searchPathEndpoint,'Searching path entities');expandSelection=wrap(expandSelection,'Expanding connections');expandOne=wrap(expandOne,'Expanding connections');
 runDiseaseComparison=wrap(runDiseaseComparison,'Comparing diseases');findPaths=wrap(findPaths,'Finding evidence paths');addEntityToCurrentGraph=wrap(addEntityToCurrentGraph,'Adding entity');startEntityAnalysis=wrap(startEntityAnalysis,'Starting analysis');
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
