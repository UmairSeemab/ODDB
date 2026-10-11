const esc=s=>String(s??'')
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
 .replaceAll('"','&quot;').replaceAll("'","&#039;");
const fmt=n=>Number(n||0).toLocaleString();

const charts={};
function chart(id){const el=document.getElementById(id);if(!el)return null;charts[id]=charts[id]||echarts.init(el,null,{renderer:'canvas'});return charts[id]}
function isMobile(){return window.innerWidth<768}
function isNarrow(){return window.innerWidth<520}

async function getStats(){const r=await fetch('api/stats.php');const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.error||`HTTP ${r.status}`);return d}
function overviewCard(label,value){return `<div class="overview-card"><div class="overview-value">${fmt(value)}</div><div class="overview-label">${esc(label)}</div></div>`}

function pieOption(rows,nameKey,valueKey,centerText='',centerValue=null){
 const total=rows.reduce((a,x)=>a+Number(x[valueKey]||0),0);
 return {
  aria:{enabled:true},
  tooltip:{trigger:'item',formatter:p=>`${esc(p.name)}<br><strong>${fmt(p.value)}</strong> (${p.percent}%)`},
  legend:{type:'scroll',bottom:0,left:'center',textStyle:{fontSize:isMobile()?10:11}},
  series:[{type:'pie',radius:isNarrow()?['42%','66%']:['48%','72%'],center:['50%',isMobile()?'43%':'44%'],
   avoidLabelOverlap:true,itemStyle:{borderColor:'#fff',borderWidth:2,borderRadius:4},label:{show:false},
   emphasis:{label:{show:true,fontSize:isMobile()?12:14,fontWeight:'bold'}},
   data:rows.map(x=>({name:String(x[nameKey]),value:Number(x[valueKey]||0)}))}],
  graphic:centerText?[{type:'text',left:'center',top:isMobile()?'37%':'38%',
   style:{text:centerText.replace('{total}',fmt(centerValue===null?total:centerValue)),textAlign:'center',textVerticalAlign:'middle',
   fill:'#172033',font:isMobile()?'700 13px system-ui':'700 15px system-ui',lineHeight:isMobile()?17:20}}]:[]
 };
}

function treemapOption(rows,nameKey,valueKey){
 const positive=rows.filter(x=>Number(x[valueKey]||0)>0);
 return {aria:{enabled:true},tooltip:{formatter:p=>`${esc(p.name)}<br><strong>${fmt(p.value)}</strong>`},
  series:[{type:'treemap',roam:false,nodeClick:false,breadcrumb:{show:false},visibleMin:1,
  label:{show:true,formatter:p=>`${p.name}
${fmt(p.value)}`,fontSize:isMobile()?10:12,overflow:'truncate'},
  itemStyle:{borderColor:'#fff',borderWidth:2,gapWidth:2},
  data:positive.map(x=>({name:String(x[nameKey]),value:Number(x[valueKey]||0)}))}]};
}

function sankeyOption(t){
 const union=Number(t.direct_without_target)+Number(t.direct_plus_target)+Number(t.target_only);
 const nodes=[{name:'Observed disease–drug pairs'},{name:'Direct only'},{name:'Direct + target overlap'},{name:'Target-overlap only'},{name:'Therapeutic evidence'},{name:'Discovery-only'}];
 const links=[
  {source:'Observed disease–drug pairs',target:'Direct only',value:Number(t.direct_without_target)},
  {source:'Observed disease–drug pairs',target:'Direct + target overlap',value:Number(t.direct_plus_target)},
  {source:'Observed disease–drug pairs',target:'Target-overlap only',value:Number(t.target_only)},
  {source:'Direct only',target:'Therapeutic evidence',value:Number(t.direct_without_target)},
  {source:'Direct + target overlap',target:'Therapeutic evidence',value:Number(t.direct_plus_target)},
  {source:'Target-overlap only',target:'Discovery-only',value:Number(t.target_only)}];
 return {aria:{enabled:true},tooltip:{trigger:'item',triggerOn:'mousemove',formatter:p=>p.dataType==='edge'?`${esc(p.data.source)} → ${esc(p.data.target)}<br><strong>${fmt(p.data.value)}</strong> pairs`:`${esc(p.name)}`},
  series:[{type:'sankey',orient:isMobile()?'vertical':'horizontal',left:isMobile()?18:10,right:isMobile()?18:16,top:18,bottom:18,
   nodeWidth:isMobile()?18:22,nodeGap:isMobile()?14:18,draggable:!isMobile(),emphasis:{focus:'adjacency'},
   label:{fontSize:isMobile()?10:12,color:'#334155'},lineStyle:{color:'gradient',curveness:.5,opacity:.45},data:nodes,links}],
  graphic:[{type:'text',right:10,bottom:2,style:{text:`Unique union: ${fmt(union)} disease–drug pairs`,fill:'#64748b',font:'11px system-ui'}}]};
}



function evidenceOrbitOption(kind,entityCount,diseaseCount,drugCount){
 const title=kind==='trial'?'Clinical trials':'Clinical reports';
 const entityLabel=kind==='trial'?'Trials':'Reports';
 const diseaseDensity=entityCount?diseaseCount/entityCount:0;
 const drugDensity=entityCount?drugCount/entityCount:0;

 return {
  aria:{enabled:true},
  tooltip:{
   confine:true,
   formatter:p=>{
    if(p.dataType==='edge'){
     return `${esc(p.data.label)}<br><strong>${fmt(p.data.value)}</strong> relationship rows`;
    }
    if(p.data.role==='entity'){
     return `${esc(title)}<br><strong>${fmt(entityCount)}</strong> unique records`;
    }
    return `${esc(p.data.fullLabel)}<br><strong>${fmt(p.data.value)}</strong> relationship rows`;
   }
  },
  series:[{
   type:'graph',
   layout:'none',
   roam:false,
   emphasis:{focus:'adjacency'},
   label:{show:true,color:'#172033',fontWeight:700,fontSize:isMobile()?10:12},
   edgeLabel:{
    show:!isMobile(),
    formatter:p=>`${Number(p.data.density).toFixed(2)} / record`,
    color:'#64748b',
    fontSize:10
   },
   lineStyle:{width:isMobile()?3:4,curveness:.18,opacity:.42},
   data:[
    {
     name:entityLabel,fullLabel:title,role:'entity',value:Number(entityCount),
     x:50,y:58,symbol:'circle',symbolSize:isMobile()?96:116,
     itemStyle:{color:'#5b6fc9'},
     label:{formatter:`${fmt(entityCount)}\n${entityLabel}`,color:'#fff',fontSize:isMobile()?13:15,lineHeight:isMobile()?17:20}
    },
    {
     name:'Disease links',fullLabel:'Disease associations',role:'association',value:Number(diseaseCount),
     x:18,y:20,symbol:'circle',symbolSize:isMobile()?72:88,
     itemStyle:{color:'#8dcc70'},
     label:{formatter:`${fmt(diseaseCount)}\nDisease links`,color:'#fff',fontSize:isMobile()?10:12,lineHeight:isMobile()?14:17}
    },
    {
     name:'Drug links',fullLabel:'Drug associations',role:'association',value:Number(drugCount),
     x:82,y:20,symbol:'circle',symbolSize:isMobile()?72:88,
     itemStyle:{color:'#f3b64b'},
     label:{formatter:`${fmt(drugCount)}\nDrug links`,color:'#fff',fontSize:isMobile()?10:12,lineHeight:isMobile()?14:17}
    }
   ],
   links:[
    {source:entityLabel,target:'Disease links',value:Number(diseaseCount),density:diseaseDensity,label:'Disease associations',lineStyle:{color:'#8dcc70'}},
    {source:entityLabel,target:'Drug links',value:Number(drugCount),density:drugDensity,label:'Drug associations',lineStyle:{color:'#f3b64b'}}
   ]
  }]
 };
}

function evidenceMetrics(entityCount,diseaseCount,drugCount){
 const diseaseDensity=entityCount?diseaseCount/entityCount:0;
 const drugDensity=entityCount?drugCount/entityCount:0;
 return [
  `<div class="clinical-metric"><strong>${fmt(entityCount)}</strong><span>Unique evidence records</span></div>`,
  `<div class="clinical-metric"><strong>${diseaseDensity.toFixed(2)}</strong><span>Disease links per record</span></div>`,
  `<div class="clinical-metric"><strong>${drugDensity.toFixed(2)}</strong><span>Drug links per record</span></div>`
 ].join('');
}

function stageLabel(v){const s=String(v??'');const m={APPROVAL:'Approval-stage',PHASE_1:'Phase 1',PHASE_1_2:'Combined Phase 1/2',PHASE_2:'Phase 2',PHASE_2_3:'Combined Phase 2/3',PHASE_3:'Phase 3',UNKNOWN:'Stage unknown',NO_STAGE_REPORTED:'No stage reported'};return m[s]||s.replaceAll('_',' ')}

const shortVariant={
 'missense variant':'Missense','inframe deletion':'Inframe del.','frameshift variant':'Frameshift','intron variant':'Intron',
 'regulatory region variant':'Regulatory','intergenic variant':'Intergenic','splice region variant':'Splice region',
 'splice donor variant':'Splice donor','non coding transcript exon variant':'NC exon',"3-prime UTR variant":"3′ UTR",
 "5-prime UTR variant":"5′ UTR",'stop gained':'Stop gained','synonymous variant':'Synonymous',
 'TF binding site variant':'TF binding','splice acceptor variant':'Splice acceptor','downstream gene variant':'Downstream',
 'stop lost':'Stop lost','upstream gene variant':'Upstream','inframe insertion':'Inframe ins.',
 'protein altering variant':'Protein altering','Multiple reported':'Multiple'
};
const shortAnatomy={'Lacrimal Apparatus Diseases':'Lacrimal','Ocular Motility Disorders':'Motility','Conjunctival Diseases':'Conjunctival','Ocular Hypertension':'Ocular HTN','Eye Neoplasms':'Neoplasms','Refractive Errors':'Refractive','Retinal Diseases':'Retinal','Corneal Diseases':'Corneal','Orbital Diseases':'Orbital','Uveal Diseases':'Uveal','Lens Diseases':'Lens'};
const shortInheritance={'Autosomal dominant':'AD','Autosomal recessive':'AR','Mitochondrial':'Mitochondrial','X-linked dominant':'XLD','X-linked recessive':'XLR','Other':'Other'};

function displayLabel(name,map){
 if(map.id.includes('variant')&&shortVariant[name])return shortVariant[name];
 if(map.left_label==='Anatomy category'&&shortAnatomy[name])return shortAnatomy[name];
 if(map.left_label==='Inheritance category'&&shortInheritance[name])return shortInheritance[name];
 if(map.right_label==='Drug stage')return stageLabel(name);
 return name;
}

function relationshipOption(map){
 const totals={};
 map.left_nodes.forEach(n=>totals[`L:${n}`]=0);
 map.right_nodes.forEach(n=>totals[`R:${n}`]=0);
 map.links.forEach(x=>{const v=Number(x.association_count||0);totals[`L:${x.left_name}`]=(totals[`L:${x.left_name}`]||0)+v;totals[`R:${x.right_name}`]=(totals[`R:${x.right_name}`]||0)+v});
 const max=Math.max(1,...Object.values(totals)),minNode=isMobile()?7:9,maxNode=isMobile()?20:28;
 const left=map.left_nodes.map(n=>({name:`L:${n}`,full:n,display:displayLabel(n,map),category:0,value:totals[`L:${n}`]||0,symbolSize:minNode+(maxNode-minNode)*Math.sqrt((totals[`L:${n}`]||0)/max)}));
 const right=map.right_nodes.map(n=>({name:`R:${n}`,full:n,display:displayLabel(n,map),category:1,value:totals[`R:${n}`]||0,symbolSize:minNode+(maxNode-minNode)*Math.sqrt((totals[`R:${n}`]||0)/max)}));
 const links=map.links.map(x=>{const v=Number(x.association_count||0);return {source:`L:${x.left_name}`,target:`R:${x.right_name}`,value:v,left_full:x.left_name,right_full:x.right_name,lineStyle:{width:Math.min(isMobile()?4.5:6,.55+Math.log10(v+1)*(isMobile()?1.15:1.55)),opacity:isMobile()?.17:.25,curveness:.14}}});
 const labelSize=map.id.includes('variant')?(isNarrow()?7:isMobile()?8:9):(isNarrow()?8:isMobile()?9:10);
 return {animationDurationUpdate:280,aria:{enabled:true},
  tooltip:{confine:true,formatter:p=>p.dataType==='edge'?`${esc(p.data.left_full)} ↔ ${esc(p.data.right_full)}<br><strong>${fmt(p.data.value)}</strong> ${esc(map.metric_label)}`:`${esc(p.data.full)}<br><strong>${fmt(p.data.value)}</strong> connected ${esc(map.metric_label)}`},
  series:[{type:'graph',layout:'circular',circular:{rotateLabel:true},roam:true,
   categories:[{name:map.left_label,itemStyle:{color:'#6d5ce7'}},{name:map.right_label,itemStyle:{color:'#78c45d'}}],
   data:[...left,...right],links,lineStyle:{color:'source',opacity:.25},
   label:{show:true,position:'right',fontSize:labelSize,color:'#334155',formatter:p=>p.data.display},
   labelLayout:{hideOverlap:false},emphasis:{focus:'adjacency',lineStyle:{opacity:.8}},edgeSymbol:['none','none']}]};
}

let payload=null,relationshipIndex=0,touchStartX=null,touchStartY=null;
function relationshipMap(){return payload?.relationship_maps?.[relationshipIndex]||null}
function renderRelationship(direction=''){
 const map=relationshipMap();if(!map)return;
 document.getElementById('relationshipCounter').textContent=`Map ${relationshipIndex+1} of ${payload.relationship_maps.length}`;
 document.getElementById('relationshipTitle').textContent=map.title;
 document.getElementById('relationshipDescription').textContent=map.description;
 document.getElementById('relationshipSelect').value=map.id;
 document.getElementById('relationshipLegend').innerHTML=`<span><i class="legend-dot left-side"></i>${esc(map.left_label)}</span><span><i class="legend-dot right-side"></i>${esc(map.right_label)}</span><span class="text-secondary">Edge metric: ${esc(map.metric_label)}</span>`;
 document.getElementById('relationshipMobileHint').classList.toggle('d-none',!map.id.includes('variant'));
 const wrap=document.querySelector('.relationship-canvas-wrap');wrap.classList.remove('slide-left','slide-right');void wrap.offsetWidth;if(direction)wrap.classList.add(direction==='next'?'slide-left':'slide-right');
 const c=chart('relationshipRing');c.clear();c.setOption(relationshipOption(map),true);setTimeout(()=>c.resize(),20);
 document.querySelectorAll('.relationship-dot').forEach((b,i)=>b.classList.toggle('active',i===relationshipIndex));
}
function setRelationshipIndex(index,direction=''){const n=payload.relationship_maps.length;relationshipIndex=(index+n)%n;renderRelationship(direction)}
function bindRelationshipControls(){
 const select=document.getElementById('relationshipSelect');
 select.innerHTML=payload.relationship_maps.map((m,i)=>`<option value="${esc(m.id)}">${i+1}. ${esc(m.title)}</option>`).join('');
 const dots=document.getElementById('relationshipDots');
 dots.innerHTML=payload.relationship_maps.map((m,i)=>`<button type="button" class="relationship-dot ${i===0?'active':''}" data-map-index="${i}" aria-label="Show ${esc(m.title)}"></button>`).join('');
 document.getElementById('relationshipPrev').onclick=()=>setRelationshipIndex(relationshipIndex-1,'prev');
 document.getElementById('relationshipNext').onclick=()=>setRelationshipIndex(relationshipIndex+1,'next');
 select.onchange=()=>{const i=payload.relationship_maps.findIndex(m=>m.id===select.value);if(i>=0)setRelationshipIndex(i,i>relationshipIndex?'next':'prev')};
 dots.querySelectorAll('[data-map-index]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.mapIndex);setRelationshipIndex(i,i>relationshipIndex?'next':'prev')});
 document.getElementById('relationshipReset').onclick=()=>{const c=chart('relationshipRing');c.clear();c.setOption(relationshipOption(relationshipMap()),true)};
 const vp=document.getElementById('relationshipViewport');
 vp.addEventListener('touchstart',e=>{const t=e.changedTouches[0];touchStartX=t.clientX;touchStartY=t.clientY},{passive:true});
 vp.addEventListener('touchend',e=>{if(touchStartX===null)return;const t=e.changedTouches[0],dx=t.clientX-touchStartX,dy=t.clientY-touchStartY;touchStartX=touchStartY=null;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.25){dx<0?setRelationshipIndex(relationshipIndex+1,'next'):setRelationshipIndex(relationshipIndex-1,'prev')}},{passive:true});
 vp.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){e.preventDefault();setRelationshipIndex(relationshipIndex-1,'prev')}if(e.key==='ArrowRight'){e.preventDefault();setRelationshipIndex(relationshipIndex+1,'next')}});
}

function render(){
 if(!payload)return;const d=payload,o=d.overview;
 document.getElementById('overviewGrid').innerHTML=[['Diseases',o.diseases],['Genes',o.genes],['Disease–gene associations',o.disease_genes],['Variants',o.variants],['Disease–variant associations',o.disease_variants],['Drugs',o.drugs],['Drug–target associations',o.drug_targets],['Direct disease–drug associations',o.disease_drugs],['Clinical trials',o.trials],['Clinical reports',o.clinical_reports]].map(x=>overviewCard(x[0],x[1])).join('');
 document.getElementById('anatomySummaryText').textContent=`${fmt(o.diseases)} canonical diseases grouped by ocular localization.`;
 chart('anatomyDonut').setOption(pieOption(d.disease.anatomy,'category_name','disease_count','{total}\nDiseases',o.diseases),true);
 chart('inheritanceDonut').setOption(pieOption(d.disease.inheritance,'category_name','disease_count','{total}\nMemberships'),true);
 const cov=[{name:'Classified',value:Number(d.disease.inheritance_classified)},{name:'Not classified',value:Number(d.disease.inheritance_unclassified)}];
 chart('inheritanceCoverageDonut').setOption({aria:{enabled:true},tooltip:{trigger:'item'},series:[{type:'pie',radius:['52%','76%'],center:['50%','50%'],label:{show:false},itemStyle:{borderColor:'#fff',borderWidth:2},data:cov}]},true);
 document.getElementById('inheritanceCoverageText').innerHTML=`<div class="coverage-number">${fmt(d.disease.inheritance_classified)} / ${fmt(o.diseases)}</div><div class="coverage-label">canonical diseases have at least one directly supported inheritance classification.</div>`;
 chart('geneTreemap').setOption(treemapOption(d.genetics.gene_categories,'category_name','entity_count'),true);
 chart('variantTreemap').setOption(treemapOption(d.genetics.variant_consequences,'consequence_term','variant_count'),true);
 document.getElementById('variantCoverageText').textContent=`${fmt(d.genetics.variants_with_consequence)} canonical variants with mapped consequence annotations · ${d.genetics.populated_consequence_categories} categories represented`;
 const stages=d.therapeutics.drug_stages.map(x=>({stage_label:stageLabel(x.stage),drug_count:Number(x.drug_count)}));
 chart('drugStageDonut').setOption(pieOption(stages,'stage_label','drug_count','{total}\nDrugs'),true);
 chart('therapeuticSankey').setOption(sankeyOption(d.therapeutics),true);
 chart('trialEvidenceOrbit').setOption(evidenceOrbitOption('trial',d.clinical.trials,d.clinical.disease_trial,d.clinical.drug_trial),true);
 document.getElementById('trialEvidenceMetrics').innerHTML=evidenceMetrics(d.clinical.trials,d.clinical.disease_trial,d.clinical.drug_trial);
 chart('reportEvidenceOrbit').setOption(evidenceOrbitOption('report',d.clinical.reports,d.clinical.disease_report,d.clinical.drug_report),true);
 document.getElementById('reportEvidenceMetrics').innerHTML=evidenceMetrics(d.clinical.reports,d.clinical.disease_report,d.clinical.drug_report);
 renderRelationship();
}

let resizeTimer=null;
window.addEventListener('resize',()=>{
 clearTimeout(resizeTimer);
 resizeTimer=setTimeout(()=>{
  Object.values(charts).forEach(c=>c.resize());
 },180);
});
document.addEventListener('DOMContentLoaded',async()=>{try{payload=await getStats();bindRelationshipControls();render()}catch(e){document.getElementById('overviewGrid').innerHTML=`<div class="alert alert-danger">Could not load ODDB statistics: ${esc(e.message)}</div>`}});
