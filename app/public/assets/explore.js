/* ODDB graph zoom responsiveness fix v0.7.9a */
/* ODDB graph evidence filter integration v0.7.8 */
/* ODDB analysis request integration v0.7.6 */
const API='api',
 $=id=>document.getElementById(id),
 esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#039;"),
 nonempty=v=>v!==null&&v!==undefined&&String(v).trim()!=='';

const EXPAND_ACTIONS={
 disease:{genes:'Show genes',variants:'Show variants',drugs:'Show direct drugs',trials:'Show clinical trials',reports:'Show clinical reports'},
 gene:{diseases:'Show diseases',variants:'Show variants',drugs:'Show targeting drugs'},
 variant:{genes:'Show gene(s)',diseases:'Show explicitly linked diseases',consequence:'Show consequence'},
 drug:{diseases:'Show direct diseases',targets:'Show molecular targets',trials:'Show clinical trials',reports:'Show clinical reports'},
 trial:{diseases:'Show linked diseases',drugs:'Show investigated drugs'},
 report:{diseases:'Show linked diseases',drugs:'Show linked drugs'}
};

const LAYER_DEFAULTS={
 disease:true,
 gene:true,
 variant:true,
 direct:true,
 target:true,
 overlap:true,
 trial:true,
 report:true
};

const LAYER_NODE_TYPES={
 disease:['disease'],
 gene:['gene','locus'],
 variant:['variant','consequence'],
 trial:['trial'],
 report:['report']
};

const LAYER_EDGE_TYPES={
 direct:['direct_disease_drug'],
 target:['drug_target'],
 overlap:['target_overlap_only'],
 trial:['disease_trial','drug_trial'],
 report:['disease_report','drug_report']
};

function nodeLayerKey(node){
 const t=node?.data?node.data('type'):null;
 for(const [layer,types] of Object.entries(LAYER_NODE_TYPES))if(types.includes(t))return layer;
 return null;
}
function edgeLayerKey(edge){
 const t=edge?.data?edge.data('type'):null;
 for(const [layer,types] of Object.entries(LAYER_EDGE_TYPES))if(types.includes(t))return layer;
 return null;
}

let taxonomy=null,
 comparisonData=null,
 comparisonActiveTab='shared_genes',
 pathEndpoints={from:null,to:null},
 pathFinderData=null,
 pathSearchTimers={from:null,to:null},
 globalSearchType='disease',
 globalSearchResults=[],
 globalSearchTimer=null,
 categorySystem='anatomy',
 dataMode='gene',
 selectedCategory='',
 selectedSubtype='',
 selectedDrugPhase='',
 selectedDiseases=new Map(),
 currentDiseaseRows=[],
 selectedGraphNodes=new Map(),
 pinnedNodes=new Map(),
 cy=null,
 timer=null,
 focusActive=false,
 layerVisibility={...LAYER_DEFAULTS},
 historyStack=[],
 futureStack=[],
 breadcrumbSteps=[],
 historyRestoring=false,
 MAX_HISTORY=30;

async function apiGet(file,params={}){
 return window.ODDBAnalysis.request(file,params);
}

function badge(t){return `<span class="entity-badge ${esc(t)}">${esc(t)}</span>`}
function nodeKey(type,id){return `${type}::${id}`}
function entityLabel(d){return d?.label||d?.entity_id||d?.id||''}

function showNotice(message,kind='info',timeout=5000){
 const el=$('workbenchNotice');
 if(!message){el.className='workbench-notice d-none';el.textContent='';return}
 el.className=`workbench-notice ${kind}`;
 el.textContent=message;
 if(timeout)window.setTimeout(()=>{if(el.textContent===message)showNotice('')},timeout);
}

function visibleElementCollection(){
 if(!cy)return null;
 return cy.elements().filter(ele=>!ele.hasClass('layer-hidden')&&!ele.hasClass('evidence-hidden'));
}

function snapshotGraphState(){
 if(!cy)return null;
 return {
  elements:cy.elements().map(ele=>{
   const item={group:ele.isNode()?'nodes':'edges',data:{...ele.data()}};
   if(ele.isNode())item.position={...ele.position()};
   return item;
  }),
  zoom:cy.zoom(),
  pan:{...cy.pan()},
  selectedGraphNodes:[...selectedGraphNodes.entries()].map(([id,d])=>[id,{...d}]),
  pinnedNodes:[...pinnedNodes.entries()].map(([id,d])=>[id,{...d}]),
  selectedDiseases:[...selectedDiseases.entries()].map(([id,d])=>[id,{...d}]),
  layerVisibility:{...layerVisibility},
  evidenceFilters:window.ODDBEvidence?.snapshot(),
  drugComparison:window.ODDBDrugComparison?.snapshot(),
  breadcrumbSteps:[...breadcrumbSteps],
  focusActive,
  focusKeepIds:focusActive?cy.elements('.focus-keep').map(ele=>ele.id()):[]
 };
}

function commitHistory(before,label){
 if(historyRestoring||!before)return;
 historyStack.push(before);
 if(historyStack.length>MAX_HISTORY)historyStack.shift();
 futureStack=[];
 breadcrumbSteps.push(label);
 if(breadcrumbSteps.length>10)breadcrumbSteps=breadcrumbSteps.slice(-10);
 renderHistoryBar();
}

function restoreGraphState(state){
 if(!state||!cy)return;
 historyRestoring=true;
 try{
  window.ODDBEvidence?.restore(state.evidenceFilters);
  window.ODDBDrugComparison?.restore(state.drugComparison);
  cy.elements().remove();
  if(state.elements?.length)cy.add(state.elements);

  selectedGraphNodes=new Map(state.selectedGraphNodes||[]);
  pinnedNodes=new Map(state.pinnedNodes||[]);
  selectedDiseases=new Map(state.selectedDiseases||[]);
  layerVisibility={...LAYER_DEFAULTS,...(state.layerVisibility||{})};
  breadcrumbSteps=[...(state.breadcrumbSteps||[])];

  syncWorkbenchClasses();
  renderPinnedBar();
  renderGraphSelectionBar();
  renderSelectedDiseaseSummary();
  syncLayerControls();
  applyLayerVisibility(false);

  focusActive=false;
  cy.elements().removeClass('focus-dim focus-keep');
  if(state.focusActive&&state.focusKeepIds?.length){
   cy.elements().addClass('focus-dim');
   state.focusKeepIds.forEach(id=>{
    const ele=cy.$id(id);
    if(ele.length)ele.removeClass('focus-dim').addClass('focus-keep');
   });
   focusActive=true;
  }

  if(Number.isFinite(state.zoom))cy.zoom(state.zoom);
  if(state.pan&&Number.isFinite(state.pan.x)&&Number.isFinite(state.pan.y))cy.pan(state.pan);

  refreshNetworkSummary();
  if(selectedCategory)loadDiseases();
 }finally{
  historyRestoring=false;
 }
}

function historyBack(){
 if(!historyStack.length)return;
 const previous=historyStack.pop();
 const current=snapshotGraphState();
 if(current)futureStack.push(current);
 restoreGraphState(previous);
 renderHistoryBar();
 showNotice('Returned to the previous Explorer state.','info',2500);
}

function historyForward(){
 if(!futureStack.length)return;
 const next=futureStack.pop();
 const current=snapshotGraphState();
 if(current)historyStack.push(current);
 restoreGraphState(next);
 renderHistoryBar();
 showNotice('Moved forward to the next Explorer state.','info',2500);
}

function renderHistoryBar(){
 const back=$('historyBack'),forward=$('historyForward');
 if(back)back.disabled=!historyStack.length;
 if(forward)forward.disabled=!futureStack.length;
 if($('historyCount'))$('historyCount').textContent=`${historyStack.length} step${historyStack.length===1?'':'s'}`;

 const trail=$('historyBreadcrumb');
 if(trail){
  const steps=breadcrumbSteps.slice(-6);
  trail.innerHTML='<span class="history-start">Start</span>'+
   steps.map((s,i)=>`<span class="history-arrow">›</span><span class="history-step" title="${esc(s)}">${esc(s)}</span>`).join('');
 }
}

function relationLabel(type,relation){
 if(relation==='all')return 'all relationships';
 return EXPAND_ACTIONS[type]?.[relation]||relation;
}

function selectionHistoryLabel(relation){
 const rows=[...selectedGraphNodes.values()];
 const types=[...new Set(rows.map(x=>x.type))];
 if(rows.length===1){
  const d=rows[0];
  return `${entityLabel(d)} → ${relationLabel(d.type,relation)}`;
 }
 if(types.length===1)return `${rows.length} ${types[0]} nodes → ${relationLabel(types[0],relation)}`;
 return `${rows.length} selected nodes → ${relation==='all'?'all relationships':relation}`;
}

function syncLayerControls(){
 document.querySelectorAll('[data-layer-toggle]').forEach(input=>{
  input.checked=layerVisibility[input.dataset.layerToggle]!==false;
 });
}

function updateLayerCounts(){
 if(!cy)return;
 const nodeCounts={disease:0,gene:0,variant:0,trial:0,report:0};
 cy.nodes().forEach(n=>{
  const t=n.data('type');
  if(t==='disease')nodeCounts.disease++;
  else if(t==='gene'||t==='locus')nodeCounts.gene++;
  else if(t==='variant'||t==='consequence')nodeCounts.variant++;
  else if(t==='trial')nodeCounts.trial++;
  else if(t==='report')nodeCounts.report++;
 });
 const edgeCounts={direct:0,target:0,overlap:0};
 cy.edges().forEach(e=>{
  const t=e.data('type');
  if(t==='direct_disease_drug')edgeCounts.direct++;
  else if(t==='drug_target')edgeCounts.target++;
  else if(t==='target_overlap_only')edgeCounts.overlap++;
 });
 const counts={...nodeCounts,...edgeCounts};
 Object.entries(counts).forEach(([layer,n])=>{
  const el=document.querySelector(`[data-layer-count="${layer}"]`);
  if(el)el.textContent=n.toLocaleString();
 });
 const hidden=Object.entries(layerVisibility).filter(([,v])=>!v).map(([k])=>k);
 if($('hiddenLayerCount'))$('hiddenLayerCount').textContent=hidden.length?`${hidden.length} layer${hidden.length===1?'':'s'} hidden`:'All layers visible';
}

function applyLayerVisibility(refresh=true){
 if(!cy)return;
 cy.elements().removeClass('layer-hidden');

 Object.entries(LAYER_NODE_TYPES).forEach(([layer,types])=>{
  if(layerVisibility[layer]!==false)return;
  cy.nodes().forEach(n=>{if(types.includes(n.data('type')))n.addClass('layer-hidden')});
 });

 Object.entries(LAYER_EDGE_TYPES).forEach(([layer,types])=>{
  if(layerVisibility[layer]!==false)return;
  cy.edges().forEach(e=>{if(types.includes(e.data('type')))e.addClass('layer-hidden')});
 });

 /* An edge whose endpoint is hidden is not visually shown either. Mark it
    explicitly so visible counts and CSV exports match the actual graph view. */
 cy.edges().forEach(e=>{
  if(e.source().hasClass('layer-hidden')||e.target().hasClass('layer-hidden')){
   e.addClass('layer-hidden');
  }
 });

 updateLayerCounts();
 window.ODDBEvidence?.apply();
 if(refresh)refreshNetworkSummary();
}

/* ODDB_SEARCH_HOVER_22: local node labels, no network requests. */
function installEntityHover22(graph){
 const canvas=graph.container();
 const tip=document.createElement('div');
 tip.id='oddbEntityHover22';tip.className='oddb-entity-hover22';
 tip.setAttribute('role','tooltip');tip.hidden=true;
 const name=document.createElement('div'),type=document.createElement('div');
 name.className='oddb-entity-hover22-name';type.className='oddb-entity-hover22-type';
 tip.append(name,type);document.body.appendChild(tip);
 const types={disease:'Disease',gene:'Gene',locus:'Genetic locus',variant:'Variant',drug:'Drug',trial:'Clinical trial',report:'Clinical report',consequence:'Variant consequence'};
 const hide=()=>{tip.hidden=true;};
 function show(event){
  const node=event.target;
  if(!node?.length||node.removed()||!node.visible()){hide();return;}
  const data=node.data();
  name.textContent=String(data.label||data.preferred_name||data.gene_symbol||data.disease_name||data.nct_id||data.title||data.entity_id||data.id||'Unnamed entity');
  type.textContent=types[data.type]||String(data.type||'Entity').replaceAll('_',' ');
  const original=event.originalEvent||{};
  const box=canvas.getBoundingClientRect();
  const point=event.renderedPosition||node.renderedPosition();
  const x=Number.isFinite(original.clientX)?original.clientX:box.left+point.x;
  const y=Number.isFinite(original.clientY)?original.clientY:box.top+point.y;
  tip.hidden=false;
  const rect=tip.getBoundingClientRect();
  const maxX=Math.max(8,window.innerWidth-rect.width-8);
  const maxY=Math.max(8,window.innerHeight-rect.height-8);
  let top=y+16;
  if(top>maxY)top=y-rect.height-12;
  tip.style.left=Math.max(8,Math.min(maxX,x+16))+'px';
  tip.style.top=Math.max(8,Math.min(maxY,top))+'px';
 }
 const escape=event=>{if(event.key==='Escape')hide();};
 graph.on('mouseover mousemove','node',show);
 graph.on('mouseout','node',hide);
 graph.on('pan zoom layoutstart remove drag tap',hide);
 canvas.addEventListener('mouseleave',hide);
 window.addEventListener('scroll',hide,true);
 window.addEventListener('blur',hide);
 document.addEventListener('keydown',escape);
 graph.on('destroy',()=>{
  hide();tip.remove();canvas.removeEventListener('mouseleave',hide);
  window.removeEventListener('scroll',hide,true);window.removeEventListener('blur',hide);
  document.removeEventListener('keydown',escape);
 });
}

function initCy(){
 cy=cytoscape({
  container:$('cy'),elements:[],autounselectify:true,
  // Native wheel sensitivity. Cache the viewport during gestures; draw live at standard density.
  textureOnViewport:true,pixelRatio:1,
  style:[
   {selector:'node',style:{
    'label':'data(label)','font-size':10,'text-wrap':'wrap','text-max-width':94,
    'text-valign':'bottom','text-margin-y':6,'background-color':'#64748b',
    'width':30,'height':30,'border-width':2,'border-color':'#fff','opacity':1
   }},
   {selector:'node[type="disease"]',style:{'background-color':'#7c3aed','width':42,'height':42}},
   {selector:'node[type="gene"]',style:{'background-color':'#0284c7'}},
   {selector:'node[type="locus"]',style:{'background-color':'#6366f1','shape':'diamond','width':36,'height':36}},
   {selector:'node[type="variant"]',style:{'background-color':'#475569','shape':'hexagon','width':28,'height':28}},
   {selector:'node[type="drug"]',style:{'background-color':'#059669','shape':'round-rectangle','width':42,'height':28}},
   {selector:'node[type="trial"]',style:{'background-color':'#d97706','shape':'round-hexagon','width':36,'height':36}},
   {selector:'node[type="report"]',style:{'background-color':'#db2777','shape':'round-diamond','width':34,'height':34}},
   {selector:'node[type="consequence"]',style:{'background-color':'#64748b','shape':'tag','width':36,'height':26}},
   {selector:'node[expanded = 1]',style:{'border-width':3,'border-color':'#a78bfa'}},
   {selector:'node[seed = 1]',style:{'border-width':5,'border-color':'#f59e0b'}},
   {selector:'node.pinned-node',style:{
    'border-width':5,'border-color':'#f97316','underlay-color':'#fed7aa','underlay-opacity':.34,'underlay-padding':10
   }},
   {selector:'node.workbench-selected',style:{
    'border-width':5,'border-color':'#111827','underlay-color':'#93c5fd','underlay-opacity':.30,'underlay-padding':7
   }},
   {selector:'node.pinned-node.workbench-selected',style:{
    'border-width':5,'border-color':'#111827','underlay-color':'#fb923c','underlay-opacity':.35,'underlay-padding':11
   }},
   {selector:'edge',style:{'curve-style':'bezier','width':2,'line-color':'#94a3b8','opacity':.82}},
   {selector:'edge[type="disease_gene"]',style:{'line-color':'#7c3aed'}},
   {selector:'edge[type="disease_locus"]',style:{'line-color':'#6366f1'}},
   {selector:'edge[type="disease_variant"]',style:{'line-color':'#475569'}},
   {selector:'edge[type="gene_variant"]',style:{'line-color':'#0284c7','line-style':'dotted'}},
   {selector:'edge[type="variant_consequence"]',style:{'line-color':'#64748b','line-style':'dotted'}},
   {selector:'edge[type="direct_disease_drug"]',style:{'line-color':'#dc2626','width':3.5}},
   {selector:'edge[type="drug_target"]',style:{'line-color':'#0284c7','target-arrow-shape':'triangle','target-arrow-color':'#0284c7'}},
   {selector:'edge[type="target_overlap_only"]',style:{'line-color':'#94a3b8','line-style':'dashed','width':2.4}},
   {selector:'edge[type="disease_trial"], edge[type="drug_trial"]',style:{'line-color':'#d97706','line-style':'dotted','width':2.4}},
   {selector:'edge[type="disease_report"], edge[type="drug_report"]',style:{'line-color':'#db2777','line-style':'dotted','width':2.4}},
   {selector:'.layer-hidden',style:{'display':'none'}},
   {selector:'.evidence-hidden',style:{'display':'none'}},
   {selector:'.focus-dim',style:{'opacity':.08,'text-opacity':.08}},
   {selector:'.focus-keep',style:{'opacity':1,'text-opacity':1}},
   {selector:'node.path-highlight',style:{'border-width':7,'border-color':'#16a34a','underlay-color':'#bbf7d0','underlay-opacity':.36,'underlay-padding':10}},
   {selector:'edge.path-highlight',style:{'width':5,'opacity':1,'z-index':900}}
  ],
  layout:{name:'cose',animate:false,fit:true,padding:30}
 });

 installEntityHover22(cy);
 cy.on('tap','node',e=>{
  const d=e.target.data(),oe=e.originalEvent||{},multi=!!(oe.ctrlKey||oe.metaKey||oe.shiftKey);
  if(multi)toggleGraphSelection(e.target);
  else selectOnlyGraphNode(e.target);
  renderNodeDetails(e.target);
 });

 cy.on('tap','edge',e=>renderEdge(window.ODDBEvidence?.edgeData(e.target.data())||e.target.data()));
 cy.on('tap',e=>{
  if(e.target===cy){
   selectedGraphNodes.clear();
   syncWorkbenchClasses();
   renderGraphSelectionBar();
  }
 });
}

function layout(){
 if(cy&&cy.elements().length){
  cy.layout({name:'cose',animate:false,fit:true,padding:38,nodeRepulsion:950000,idealEdgeLength:105,edgeElasticity:80}).run();
 }
}

function mergeElements(elements,{relayout=true}={}){
 const add=[];
 for(const el of elements||[]){
  const id=el?.data?.id;
  if(!id)continue;
  if(cy.$id(id).length===0)add.push(el);
  else if(el.data&&el.data.expanded)cy.$id(id).data('expanded',el.data.expanded);
 }
 if(add.length)cy.add(add);
 pruneMissingWorkbenchState();
 syncWorkbenchClasses();
 applyLayerVisibility(false);
 if(focusActive)showAllNodes();
 if(relayout&&add.length)layout();
 refreshNetworkSummary();
 return add.length;
}

function replaceGraphKeepingPins(elements){
 const keepNodes=[],keepEdges=[];
 const pinIds=new Set(pinnedNodes.keys());
 if(cy){
  cy.nodes().forEach(n=>{if(pinIds.has(n.id()))keepNodes.push({data:{...n.data()}})});
  cy.edges().forEach(e=>{if(pinIds.has(e.source().id())&&pinIds.has(e.target().id()))keepEdges.push({data:{...e.data()}})});
  cy.elements().remove();
 }
 mergeElements(elements,{relayout:false});
 mergeElements([...keepNodes,...keepEdges],{relayout:false});
 syncWorkbenchClasses();
 applyLayerVisibility(false);
 layout();
 refreshNetworkSummary();
}

function pruneMissingWorkbenchState(){
 for(const id of [...selectedGraphNodes.keys()])if(cy.$id(id).length===0)selectedGraphNodes.delete(id);
}

function selectOnlyGraphNode(node){
 selectedGraphNodes.clear();
 selectedGraphNodes.set(node.id(),{...node.data()});
 syncWorkbenchClasses();
 renderGraphSelectionBar();
}
function toggleGraphSelection(node){
 if(selectedGraphNodes.has(node.id()))selectedGraphNodes.delete(node.id());
 else selectedGraphNodes.set(node.id(),{...node.data()});
 syncWorkbenchClasses();
 renderGraphSelectionBar();
}
function syncWorkbenchClasses(){
 if(!cy)return;
 cy.nodes().removeClass('workbench-selected pinned-node');
 selectedGraphNodes.forEach((_,id)=>{const n=cy.$id(id);if(n.length)n.addClass('workbench-selected')});
 pinnedNodes.forEach((_,id)=>{const n=cy.$id(id);if(n.length)n.addClass('pinned-node')});
 window.ODDBEvidence?.apply();
}

function commonSelectionType(){
 const types=[...new Set([...selectedGraphNodes.values()].map(x=>x.type))];
 return types.length===1?types[0]:null;
}
function renderGraphSelectionBar(){
 const n=selectedGraphNodes.size,type=commonSelectionType(),select=$('expandAction');
 $('graphSelectionSummary').textContent=`${n} graph node${n===1?'':'s'} selected`;
 select.innerHTML='';
 if(!n){
  select.innerHTML='<option value="">Select node(s) first</option>';
  select.disabled=true;
 }else if(type&&EXPAND_ACTIONS[type]){
  select.append(new Option('Expand all available relationships','all'));
  Object.entries(EXPAND_ACTIONS[type]).forEach(([value,label])=>select.append(new Option(label,value)));
  select.disabled=false;
 }else{
  select.append(new Option('Expand all available relationships','all'));
  select.disabled=false;
 }
 ['expandSelected','pinSelected','unpinSelected','focusSelected'].forEach(id=>$(id).disabled=!n);
 syncWorkbenchClasses();
}

function renderPinnedBar(){
 const box=$('pinnedEntityChips');
 if(!pinnedNodes.size){
  box.innerHTML='<span class="text-secondary small">No pinned entities.</span>';
  syncWorkbenchClasses();
  return;
 }
 box.innerHTML=[...pinnedNodes.entries()].map(([cyid,d])=>`
  <button type="button" class="workbench-chip pinned" data-pinned-select="${esc(cyid)}" title="Select ${esc(entityLabel(d))}">
   ${badge(d.type)} <span>${esc(entityLabel(d))}</span>
   <i data-unpin="${esc(cyid)}" title="Unpin">×</i>
  </button>`).join('');
 box.querySelectorAll('[data-pinned-select]').forEach(btn=>btn.onclick=e=>{
  const unpin=e.target.closest('[data-unpin]');
  if(unpin){e.stopPropagation();unpinNode(unpin.dataset.unpin);return}
  const n=cy.$id(btn.dataset.pinnedSelect);
  if(n.length){selectOnlyGraphNode(n);renderNodeDetails(n);cy.center(n)}
 });
 syncWorkbenchClasses();
}

function pinSelected(){
 selectedGraphNodes.forEach((d,id)=>pinnedNodes.set(id,{...d}));
 renderPinnedBar();
 showNotice(`${selectedGraphNodes.size} selected node(s) pinned.`,'success');
}
function unpinSelected(){
 let n=0;
 selectedGraphNodes.forEach((_,id)=>{if(pinnedNodes.delete(id))n++});
 renderPinnedBar();
 showNotice(`${n} node(s) unpinned.`,'info');
}
function unpinNode(id){
 pinnedNodes.delete(id);
 renderPinnedBar();
}

function focusSelected(){
 if(!selectedGraphNodes.size)return;
 let keep=cy.collection();
 selectedGraphNodes.forEach((_,id)=>{
  const n=cy.$id(id);
  if(n.length)keep=keep.union(n.closedNeighborhood());
 });
 cy.elements().addClass('focus-dim').removeClass('focus-keep');
 keep.removeClass('focus-dim').addClass('focus-keep');
 focusActive=true;
 showNotice('Focus mode: selected nodes and their direct neighbours are emphasized.','info');
}
function showAllNodes(){
 if(!cy)return;
 cy.elements().removeClass('focus-dim focus-keep');
 focusActive=false;
}

function clearUnpinned(){
 if(!cy)return;
 const before=snapshotGraphState();
 const pinIds=new Set(pinnedNodes.keys());
 const remove=cy.nodes().filter(n=>!pinIds.has(n.id()));
 if(!remove.length){showNotice('There are no unpinned nodes to clear.','info');return}
 cy.remove(remove);
 for(const id of [...selectedGraphNodes.keys()])if(!pinIds.has(id))selectedGraphNodes.delete(id);
 showAllNodes();
 renderGraphSelectionBar();
 applyLayerVisibility(false);
 refreshNetworkSummary();
 if(cy.elements().length)cy.fit(undefined,40);
 commitHistory(before,'Cleared unpinned entities');
 showNotice('Unpinned entities were cleared.','info');
}
function resetAnalysis(){
 pathFinderData=null;pathEndpoints={from:null,to:null};
 selectedDiseases.clear();selectedGraphNodes.clear();pinnedNodes.clear();
 historyStack=[];futureStack=[];breadcrumbSteps=[];
 layerVisibility={...LAYER_DEFAULTS};
 window.ODDBEvidence?.restore(undefined);
 window.ODDBDrugComparison?.restore(undefined);
 if(cy)cy.elements().remove();
 showAllNodes();
 renderSelectedDiseaseSummary();renderComparisonSelection();syncPathFinderControls();renderGraphSelectionBar();renderPinnedBar();renderHistoryBar();
 syncLayerControls();applyLayerVisibility(false);
 refreshNetworkSummary();
 $('detailsPanel').innerHTML='<div class="empty-state"><div class="empty-symbol">◎</div><div class="fw-semibold">Analysis reset</div><div class="small text-secondary">Select diseases or search an entity to begin again.</div></div>';
 if(selectedCategory)loadDiseases();
 showNotice('Complete Explorer analysis reset.','info');
}

async function expandRequest(type,ids,relation){
 return apiGet('expand.php',{type,ids,relation,limit:400});
}

async function expandSelection(relation){
 if(!selectedGraphNodes.size)return;
 const before=snapshotGraphState();
 const historyLabel=selectionHistoryLabel(relation);
 const groups=new Map();
 selectedGraphNodes.forEach(d=>{
  if(!EXPAND_ACTIONS[d.type])return;
  if(!groups.has(d.type))groups.set(d.type,[]);
  groups.get(d.type).push(d.entity_id);
 });
 if(!groups.size)return;

 if(relation==='all'&&selectedGraphNodes.size>12){
  if(!window.confirm(`Expand all available relationships for ${selectedGraphNodes.size} selected nodes? This may create a large graph.`))return;
 }

 $('expandSelected').disabled=true;
 showNotice('Expanding selected entities…','info',0);
 const jobs=[];
 groups.forEach((ids,type)=>{
  if(relation==='all')Object.keys(EXPAND_ACTIONS[type]).forEach(rel=>jobs.push(expandRequest(type,ids,rel)));
  else if(EXPAND_ACTIONS[type]?.[relation])jobs.push(expandRequest(type,ids,relation));
 });
 try{
  const results=await Promise.allSettled(jobs);
  let added=0;const notices=[];const errors=[];
  for(const r of results){
   if(r.status==='fulfilled'){
    added+=mergeElements(r.value.elements,{relayout:false});
    if(r.value.notice)notices.push(r.value.notice);
   }else errors.push(r.reason?.message||'Expansion failed');
  }
  if(added){
   layout();
   commitHistory(before,historyLabel);
  }
  syncWorkbenchClasses();applyLayerVisibility(false);refreshNetworkSummary();
  const msg=[`${added} new graph element(s) added.`,...new Set(notices),...new Set(errors)].join(' ');
  showNotice(msg,errors.length?'warning':'success',7000);
 }finally{
  $('expandSelected').disabled=false;
 }
}

async function expandOne(type,id,relation,label=''){
 const before=snapshotGraphState();
 showNotice(`Expanding ${label||id}…`,'info',0);
 try{
  const d=await expandRequest(type,[id],relation);
  const added=mergeElements(d.elements,{relayout:true});
  const n=cy.$id(nodeKey(type,id));
  if(n.length){selectOnlyGraphNode(n);renderNodeDetails(n)}
  if(added)commitHistory(before,`${label||id} → ${relationLabel(type,relation)}`);
  showNotice(`${added} new graph element(s) added.${d.notice?' '+d.notice:''}`,d.notice?'warning':'success',6500);
 }catch(e){showNotice(e.message,'warning',7000)}
}

function expansionButtons(type,id,label){
 const actions=EXPAND_ACTIONS[type];
 if(!actions)return '';
 return `<div class="detail-actions mt-3">
  <div class="small fw-bold text-uppercase text-secondary mb-2">Expand from this ${esc(type)}</div>
  <div class="detail-action-grid">
   ${Object.entries(actions).map(([rel,text])=>`<button class="btn btn-sm btn-outline-primary" data-expand-one-type="${esc(type)}" data-expand-one-id="${esc(id)}" data-expand-one-rel="${esc(rel)}" data-expand-one-label="${esc(label)}">${esc(text)}</button>`).join('')}
  </div>
 </div>`;
}

function localNodeActions(node){
 const d=node.data(),isPinned=pinnedNodes.has(node.id());
 return `<div class="detail-workbench-actions mt-3">
   <button class="btn btn-sm ${isPinned?'btn-warning':'btn-outline-secondary'}" data-detail-pin="${esc(node.id())}">${isPinned?'Unpin':'Pin'}</button>
   <button class="btn btn-sm btn-outline-secondary" data-detail-focus="${esc(node.id())}">Focus</button>
  </div>`;
}

function bindDetailActions(){
 document.querySelectorAll('[data-related-type]').forEach(el=>el.onclick=()=>loadEntity(el.dataset.relatedType,el.dataset.relatedId));
 document.querySelectorAll('[data-expand-one-type]').forEach(btn=>btn.onclick=()=>expandOne(btn.dataset.expandOneType,btn.dataset.expandOneId,btn.dataset.expandOneRel,btn.dataset.expandOneLabel));
 document.querySelectorAll('[data-detail-pin]').forEach(btn=>btn.onclick=()=>{
  const id=btn.dataset.detailPin,n=cy.$id(id);if(!n.length)return;
  if(pinnedNodes.has(id))pinnedNodes.delete(id);else pinnedNodes.set(id,{...n.data()});
  renderPinnedBar();renderNodeDetails(n);
 });
 document.querySelectorAll('[data-detail-focus]').forEach(btn=>btn.onclick=()=>{
  const n=cy.$id(btn.dataset.detailFocus);if(!n.length)return;
  selectOnlyGraphNode(n);focusSelected();
 });
}

function renderNodeDetails(node){
 const d=node.data();
 if(d.type==='report'||d.type==='consequence'){
  $('detailsPanel').innerHTML=`${badge(d.type)}<h2 class="h5 mt-2">${esc(d.label)}</h2>
   ${d.subtitle?`<p class="small text-secondary">${esc(d.subtitle)}</p>`:''}
   ${props(d)}${expansionButtons(d.type,d.entity_id,d.label)}${localNodeActions(node)}`;
  bindDetailActions();
  return;
 }
 loadEntity(d.type,d.entity_id,node);
}

async function loadTaxonomy(){taxonomy=await apiGet('taxonomy.php');renderCategories();renderSubtypes();renderPhases()}

function renderCategories(){
 const rows=taxonomy.disease_categories.filter(x=>x.category_system===categorySystem);
 $('categoryStrip').innerHTML=rows.map(x=>`
  <button class="category-card ${selectedCategory===x.category_id?'active':''}" data-category="${esc(x.category_id)}">
   <div class="fw-semibold">${esc(x.category_name)}</div><div class="count">${Number(x.disease_count).toLocaleString()} diseases</div>
  </button>`).join('');
 document.querySelectorAll('[data-category]').forEach(el=>el.onclick=()=>{
  selectedCategory=el.dataset.category;selectedDiseases.clear();renderCategories();renderSelectedDiseaseSummary();loadDiseases();
 });
}

function renderSubtypes(){
 const isGene=dataMode==='gene',rows=isGene?taxonomy.gene_categories:taxonomy.variant_consequences;
 $('subtypeTitle').textContent=isGene?'Gene type':'Variant consequence';
 $('subtypeChips').innerHTML=`<button class="filter-chip ${selectedSubtype===''?'active':''}" data-subtype="">${isGene?'All gene types':'All variant types'}</button>`+
  rows.map(x=>{const id=isGene?x.gene_category_id:x.consequence_id,n=Number(isGene?x.entity_count:x.variant_count),label=isGene?x.category_name:x.consequence_term;return `<button class="filter-chip ${selectedSubtype===id?'active':''} ${n===0?'zero':''}" data-subtype="${esc(id)}">${esc(label)} <span class="opacity-75">${n.toLocaleString()}</span></button>`}).join('');
 document.querySelectorAll('[data-subtype]').forEach(el=>el.onclick=()=>{selectedSubtype=el.dataset.subtype;renderSubtypes();if(selectedCategory)loadDiseases()});
}

function phaseLabel(v){
 const s=String(v??'');
 const labels={
  APPROVAL:'Approval stage',
  PHASE_1:'Phase 1',
  PHASE_1_2:'Phase 1/2',
  PHASE_2:'Phase 2',
  PHASE_2_3:'Phase 2/3',
  PHASE_3:'Phase 3',
  UNKNOWN:'Unknown',
  NO_STAGE_REPORTED:'Not reported'
 };
 return labels[s]??(/^\d+(\.\d+)?$/.test(s)?`Phase ${s}`:s.replaceAll('_',' '));
}
function renderPhases(){
 $('drugPhaseChips').innerHTML=`<button class="filter-chip ${selectedDrugPhase===''?'active':''}" data-phase="">All phases</button>`+
  taxonomy.drug_phases.map(x=>`<button class="filter-chip ${selectedDrugPhase===x.phase?'active':''}" data-phase="${esc(x.phase)}">${esc(phaseLabel(x.phase))} <span class="opacity-75">${Number(x.drug_count).toLocaleString()}</span></button>`).join('');
 document.querySelectorAll('[data-phase]').forEach(el=>el.onclick=()=>{selectedDrugPhase=el.dataset.phase;renderPhases();if(selectedCategory)loadDiseases()});
}

function renderSelectedDiseaseSummary(){
 const n=selectedDiseases.size;
 $('selectedDiseaseSummary').innerHTML=n?`<strong>${n}</strong> disease${n===1?'':'s'} selected`:'0 diseases selected';
 renderComparisonSelection();
}

async function loadDiseases(){
 if(!selectedCategory)return;
 const p={category_system:categorySystem,category_id:selectedCategory,mode:dataMode,drug_phase:selectedDrugPhase,q:$('diseaseSearch').value.trim(),limit:200};
 if(dataMode==='gene')p.gene_category_id=selectedSubtype;else p.consequence_id=selectedSubtype;
 const requestState=JSON.stringify([categorySystem,dataMode,selectedCategory,selectedSubtype,selectedDrugPhase,$('diseaseSearch').value.trim()]);
 const d=await apiGet('browse.php',p);
 if(requestState!==JSON.stringify([categorySystem,dataMode,selectedCategory,selectedSubtype,selectedDrugPhase,$('diseaseSearch').value.trim()]))return;
 currentDiseaseRows=d.diseases;$('diseaseCount').textContent=`${d.total.toLocaleString()} matching diseases`;
 $('diseaseList').innerHTML=d.diseases.length?d.diseases.map(x=>{
  const checked=selectedDiseases.has(x.disease_id);
  return `<div class="list-group-item disease-item ${checked?'active':''}" data-disease="${esc(x.disease_id)}">
   <div class="disease-select-line"><input class="form-check-input disease-check" type="checkbox" ${checked?'checked':''} aria-label="Select ${esc(x.disease_name)}">
    <div class="disease-main"><div class="fw-semibold">${esc(x.disease_name)}</div><div class="small text-secondary">${esc(x.inheritance||x.localization||'')}</div></div>
    <button class="btn btn-sm btn-link disease-detail-btn" data-disease-details="${esc(x.disease_id)}" title="Open disease details">ⓘ</button>
   </div>
   <div class="metric-row"><span class="metric-pill">${Number(x.gene_count).toLocaleString()} genes</span><span class="metric-pill">${Number(x.variant_count).toLocaleString()} variants</span><span class="metric-pill">${Number(x.drug_count).toLocaleString()} drugs</span><span class="metric-pill">${Number(x.trial_count).toLocaleString()} trials</span></div>
  </div>`}).join(''):'<div class="p-4 text-center text-secondary small">No diseases match these filters.</div>';
 document.querySelectorAll('[data-disease]').forEach(row=>row.addEventListener('click',e=>{if(e.target.closest('[data-disease-details]'))return;toggleDisease(row.dataset.disease)}));
 document.querySelectorAll('[data-disease-details]').forEach(btn=>btn.onclick=e=>{e.stopPropagation();loadEntity('disease',btn.dataset.diseaseDetails)});
}

function toggleDisease(id){
 const row=currentDiseaseRows.find(x=>x.disease_id===id);if(!row)return;
 if(selectedDiseases.has(id))selectedDiseases.delete(id);else selectedDiseases.set(id,row);
 renderSelectedDiseaseSummary();loadDiseases();
}
function selectAllShown(){currentDiseaseRows.forEach(row=>selectedDiseases.set(row.disease_id,row));renderSelectedDiseaseSummary();loadDiseases()}

async function loadNetwork(){
 if(!selectedDiseases.size){clearNetwork();return}
 const before=snapshotGraphState();
 const p={mode:dataMode,disease_ids:[...selectedDiseases.keys()],direct:$('showDirect').checked?1:0,overlap:$('showOverlap').checked?1:0,target:1,drug_phase:selectedDrugPhase,expand_gene_diseases:0,include_neighbor_genes:0,limit:700};
 if(dataMode==='gene')p.gene_category_id=selectedSubtype;else p.consequence_id=selectedSubtype;
 $('networkSummary').textContent='Updating network…';
 try{
  const d=await apiGet('network_multi.php',p);
  replaceGraphKeepingPins(d.elements);
  applyLayerVisibility(false);
  refreshNetworkSummary();
  commitHistory(before,`Loaded ${selectedDiseases.size} selected disease${selectedDiseases.size===1?'':'s'}`);
 }catch(e){$('networkSummary').textContent=e.message}
}

function refreshNetworkSummary(){
 syncEntityStarter();
 if(!cy||!cy.elements().length){
  $('networkSummary').textContent='Start with a disease or search any ODDB entity.';
  updateLayerCounts();
  return;
 }
 const visibleNodes=cy.nodes().filter(n=>!n.hasClass('layer-hidden')&&!n.hasClass('evidence-hidden')),
       visibleEdges=cy.edges().filter(e=>!e.hasClass('layer-hidden')&&!e.hasClass('evidence-hidden')),
       hidden=cy.elements('.layer-hidden,.evidence-hidden').length,
       byType={};
 visibleNodes.forEach(n=>byType[n.data('type')]=(byType[n.data('type')]||0)+1);
 const extra=['disease','gene','variant','drug','trial','report']
  .filter(t=>byType[t])
  .map(t=>`${byType[t]} ${t}${byType[t]===1?'':'s'}`).join(' · ');
 $('networkSummary').textContent=
  `${visibleNodes.length.toLocaleString()} visible nodes · ${visibleEdges.length.toLocaleString()} visible relationships`+
  `${hidden?` · ${hidden.toLocaleString()} hidden element${hidden===1?'':'s'}`:''}${extra?' · '+extra:''}`;
 updateLayerCounts();
}

function extLinks(a){return !a?.length?'':`<div class="mt-3"><div class="small fw-semibold mb-1">External resources</div>${a.map(x=>`<a class="external-link" target="_blank" rel="noopener" href="${esc(x.url)}">${esc(x.display_label||x.resource_name)} ↗</a>`).join('')}</div>`}
function evidenceLinks(x){const a=[];if(nonempty(x.pmid))String(x.pmid).split(/[|,;\s]+/).forEach(v=>{v=v.replace(/^PMID:/i,'');if(/^\d+$/.test(v))a.push(`<a class="external-link" target="_blank" rel="noopener" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(v)}/">PMID ${esc(v)} ↗</a>`)});if(nonempty(x.doi))String(x.doi).split(/[|;]+/).forEach(v=>{v=v.replace(/^doi:/i,'').replace(/^https?:\/\/(dx\.)?doi\.org\//i,'').trim();if(v)a.push(`<a class="external-link" target="_blank" rel="noopener" href="https://doi.org/${encodeURI(v)}">DOI ↗</a>`)});if(nonempty(x.evidence_source_ids))String(x.evidence_source_ids).split('|').map(s=>s.trim()).forEach(v=>{if(/^NCT\d{8}$/i.test(v))a.push(`<a class="external-link" target="_blank" rel="noopener" href="https://clinicaltrials.gov/study/${encodeURIComponent(v)}">${esc(v)} ↗</a>`)});return [...new Set(a)].join('')}
function titleFor(t,e){return t==='disease'?e.disease_name:t==='gene'?e.gene_symbol:t==='locus'?e.locus_label:t==='drug'?e.preferred_name:t==='trial'?e.nct_id:(e.clinvar_variation_id||e.variant_id||e.title||e.id)}
function props(e){const skip=new Set(['source_record_json','source_file','source_release']);return `<table class="table table-sm property-table"><tbody>${Object.entries(e).filter(([k,v])=>!skip.has(k)&&nonempty(v)&&!['id','label','type'].includes(k)).map(([k,v])=>`<tr><td>${esc(k.replaceAll('_',' '))}</td><td>${esc(v)}</td></tr>`).join('')}</tbody></table>`}
function related(title,rows,type,showEvidence=false){if(!rows?.length)return'';return `<div class="mt-3"><h3 class="h6">${esc(title)} <span class="text-secondary">(${rows.length})</span></h3><div class="list-group list-group-flush border rounded">${rows.map(r=>`<button class="list-group-item list-group-item-action" data-related-type="${esc(type)}" data-related-id="${esc(r.id)}"><div class="fw-semibold">${esc(r.label||r.id)}</div>${showEvidence?evidenceLinks(r):''}</button>`).join('')}</div></div>`}

async function loadEntity(type,id,graphNode=null){
 try{
  const d=await apiGet('entity.php',{type,id}),e=d.entity,r=d.related,label=titleFor(type,e);
  let h=`${badge(type)}<h2 class="h5 mt-2">${esc(label)}</h2>${props(e)}${extLinks(d.external_links)}`;
  if(type==='disease')h+=related('Genes',r.genes,'gene',true)+related('Direct therapeutic evidence',r.drugs,'drug')+related('Clinical trials',r.trials,'trial')+`<div class="alert alert-light border small mt-3"><strong>Variants:</strong> ${Number(r.variant_count).toLocaleString()}</div>`;
  if(type==='gene')h+=related('Diseases',r.diseases,'disease',true)+related('Targeting drugs',r.drugs,'drug')+`<div class="alert alert-light border small mt-3"><strong>Variants:</strong> ${Number(r.variant_count).toLocaleString()}</div>`;
  if(type==='locus')h+=related('Diseases',r.diseases,'disease',true);
  if(type==='drug')h+=related('Direct disease evidence',r.diseases,'disease')+related('Molecular targets',r.targets,'gene')+related('Clinical trials',r.trials,'trial');
  if(type==='trial')h+=related('Diseases',r.diseases,'disease')+related('Investigated drugs',r.drugs,'drug');
  if(type==='variant'){h+=related('Genes',r.genes,'gene')+related('Diseases',r.diseases,'disease');if(r.consequences?.length)h+=`<div class="mt-3"><h3 class="h6">Variant consequence</h3>${r.consequences.map(x=>`<span class="filter-chip">${esc(x.consequence_term)}</span>`).join(' ')}</div>`}
  h+=expansionButtons(type,id,label);
  const n=graphNode||cy.$id(nodeKey(type,id));if(n.length)h+=localNodeActions(n);
  $('detailsPanel').innerHTML=h;bindDetailActions();
 }catch(e){$('detailsPanel').innerHTML=`<div class="alert alert-danger">${esc(e.message)}</div>`}
}

function renderEdge(d){
 const names={disease_gene:'Disease–gene association',disease_locus:'Disease–locus association',disease_variant:'Disease–variant association',gene_variant:'Gene–variant association',variant_consequence:'Variant consequence',direct_disease_drug:'Direct therapeutic evidence',drug_target:'Drug–target pharmacology',target_overlap_only:'Target-overlap discovery',disease_trial:'Disease–clinical trial association',drug_trial:'Drug–clinical trial association',disease_report:'Disease–clinical report association',drug_report:'Drug–clinical report association'};
 const registryClass='registered_trial_condition_intervention';
 const records=Array.isArray(d.evidence_rows)?d.evidence_rows:[];
 const subtypes=String(d.evidence_subtypes||'').split('|').map(x=>x.trim()).filter(Boolean);
 const registry=d.type==='direct_disease_drug'&&d.association_class===registryClass&&subtypes.every(x=>x===registryClass)&&records.every(r=>r&&r.evidence_subtype===registryClass);

 function value(v){
  if(v===null||v===undefined)return '';
  if(Array.isArray(v))return v.length?'<ol>'+v.map(x=>'<li>'+value(x)+'</li>').join('')+'</ol>':'None recorded';
  if(typeof v==='object')return '<table class="table table-sm property-table"><tbody>'+Object.entries(v).map(([k,x])=>'<tr><td>'+esc(k.replaceAll('_',' '))+'</td><td>'+value(x)+'</td></tr>').join('')+'</tbody></table>';
  return esc(String(v));
 }

 const rows=Object.entries(d).filter(([k,v])=>!['id','source','target','type'].includes(k)&&nonempty(v)).map(([k,v])=>'<tr><td>'+esc(k.replaceAll('_',' '))+'</td><td>'+value(v)+'</td></tr>').join('');
 const ids=new Set();

 for(const raw of [d.evidence_source_ids,...records.map(r=>r?.source_id)]){
  for(const part of String(raw||'').split('|')){
   const match=part.trim().match(/^(NCT\d{8})(?::[A-Za-z0-9_-]+)?$/i);
   if(match)ids.add(match[1].toUpperCase());
  }
 }

 const links=evidenceLinks({...d,evidence_source_ids:''})+[...ids].map(id=>'<a class="external-link" target="_blank" rel="noopener noreferrer" href="https://clinicaltrials.gov/study/'+encodeURIComponent(id)+'">'+esc(id)+' ↗</a>').join('');
 const title=registry?'Registered clinical trial association':(names[d.type]||'Evidence');
 const explanation=registry?'<p class="small text-secondary">Registry condition–intervention association. This record does not establish approval or efficacy.</p>':'';

 $('detailsPanel').innerHTML='<div class="evidence-box '+(d.type==='target_overlap_only'?'discovery':'')+'"><div class="small text-uppercase fw-bold text-secondary">Relationship</div><h2 class="h5">'+esc(title)+'</h2>'+explanation+(d.warning?'<div class="alert alert-warning small">'+esc(d.warning)+'</div>':'')+'<table class="table table-sm property-table"><tbody>'+rows+'</tbody></table>'+links+'</div>';
}
/* ODDB_VIEWPORT_BUTTONS_21: viewport changes only; graph data is unchanged. */
document.addEventListener('click', function oddbViewportButton21(event) {
 const button=event.target.closest?.('#oddbViewportControls21 button[data-viewport-action]');
 if(!button || !cy || cy.destroyed())return;
 const action=button.dataset.viewportAction;
 const steps={left:{x:-80,y:0},right:{x:80,y:0},up:{x:0,y:-80},down:{x:0,y:80}};
 if(action==='in'||action==='out'){
  const factor=action==='in'?1.25:0.8;
  const level=Math.max(cy.minZoom(),Math.min(cy.maxZoom(),cy.zoom()*factor));
  cy.zoom({level,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});
 }else if(steps[action]){
  cy.panBy(steps[action]);
 }else if(action==='fit'){
  document.getElementById('fitGraph')?.click();
 }
});


function clearNetwork(){if(cy)cy.elements().remove();selectedGraphNodes.clear();renderGraphSelectionBar();refreshNetworkSummary()}
function clearDiseaseBrowse(){selectedDiseases.clear();renderSelectedDiseaseSummary();$('diseaseList').innerHTML='<div class="p-4 text-center text-secondary small">Select a category above.</div>';$('diseaseCount').textContent='Choose a category.'}

function csvEscape(v){const s=String(v??'');return /[",\n\r]/.test(s)?`"${s.replaceAll('"','""')}"`:s}
function rowsToCsv(rows){const keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];return [keys.map(csvEscape).join(','),...rows.map(r=>keys.map(k=>csvEscape(r[k])).join(','))].join('\r\n')}
function elementRows(elements){const rows=[],nodeLabels=new Map();elements.filter('node').forEach(n=>nodeLabels.set(n.id(),n.data('label')));elements.filter('node').forEach(n=>{const d=n.data();rows.push({record_type:'node',type:d.type,id:d.id,entity_id:d.entity_id,label:d.label,role:pinnedNodes.has(n.id())?'pinned':(selectedGraphNodes.has(n.id())?'selected':(d.seed?'selected disease':(d.expanded?'expanded':'')))})});elements.filter('edge').forEach(e=>{const d=e.data();rows.push({record_type:'relationship',type:d.type,id:d.id,label:d.label||'',source_id:d.source,source_label:nodeLabels.get(d.source)||'',target_id:d.target,target_label:nodeLabels.get(d.target)||'',evidence_class:d.evidence_class||'',evidence_status:d.evidence_status||'',source_name:d.source_name||'',source_record_id:d.source_id||'',pmid:d.pmid||'',doi:d.doi||'',association_class:d.association_class||'',clinical_stage:d.clinical_stage||'',mechanism_of_action:d.mechanism_of_action||'',warning:d.warning||''})});const filters=window.ODDBEvidence?.exportInfo();if(filters)rows.forEach(row=>{row.evidence_filters=JSON.stringify(filters.filters);row.evidence_checked_at=filters.validation?.validated_at||'';});return rows}
function selectedElements(){let nodes=cy.collection();selectedGraphNodes.forEach((_,id)=>{const n=cy.$id(id);if(n.length)nodes=nodes.union(n)});selectedDiseases.forEach((_,id)=>{const n=cy.$id(`disease::${id}`);if(n.length)nodes=nodes.union(n)});const ids=new Set(nodes.map(n=>n.id()));let edges=cy.edges().filter(e=>ids.has(e.source().id())&&ids.has(e.target().id()));return nodes.union(edges).filter(e=>!e.hasClass('layer-hidden')&&!e.hasClass('evidence-hidden'))}
function downloadBlob(blob,filename){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},700)}
function exportCsv(scope){const els=scope==='selected'?selectedElements():visibleElementCollection();if(!els||!els.length){alert('There is no visible network data to export.');return}downloadBlob(new Blob(['\ufeff',rowsToCsv(elementRows(els))],{type:'text/csv;charset=utf-8'}),`oddb-explorer-${scope}-network.csv`)}
function downloadPng(dataUrl,filename){const a=document.createElement('a');a.href=dataUrl;a.download=filename;document.body.appendChild(a);a.click();a.remove()}
async function exportSelectedPng(){const els=selectedElements();if(!els.length){alert('Select graph nodes or diseases first.');return}const div=document.createElement('div');Object.assign(div.style,{position:'fixed',left:'-100000px',top:'0',width:'1600px',height:'1000px',background:'#fff'});document.body.appendChild(div);const clone=cytoscape({container:div,elements:els.jsons(),style:cy.style().json(),layout:{name:'cose',animate:false,fit:true,padding:70}});await new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;resolve()};clone.one('layoutstop',finish);setTimeout(finish,700)});clone.fit(undefined,70);const png=clone.png({full:true,scale:1.5,bg:'#ffffff'});clone.destroy();div.remove();downloadPng(png,'oddb-explorer-selected-subgraph.png')}
function graphExportPixelRatio(){const ratio=Number(window.devicePixelRatio);return Number.isFinite(ratio)&&ratio>0?ratio:1}
function bindExports(){document.querySelectorAll('[data-export]').forEach(btn=>btn.onclick=async()=>{const type=btn.dataset.export;if(type==='viewport-png')downloadPng(cy.png({full:false,scale:2*graphExportPixelRatio(),bg:'#ffffff'}),'oddb-explorer-current-view.png');else if(type==='full-png')downloadPng(cy.png({full:true,scale:1.7*graphExportPixelRatio(),bg:'#ffffff'}),'oddb-explorer-full-network.png');else if(type==='selected-png')await exportSelectedPng();else if(type==='shown-csv')exportCsv('shown');else if(type==='selected-csv')exportCsv('selected');const details=btn.closest('details');if(details)details.open=false})}



/* ============================================================
   ODDB Explorer Global Search + Entity-first Workflows v0.7.4
   ============================================================ */

const ENTITY_SEARCH_TYPES=['disease','gene','variant','drug','trial','report'];
const ENTITY_SEARCH_LABELS={
 disease:'Diseases',gene:'Genes',variant:'Variants',drug:'Drugs',
 trial:'Clinical Trials',report:'Clinical Reports'
};

function syncEntityStarter(){
 const panel=$('entityStarter');
 if(!panel)return;
 const empty=!cy||cy.nodes().length===0;
 panel.classList.toggle('d-none',!empty);
}
function scopedEntitySearchType22(type){
 return ENTITY_SEARCH_TYPES.includes(type)?type:'disease';
}
function syncGlobalSearchTypeFilters(){
 globalSearchType=scopedEntitySearchType22(globalSearchType);
 document.querySelectorAll('[data-global-search-type]').forEach(btn=>{
  const active=btn.dataset.globalSearchType===globalSearchType;
  btn.classList.toggle('active',active);
  btn.setAttribute('aria-pressed',String(active));
 });
 const placeholders={disease:'Search diseases…',gene:'Search HGNC genes…',variant:'Search variants…',drug:'Search drugs…',trial:'Search clinical trials…',report:'Search clinical reports…'};
 if($('globalSearch'))$('globalSearch').placeholder=placeholders[globalSearchType];
}
function focusEntitySearch(type='disease'){
 globalSearchType=scopedEntitySearchType22(type);
 syncGlobalSearchTypeFilters();
 const input=$('globalSearch');
 if(input){
  input.focus();
  input.select();
 }
 const status=$('globalSearchStatus');
 if(status)status.textContent=type?`Searching ${ENTITY_SEARCH_LABELS[type]||type} only`:'';
 const q=input?.value.trim()||'';
 if(q.length>=2)runGlobalSearch(q);
}
function clearGlobalSearch(){
 globalSearchResults=[];
 $('globalSearch').value='';
 $('searchResults').innerHTML='';
 $('searchResults').classList.add('d-none');
 $('globalSearchStatus').textContent='';
}
function globalSearchGroupHtml(type,rows){
 return `<section class="entity-search-group" data-search-group="${esc(type)}">
  <div class="entity-search-group-title">
   <span>${esc(ENTITY_SEARCH_LABELS[type]||type)}</span><span>${rows.length}</span>
  </div>
  ${rows.map((r,idx)=>`
   <article class="entity-search-result" data-search-result-key="${esc(type)}::${esc(r.id)}">
    <button class="entity-search-result-main" type="button" data-search-details="${esc(type)}::${esc(r.id)}">
     <div>${badge(type)} <strong>${esc(r.label)}</strong></div>
     <div class="small text-secondary">${esc(r.subtitle||r.id)}</div>
     <div class="entity-search-id">${esc(r.id)}</div>
    </button>
    <div class="entity-search-actions">
     <button type="button" class="btn btn-sm btn-outline-secondary" data-search-add="${esc(type)}::${esc(r.id)}">Add</button>
     <button type="button" class="btn btn-sm btn-outline-secondary" data-search-pin="${esc(type)}::${esc(r.id)}">Add + pin</button>
     <button type="button" class="btn btn-sm btn-primary" data-search-start="${esc(type)}::${esc(r.id)}">New analysis</button>
    </div>
   </article>`).join('')}
 </section>`;
}
function searchResultByKey(key){
 const [type,...rest]=String(key).split('::'),id=rest.join('::');
 return globalSearchResults.find(r=>r.type===type&&String(r.id)===id)||{type,id,label:id,subtitle:''};
}
function renderGlobalSearchResults(data){
 const box=$('searchResults');
 globalSearchResults=data.results||[];
 const groups=data.groups||{};
 const types=ENTITY_SEARCH_TYPES.filter(t=>Array.isArray(groups[t])&&groups[t].length);
 if(!types.length){
  box.innerHTML='<div class="entity-search-empty">No matching ODDB entities.</div>';
  box.classList.remove('d-none');
  return;
 }
 box.innerHTML=types.map(t=>globalSearchGroupHtml(t,groups[t])).join('');
 box.classList.remove('d-none');

 box.querySelectorAll('[data-search-details]').forEach(btn=>btn.onclick=()=>{
  const r=searchResultByKey(btn.dataset.searchDetails);
  box.classList.add('d-none');
  openSearchEntityDetails(r);
 });
 box.querySelectorAll('[data-search-add]').forEach(btn=>btn.onclick=()=>{
  const r=searchResultByKey(btn.dataset.searchAdd);
  box.classList.add('d-none');
  addEntityToCurrentGraph(r,false);
 });
 box.querySelectorAll('[data-search-pin]').forEach(btn=>btn.onclick=()=>{
  const r=searchResultByKey(btn.dataset.searchPin);
  box.classList.add('d-none');
  addEntityToCurrentGraph(r,true);
 });
 box.querySelectorAll('[data-search-start]').forEach(btn=>btn.onclick=()=>{
  const r=searchResultByKey(btn.dataset.searchStart);
  box.classList.add('d-none');
  startEntityAnalysis(r,{updateUrl:true});
 });
}
async function runGlobalSearch(q){
 globalSearchType=scopedEntitySearchType22(globalSearchType);
 syncGlobalSearchTypeFilters();
 q=String(q||'').trim();
 if(q.length<2){
  $('searchResults').classList.add('d-none');
  $('globalSearchStatus').textContent='';
  return;
 }
 const status=$('globalSearchStatus'),requestType=globalSearchType;
 const isCurrent=()=>q===$('globalSearch').value.trim()&&requestType===globalSearchType;
 status.textContent='Searching…';
 try{
  const d=await apiGet('global_search.php',{q,type:requestType,limit:8});
  if(!isCurrent())return;
  renderGlobalSearchResults(d);
  status.textContent=`${Number(d.total||0)} result${Number(d.total||0)===1?'':'s'}${globalSearchType?` in ${ENTITY_SEARCH_LABELS[globalSearchType]||globalSearchType}`:''}`;
 }catch(e){
  if(!isCurrent())return;
  $('searchResults').innerHTML=`<div class="entity-search-empty text-danger">${esc(e.message)}</div>`;
  $('searchResults').classList.remove('d-none');
  status.textContent='Search failed';
 }
}
async function fetchEntityNode(type,id){
 const d=await apiGet('entity_node.php',{type,id});
 return d.entity;
}
function clearAnalysisForEntityStart(){
 comparisonData=null;comparisonActiveTab='shared_genes';
 pathFinderData=null;pathEndpoints={from:null,to:null};
 selectedDiseases.clear();selectedGraphNodes.clear();pinnedNodes.clear();
 historyStack=[];futureStack=[];breadcrumbSteps=[];
 layerVisibility={...LAYER_DEFAULTS};
 window.ODDBEvidence?.restore(undefined);
 window.ODDBDrugComparison?.restore(undefined);
 focusActive=false;
 if(cy)cy.elements().remove();
 clearComparison();
 renderPathFinder();syncPathFinderControls();
 renderSelectedDiseaseSummary();renderGraphSelectionBar();renderPinnedBar();renderHistoryBar();
 syncLayerControls();applyLayerVisibility(false);
 if(selectedCategory)loadDiseases();
}
function positionStandaloneNode(node){
 if(!cy||!node?.length)return;
 const ext=cy.extent();
 const x=Number.isFinite(ext.x1)&&Number.isFinite(ext.x2)?(ext.x1+ext.x2)/2:0;
 const y=Number.isFinite(ext.y1)&&Number.isFinite(ext.y2)?(ext.y1+ext.y2)/2:0;
 node.position({x,y});
}
async function addEntityToCurrentGraph(result,pin=false){
 const before=snapshotGraphState();
 try{
  const e=await fetchEntityNode(result.type,result.id);
  const id=nodeKey(e.type,e.id);
  const existed=cy.$id(id).length>0;
  if(!existed){
   mergeElements([{data:{
    id,entity_id:e.id,label:e.label,type:e.type,subtitle:e.subtitle||'',
    expanded:1,entity_first:1
   }}],{relayout:false});
  }
  const node=cy.$id(id);
  if(!existed)positionStandaloneNode(node);
  if(pin){
   pinnedNodes.set(id,{...node.data()});
   renderPinnedBar();
  }
  selectOnlyGraphNode(node);
  renderNodeDetails(node);
  syncWorkbenchClasses();applyLayerVisibility(false);refreshNetworkSummary();
  if(!existed)commitHistory(before,`${e.label} added from global search`);
  if(node.length)cy.animate({fit:{eles:node,padding:150},duration:280});
  showNotice(existed?`${e.label} is already in the graph.`:`${e.label} added to the current analysis${pin?' and pinned':''}.`,'success',3400);
 }catch(err){showNotice(err.message,'warning',6000)}
}
async function startEntityAnalysis(result,{updateUrl=true,silent=false}={}){
 try{
  const e=await fetchEntityNode(result.type,result.id);
  clearAnalysisForEntityStart();
  const id=nodeKey(e.type,e.id);
  cy.add({data:{
   id,entity_id:e.id,label:e.label,type:e.type,subtitle:e.subtitle||'',
   seed:1,expanded:1,entity_first:1
  }});
  const node=cy.$id(id);
  positionStandaloneNode(node);
  selectOnlyGraphNode(node);
  renderNodeDetails(node);
  syncWorkbenchClasses();applyLayerVisibility(false);refreshNetworkSummary();
  cy.fit(node,170);
  breadcrumbSteps=[`Started with ${e.label}`];
  renderHistoryBar();
  if(updateUrl){
   const u=new URL(location.href);
   u.search='';
   u.searchParams.set('type',e.type);
   u.searchParams.set('id',e.id);
   history.replaceState({oddbEntity:true},'',u);
  }
  if(!silent)showNotice(`New ${e.type}‑centric analysis started with ${e.label}.`,'success',3600);
 }catch(err){
  $('detailsPanel').innerHTML=`<div class="alert alert-danger">${esc(err.message)}</div>`;
  if(!silent)showNotice(err.message,'warning',6000);
 }
}
async function openSearchEntityDetails(result){
 const node=cy.$id(nodeKey(result.type,result.id));
 if(node.length){
  selectOnlyGraphNode(node);renderNodeDetails(node);
  cy.animate({fit:{eles:node,padding:150},duration:250});
  return;
 }
 if(result.type==='report'){
  $('detailsPanel').innerHTML=`${badge(result.type)}<h2 class="h5 mt-2">${esc(result.label)}</h2>
   <p class="small text-secondary">${esc(result.subtitle||result.id)}</p>
   <div class="detail-actions mt-3">
    <button id="detailAddSearchEntity" class="btn btn-sm btn-outline-primary">Add to current graph</button>
    <button id="detailStartSearchEntity" class="btn btn-sm btn-primary">Start new analysis</button>
   </div>`;
  $('detailAddSearchEntity').onclick=()=>addEntityToCurrentGraph(result,false);
  $('detailStartSearchEntity').onclick=()=>startEntityAnalysis(result,{updateUrl:true});
 }else{
  await loadEntity(result.type,result.id);
 }
}
function bindGlobalEntitySearch(){
 $('globalSearch').oninput=()=>{
  clearTimeout(globalSearchTimer);
  const q=$('globalSearch').value.trim();
  if(q.length<2){
   $('searchResults').classList.add('d-none');
   $('globalSearchStatus').textContent='';
   return;
  }
  globalSearchTimer=setTimeout(()=>runGlobalSearch(q),220);
 };
 $('globalSearch').onkeydown=e=>{
  if(e.key==='Escape')$('searchResults').classList.add('d-none');
  if(e.key==='Enter'){
   const first=globalSearchResults[0];
   if(first){e.preventDefault();$('searchResults').classList.add('d-none');openSearchEntityDetails(first)}
  }
 };
 $('clearGlobalSearch').onclick=clearGlobalSearch;
 document.querySelectorAll('[data-global-search-type]').forEach(btn=>btn.onclick=()=>{
  globalSearchType=scopedEntitySearchType22(btn.dataset.globalSearchType);
  syncGlobalSearchTypeFilters();
  const q=$('globalSearch').value.trim();
  if(q.length>=2)runGlobalSearch(q);
  else focusEntitySearch(globalSearchType);
 });
 document.querySelectorAll('[data-entity-starter]').forEach(btn=>btn.onclick=()=>focusEntitySearch(btn.dataset.entityStarter));
 document.addEventListener('click',e=>{
  const wrap=document.querySelector('.entity-search-strip');
  if(wrap&&!wrap.contains(e.target))$('searchResults').classList.add('d-none');
 });
 syncGlobalSearchTypeFilters();
}

/* ============================================================
   ODDB Explorer Disease Comparison + Shared Neighbors v0.7.2
   ============================================================ */

const COMPARISON_TABS=[
 ['shared_genes','Shared genes'],
 ['unique_genes','Unique genes'],
 ['shared_variants','Shared variants'],
 ['unique_variants','Unique variants'],
 ['shared_direct_drugs','Shared direct drugs'],
 ['unique_direct_drugs','Unique direct drugs'],
 ['shared_overlap_drugs','Shared target-overlap drugs'],
 ['shared_trials','Shared trials'],
 ['shared_reports','Shared reports'],
 ['shared_target_drugs','Multi-gene targeting drugs']
];

function renderComparisonSelection(){
 const box=$('comparisonSelection'),btn=$('runComparison');
 if(!box||!btn)return;
 const rows=[...selectedDiseases.values()],n=rows.length;
 btn.disabled=n<2||n>5;
 if(!n){
  box.innerHTML='Select 2–5 diseases in the disease panel.';
  return;
 }
 const names=rows.map(x=>x.disease_name||x.label||x.disease_id).map(esc);
 box.innerHTML=`<strong>${n} selected:</strong> ${names.join(' · ')}${
  n>5?' <span class="text-danger fw-semibold">— comparison is limited to 5 diseases.</span>':
  n<2?' <span class="text-secondary">— select at least one more disease.</span>':''
 }`;
}

function comparisonEntityKey(type,id){return `${type}::${id}`}

function comparisonCountLabel(item){
 const n=Number(item.disease_count||0);
 return n?`${n} selected disease${n===1?'':'s'}`:'';
}

function renderComparison(){
 if(!comparisonData)return;
 const summary=$('comparisonSummary'),tabs=$('comparisonTabs'),results=$('comparisonResults');
 const s=comparisonData.summary||{},d=comparisonData.diseases||[];

 summary.classList.remove('d-none');
 summary.innerHTML=`
  <div class="comparison-kpis">
   <div><strong>${d.length}</strong><span>diseases compared</span></div>
   <div><strong>${Number(s.shared_genes||0)}</strong><span>shared genes</span></div>
   <div><strong>${Number(s.shared_variants||0)}</strong><span>shared variants</span></div>
   <div><strong>${Number(s.shared_direct_drugs||0)}</strong><span>shared direct drugs</span></div>
   <div><strong>${Number(s.shared_overlap_drugs||0)}</strong><span>shared target-overlap drugs</span></div>
   <div><strong>${Number(s.shared_target_drugs||0)}</strong><span>multi-gene targeting drugs</span></div>
  </div>
  <div class="comparison-semantics">
   <strong>Interpretation:</strong> “Shared” means linked to at least two of the selected diseases.
   Direct therapeutic evidence and target-overlap discovery are intentionally reported separately.
  </div>`;

 tabs.classList.remove('d-none');
 tabs.innerHTML=COMPARISON_TABS.map(([key,label])=>{
  const n=(comparisonData.results?.[key]||[]).length;
  return `<button class="comparison-tab ${comparisonActiveTab===key?'active':''}" data-comparison-tab="${key}">
   ${esc(label)} <span>${n}</span>
  </button>`;
 }).join('');
 tabs.querySelectorAll('[data-comparison-tab]').forEach(b=>b.onclick=()=>{
  comparisonActiveTab=b.dataset.comparisonTab;
  renderComparison();
 });

 const rows=comparisonData.results?.[comparisonActiveTab]||[];
 results.classList.remove('d-none');
 if(!rows.length){
  results.innerHTML='<div class="comparison-empty">No matching relationships were found for this comparison.</div>';
  return;
 }

 const isUnique=comparisonActiveTab.startsWith('unique_');
 results.innerHTML=`<div class="comparison-result-grid">${
  rows.map(item=>{
   const diseaseNames=(item.diseases||[]).map(x=>x.disease_name).join(' · ');
   const targetInfo=item.target_gene_count?`${item.target_gene_count} selected-disease genes targeted`:'';
   const warning=item.discovery_only?'Target-overlap discovery only; not direct therapeutic evidence.':'';
   return `<button class="comparison-result-card" data-compare-type="${esc(item.type)}" data-compare-id="${esc(item.id)}">
    <div class="comparison-result-top">
     ${badge(item.type)}
     <span class="comparison-link-count">${esc(comparisonCountLabel(item))}</span>
    </div>
    <div class="comparison-result-name">${esc(item.label)}</div>
    ${item.owner_disease_name?`<div class="comparison-owner">Unique to ${esc(item.owner_disease_name)}</div>`:''}
    ${diseaseNames?`<div class="comparison-diseases">${esc(diseaseNames)}</div>`:''}
    ${targetInfo?`<div class="comparison-target-info">${esc(targetInfo)}</div>`:''}
    ${warning?`<div class="comparison-warning">${esc(warning)}</div>`:''}
   </button>`;
  }).join('')
 }</div>`;

 results.querySelectorAll('[data-compare-type]').forEach(card=>card.onclick=()=>{
  highlightComparisonEntity(card.dataset.compareType,card.dataset.compareId);
 });
}

function highlightComparisonEntity(type,id){
 if(!cy)return;
 const key=comparisonEntityKey(type,id),node=cy.$id(key);
 cy.elements().removeClass('comparison-match comparison-context');

 if(node.length){
  node.addClass('comparison-match');
  node.closedNeighborhood().addClass('comparison-context');
  if(node.hasClass('layer-hidden')){
   const lk=nodeLayerKey(node);
   if(lk&&layerVisibility[lk]===false){
    layerVisibility[lk]=true;
    syncLayerControls();
    applyLayerVisibility(false);
   }
  }
  cy.animate({fit:{eles:node.closedNeighborhood(),padding:90},duration:350});
  selectOnlyGraphNode(node);
  loadEntity(type,id,node);
  showNotice(`${node.data('label')} highlighted in the current network.`,'success',2600);
 }else{
  showNotice('This comparison result is not currently loaded in the graph. Use its entity details or expand the relevant disease to add it.','info',4200);
  loadEntity(type,id);
 }
}

async function runDiseaseComparison(){
 const ids=[...selectedDiseases.keys()];
 if(ids.length<2||ids.length>5){
  showNotice('Select between 2 and 5 diseases for comparison.','warning');
  return;
 }
 const btn=$('runComparison');
 btn.disabled=true;btn.textContent='Comparing…';
 try{
  comparisonData=await apiGet('compare.php',{disease_ids:ids});
  comparisonActiveTab='shared_genes';
  renderComparison();
  showNotice(`Compared ${ids.length} selected diseases.`,'success',2600);
 }catch(e){
  $('comparisonResults').classList.remove('d-none');
  $('comparisonResults').innerHTML=`<div class="alert alert-danger mb-0">${esc(e.message)}</div>`;
 }finally{
  btn.textContent='Compare selected diseases';
  renderComparisonSelection();
 }
}

function clearComparison(){
 comparisonData=null;
 comparisonActiveTab='shared_genes';
 ['comparisonSummary','comparisonTabs','comparisonResults'].forEach(id=>{
  const el=$(id);if(el){el.classList.add('d-none');el.innerHTML=''}
 });
 if(cy)cy.elements().removeClass('comparison-match comparison-context');
 renderComparisonSelection();
}



/* ============================================================
   ODDB Explorer Evidence-aware Path Finder v0.7.3
   ============================================================ */

const PATH_ENDPOINT_TYPES=new Set(['disease','gene','variant','drug']);

function pathEndpointLabel(e){
 if(!e)return '';
 return `${e.label||e.id} (${e.type})`;
}
function syncPathFinderControls(){
 ['from','to'].forEach(side=>{
  const e=pathEndpoints[side];
  const cap=side[0].toUpperCase()+side.slice(1);
  const chosen=$(`path${cap}Chosen`);
  const input=$(`path${cap}Search`);
  if(chosen)chosen.innerHTML=e?`${badge(e.type)} <strong>${esc(e.label||e.id)}</strong> <span>${esc(e.id)}</span>`:`No ${side==='from'?'start':'destination'} entity selected.`;
  if(input&&e&&document.activeElement!==input)input.value=e.label||e.id;
 });
 const ok=!!(pathEndpoints.from&&pathEndpoints.to&&
   !(pathEndpoints.from.type===pathEndpoints.to.type&&pathEndpoints.from.id===pathEndpoints.to.id));
 $('findPaths').disabled=!ok;
}
function setPathEndpoint(side,e){
 if(!e||!PATH_ENDPOINT_TYPES.has(e.type))return;
 pathEndpoints[side]={type:e.type,id:e.id,label:e.label||e.id,subtitle:e.subtitle||''};
 const cap=side[0].toUpperCase()+side.slice(1);
 const input=$(`path${cap}Search`);
 if(input)input.value=e.label||e.id;
 const box=$(`path${cap}Results`);
 if(box)box.classList.add('d-none');
 syncPathFinderControls();
}
async function searchPathEndpoint(side,q){
 const cap=side[0].toUpperCase()+side.slice(1),box=$(`path${cap}Results`);
 if(!box)return;
 if(q.trim().length<2){box.classList.add('d-none');return}
 try{
  const d=await apiGet('search.php',{q:q.trim()});
  if(q.trim()!==$(`path${cap}Search`).value.trim())return;
  const rows=(d.results||[]).filter(r=>PATH_ENDPOINT_TYPES.has(r.type)).slice(0,12);
  box.innerHTML=rows.length?rows.map(r=>`
   <button type="button" class="search-item path-search-item" data-path-side="${side}" data-path-type="${esc(r.type)}" data-path-id="${esc(r.id)}" data-path-label="${esc(r.label)}" data-path-subtitle="${esc(r.subtitle||'')}">
    ${badge(r.type)} <strong class="ms-1">${esc(r.label)}</strong>
    <div class="small text-secondary">${esc(r.subtitle||r.id)}</div>
   </button>`).join(''):'<div class="search-item text-secondary">No disease, gene, variant or drug matches.</div>';
  box.classList.remove('d-none');
  box.querySelectorAll('[data-path-side]').forEach(el=>el.onclick=()=>setPathEndpoint(side,{
   type:el.dataset.pathType,id:el.dataset.pathId,label:el.dataset.pathLabel,subtitle:el.dataset.pathSubtitle
  }));
 }catch(e){
  if(q.trim()!==$(`path${cap}Search`).value.trim())return;
  box.innerHTML=`<div class="search-item text-danger">${esc(e.message)}</div>`;
  box.classList.remove('d-none');
 }
}
function bindPathSearch(side){
 const cap=side[0].toUpperCase()+side.slice(1),input=$(`path${cap}Search`);
 input.oninput=()=>{
  pathEndpoints[side]=null;
  syncPathFinderControls();
  clearTimeout(pathSearchTimers[side]);
  pathSearchTimers[side]=setTimeout(()=>searchPathEndpoint(side,input.value),220);
 };
 input.onfocus=()=>{if(input.value.trim().length>=2)searchPathEndpoint(side,input.value)};
}
function useSelectedForPath(side){
 if(selectedGraphNodes.size!==1){
  showNotice('Select exactly one disease, gene, variant or drug node in the graph first.','warning',4200);
  return;
 }
 const d=[...selectedGraphNodes.values()][0];
 if(!PATH_ENDPOINT_TYPES.has(d.type)){
  showNotice('Path Finder endpoints can currently be Disease, Gene, Variant or Drug.','warning',4200);
  return;
 }
 setPathEndpoint(side,{type:d.type,id:d.entity_id,label:d.label||d.entity_id,subtitle:d.subtitle||''});
}
function swapPathEndpoints(){
 const a=pathEndpoints.from;
 pathEndpoints.from=pathEndpoints.to;
 pathEndpoints.to=a;
 ['from','to'].forEach(side=>{
  const cap=side[0].toUpperCase()+side.slice(1),e=pathEndpoints[side];
  $(`path${cap}Search`).value=e?(e.label||e.id):'';
 });
 syncPathFinderControls();
}
function pathBadgeClass(c){
 return c==='direct'?'direct':c==='target_overlap'?'discovery':c==='clinical'?'clinical':'supported';
}
function pathChainHtml(path){
 return (path.nodes||[]).map((n,i)=>`${i?'<span class="path-arrow">→</span>':''}
   <span class="path-chain-node">${badge(n.type)} <strong>${esc(n.label)}</strong></span>`).join('');
}
function pathMetadataHtml(meta){
 const entries=Object.entries(meta||{}).filter(([k,v])=>v!==null&&v!==''&&v!==undefined);
 if(!entries.length)return '';
 return `<dl class="path-edge-meta">${entries.map(([k,v])=>`<div><dt>${esc(k.replaceAll('_',' '))}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`;
}
function renderPathFinder(){
 const out=$('pathFinderResults'),summary=$('pathFinderSummary');
 if(!pathFinderData){
  out.classList.add('d-none');out.innerHTML='';
  summary.textContent='Choose a From and To entity.';
  return;
 }
 const paths=pathFinderData.paths||[];
 const from=pathFinderData.from,to=pathFinderData.to;
 summary.innerHTML=`<strong>${paths.length}</strong> path${paths.length===1?'':'s'} found from <strong>${esc(from.label)}</strong> to <strong>${esc(to.label)}</strong>. Shorter evidence-supported paths are shown first.`;
 out.classList.remove('d-none');
 if(!paths.length){
  out.innerHTML=`<div class="path-empty">
   No supported path was found within ${Number(pathFinderData.max_length)} relationship${Number(pathFinderData.max_length)===1?'':'s'}.
   This does not establish that no biological relationship exists; it means no path was found in the ODDB relationships queried by this Path Finder.
  </div>`;
  return;
 }
 out.innerHTML=paths.map((p,idx)=>`
  <article class="path-card" data-path-index="${idx}">
   <div class="path-card-head">
    <div>
     <span class="path-number">Path ${idx+1}</span>
     <span class="path-badge ${pathBadgeClass(p.classification)}">${esc(p.classification_label)}</span>
     <span class="path-length">${Number(p.length)} relationship${Number(p.length)===1?'':'s'}</span>
    </div>
    <button class="btn btn-sm btn-outline-primary" data-add-path="${idx}">Add path to graph</button>
   </div>
   <div class="path-chain">${pathChainHtml(p)}</div>
   <div class="path-edges">
    ${(p.edges||[]).map((e,j)=>`
     <details class="path-edge-detail">
      <summary><strong>${j+1}. ${esc(e.label)}</strong><span>${esc(e.semantic_label||'')}</span></summary>
      <div class="path-edge-body">
       <div>${esc(e.explanation||'')}</div>
       ${pathMetadataHtml(e.metadata)}
       ${e.warning?`<div class="path-warning">${esc(e.warning)}</div>`:''}
      </div>
     </details>`).join('')}
   </div>
   ${p.warning?`<div class="path-warning mt-2">${esc(p.warning)}</div>`:''}
  </article>`).join('');
 out.querySelectorAll('[data-add-path]').forEach(btn=>btn.onclick=()=>addPathToGraph(Number(btn.dataset.addPath)));
}
async function findPaths(){
 const a=pathEndpoints.from,b=pathEndpoints.to;
 if(!a||!b)return;
 const btn=$('findPaths');btn.disabled=true;btn.textContent='Finding…';
 $('pathFinderSummary').textContent='Searching ODDB evidence relationships…';
 $('pathFinderResults').classList.add('d-none');
 try{
  pathFinderData=await apiGet('pathfinder.php',{
   from_type:a.type,from_id:a.id,to_type:b.type,to_id:b.id,
   max_length:Number($('pathMaxLength').value||3),max_paths:10
  });
  renderPathFinder();
 }catch(e){
  pathFinderData=null;
  $('pathFinderSummary').innerHTML=`<span class="text-danger">${esc(e.message)}</span>`;
 }finally{
  btn.textContent='Find paths';syncPathFinderControls();
 }
}
function pathLayerKeys(path){
 const keys=new Set();
 for(const el of path.elements||[]){
  const d=el.data||{};
  const adapter={data:key=>d[key]};
  const k=(d.source&&d.target)?edgeLayerKey(adapter):nodeLayerKey(adapter);
  if(k)keys.add(k);
 }
 return keys;
}
function addPathToGraph(index){
 const p=pathFinderData?.paths?.[index];
 if(!p||!cy)return;
 const before=snapshotGraphState();
 cy.elements().removeClass('path-highlight');
 pathLayerKeys(p).forEach(k=>{if(k in layerVisibility)layerVisibility[k]=true});
 syncLayerControls();
 const added=mergeElements(p.elements||[],{relayout:false});
 applyLayerVisibility(false);
 for(const el of p.elements||[]){
  const x=cy.$id(el.data?.id);
  if(x.length)x.addClass('path-highlight');
 }
 layout();
 const ids=(p.elements||[]).map(x=>x.data?.id).filter(Boolean);
 let coll=cy.collection();
 ids.forEach(id=>{const e=cy.$id(id);if(e.length)coll=coll.union(e)});
 if(coll.length)cy.fit(coll,75);
 commitHistory(before,`Path: ${pathFinderData.from.label} → ${pathFinderData.to.label}`);
 showNotice(`${added} new graph element(s) added from Path ${index+1}. The path is highlighted in green.`,'success',5000);
}
function clearPathFinder(){
 pathFinderData=null;
 pathEndpoints={from:null,to:null};
 ['From','To'].forEach(cap=>{
  const input=$(`path${cap}Search`),box=$(`path${cap}Results`);
  if(input)input.value='';
  if(box){box.innerHTML='';box.classList.add('d-none')}
 });
 if(cy)cy.elements().removeClass('path-highlight');
 renderPathFinder();syncPathFinderControls();
}

function bind(){
 document.querySelectorAll('[data-category-system]').forEach(b=>b.onclick=()=>{categorySystem=b.dataset.categorySystem;selectedCategory='';clearDiseaseBrowse();document.querySelectorAll('[data-category-system]').forEach(x=>{x.classList.toggle('btn-primary',x===b);x.classList.toggle('btn-light',x!==b)});renderCategories()});
 document.querySelectorAll('[data-data-mode]').forEach(b=>b.onclick=()=>{dataMode=b.dataset.dataMode;selectedSubtype='';document.querySelectorAll('[data-data-mode]').forEach(x=>{x.classList.toggle('btn-primary',x===b);x.classList.toggle('btn-light',x!==b)});renderSubtypes();if(selectedCategory)loadDiseases()});
 $('diseaseSearch').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>selectedCategory&&loadDiseases(),250)};
 $('fitGraph').onclick=()=>cy.fit(undefined,35);$('relayoutGraph').onclick=layout;
 $('historyBack').onclick=historyBack;$('historyForward').onclick=historyForward;
 $('runComparison').onclick=runDiseaseComparison;$('clearComparison').onclick=clearComparison;
 bindPathSearch('from');bindPathSearch('to');
 $('pathUseSelectedFrom').onclick=()=>useSelectedForPath('from');
 $('pathUseSelectedTo').onclick=()=>useSelectedForPath('to');
 $('swapPathEndpoints').onclick=swapPathEndpoints;
 $('findPaths').onclick=findPaths;
 $('clearPathFinder').onclick=clearPathFinder;
 document.querySelectorAll('[data-layer-toggle]').forEach(input=>input.onchange=()=>{
  layerVisibility[input.dataset.layerToggle]=input.checked;
  applyLayerVisibility(true);
  showNotice(input.checked?`${input.dataset.layerToggle} layer shown.`:`${input.dataset.layerToggle} layer hidden; data remain in the analysis.`,'info',2400);
 });
 $('showDirect').onchange=()=>selectedDiseases.size&&loadNetwork();$('showOverlap').onchange=()=>selectedDiseases.size&&loadNetwork();
 $('clearSelection').onclick=()=>{selectedDiseases.clear();renderSelectedDiseaseSummary();if(selectedCategory)loadDiseases()};
 $('selectAllShown').onclick=selectAllShown;$('updateNetwork').onclick=loadNetwork;
 $('expandSelected').onclick=()=>expandSelection($('expandAction').value||'all');
 $('pinSelected').onclick=pinSelected;$('unpinSelected').onclick=unpinSelected;$('focusSelected').onclick=focusSelected;$('showAllNodes').onclick=showAllNodes;$('clearUnpinned').onclick=clearUnpinned;$('resetAnalysis').onclick=()=>{if(window.confirm('Reset the complete Explorer analysis?'))resetAnalysis()};

 bindGlobalEntitySearch();
}

function syncModeButtons(){document.querySelectorAll('[data-category-system]').forEach(x=>{const a=x.dataset.categorySystem===categorySystem;x.classList.toggle('btn-primary',a);x.classList.toggle('btn-light',!a)});document.querySelectorAll('[data-data-mode]').forEach(x=>{const a=x.dataset.dataMode===dataMode;x.classList.toggle('btn-primary',a);x.classList.toggle('btn-light',!a)})}
async function applyUrlState(){
 const p=new URLSearchParams(location.search),sys=p.get('system'),mode=p.get('mode'),category=p.get('category'),subtype=p.get('subtype');
 if(sys==='anatomy'||sys==='inheritance')categorySystem=sys;
 if(mode==='gene'||mode==='variant')dataMode=mode;
 if(category)selectedCategory=category;if(subtype)selectedSubtype=subtype;
 syncModeButtons();renderCategories();renderSubtypes();
 if(selectedCategory)await loadDiseases();
 const type=p.get('type'),id=p.get('id');
 if(type&&id&&ENTITY_SEARCH_TYPES.includes(type)){
  await startEntityAnalysis({type,id,label:id},{updateUrl:false,silent:true});
 }
}

async function boot(){
 initCy();bind();bindExports();renderSelectedDiseaseSummary();renderGraphSelectionBar();renderPinnedBar();renderHistoryBar();syncLayerControls();applyLayerVisibility(false);syncEntityStarter();syncGlobalSearchTypeFilters();
 try{await loadTaxonomy();await applyUrlState()}catch(e){$('detailsPanel').innerHTML=`<div class="alert alert-danger">Could not initialize the ODDB explorer.<br>${esc(e.message)}</div>`}
}
document.addEventListener('DOMContentLoaded',boot);
