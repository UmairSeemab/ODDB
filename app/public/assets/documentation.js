(() => {
'use strict';

const el=document.getElementById('oddbModelChart');
if(!el || typeof echarts==='undefined') return;

const chart=echarts.init(el);
let activeFilter='all';
let selectedEntity=null;

const ENTITY_INFO={
 Disease:{
  count:'185 canonical diseases',
  description:'Central disease layer connecting genetics, variants, direct therapeutic evidence and clinical evidence.',
  identifiers:'Canonical ODDB disease ID; source names, aliases and history retained.',
  relations:[
   ['Disease–Gene','1,662 associations'],
   ['Disease–Variant','106,838 associations'],
   ['Disease–Locus','2 associations'],
   ['Disease–Drug','424 evidence associations'],
   ['Disease–Clinical Trial','1,342 links'],
   ['Disease–Clinical Report','1,370 links']
  ]
 },
 Gene:{
  count:'1,249 genes',
  description:'HGNC-aligned gene layer. Structural/regulatory loci are deliberately excluded from the gene entity set.',
  identifiers:'HGNC identifier anchors canonical gene identity.',
  relations:[
   ['Disease–Gene','1,662 associations'],
   ['Gene–Variant','707,315 associations'],
   ['Drug–Target','1,009 associations']
  ]
 },
 Variant:{
  count:'707,315 variants',
  description:'Canonical variant layer connected to genes and to diseases only where explicit disease–variant evidence is available.',
  identifiers:'Source variant identifiers with external links where available.',
  relations:[
   ['Gene–Variant','707,315 associations'],
   ['Disease–Variant','106,838 associations']
  ]
 },
 Locus:{
  count:'2 structural loci',
  description:'Non-gene genetic entities kept separate so HGNC gene analyses are not contaminated by locus/phenotype/regulatory labels.',
  identifiers:'Canonical locus identity preserved outside the gene table.',
  relations:[['Disease–Locus','2 associations']]
 },
 Drug:{
  count:'893 canonical drugs',
  description:'Therapeutic entity layer with explicit drug-form relationships and separate direct disease and molecular target evidence.',
  identifiers:'Canonical drug plus preserved source drug IDs/names; ChEMBL enrichment where validated.',
  relations:[
   ['Disease–Drug','424 evidence associations'],
   ['Drug–Target','1,009 associations'],
   ['Drug Form','99 relationships'],
   ['Drug–Clinical Trial','1,566 links'],
   ['Drug–Clinical Report','1,575 links']
  ]
 },
 'Clinical Trial':{
  count:'1,255 trials',
  description:'Trial entities linked independently to diseases and drugs, preventing unsupported disease×drug cross-products.',
  identifiers:'Source clinical-trial identifiers retained at the trial entity level.',
  relations:[
   ['Disease–Clinical Trial','1,342 links'],
   ['Drug–Clinical Trial','1,566 links']
  ]
 },
 'Clinical Report':{
  count:'1,382 reports',
  description:'Clinical report entities modeled independently from trials and linked to diseases/drugs through many-to-many tables.',
  identifiers:'Source report identifier and source mappings remain traceable.',
  relations:[
   ['Disease–Clinical Report','1,370 links'],
   ['Drug–Clinical Report','1,575 links']
  ]
 }
};

const nodes=[
 {name:'Disease',x:100,y:245,symbolSize:76,category:0,layer:['genetics','therapeutics','clinical']},
 {name:'Gene',x:370,y:120,symbolSize:70,category:1,layer:['genetics','therapeutics']},
 {name:'Variant',x:675,y:75,symbolSize:66,category:2,layer:['genetics']},
 {name:'Locus',x:370,y:315,symbolSize:58,category:3,layer:['genetics']},
 {name:'Drug',x:690,y:290,symbolSize:72,category:4,layer:['therapeutics','clinical']},
 {name:'Clinical Trial',x:410,y:500,symbolSize:74,category:5,layer:['clinical']},
 {name:'Clinical Report',x:115,y:500,symbolSize:76,category:6,layer:['clinical']}
];

const links=[
 {source:'Disease',target:'Gene',name:'Disease–Gene',layer:['genetics']},
 {source:'Gene',target:'Variant',name:'Gene–Variant',layer:['genetics']},
 {source:'Disease',target:'Variant',name:'Disease–Variant',layer:['genetics'],curve:.22},
 {source:'Disease',target:'Locus',name:'Disease–Locus',layer:['genetics']},
 {source:'Disease',target:'Drug',name:'Direct Disease–Drug',layer:['therapeutics'],curve:.12},
 {source:'Drug',target:'Gene',name:'Drug–Target',layer:['therapeutics'],curve:-.12},
 {source:'Disease',target:'Clinical Trial',name:'Disease–Trial',layer:['clinical']},
 {source:'Drug',target:'Clinical Trial',name:'Drug–Trial',layer:['clinical']},
 {source:'Disease',target:'Clinical Report',name:'Disease–Report',layer:['clinical']},
 {source:'Drug',target:'Clinical Report',name:'Drug–Report',layer:['clinical'],curve:.14}
];

function selectedData(){
 const visibleNodes=activeFilter==='all'
  ? nodes
  : nodes.filter(n=>n.layer.includes(activeFilter));
 const names=new Set(visibleNodes.map(n=>n.name));
 const visibleLinks=links.filter(l=>
  names.has(l.source) && names.has(l.target) &&
  (activeFilter==='all' || l.layer.includes(activeFilter))
 );
 return {visibleNodes,visibleLinks};
}

function option(){
 const {visibleNodes,visibleLinks}=selectedData();
 const selected=selectedEntity;

 return {
  animationDuration:350,
  tooltip:{
   confine:true,
   formatter:p=>{
    if(p.dataType==='node'){
     const info=ENTITY_INFO[p.name];
     return `<strong>${p.name}</strong><br>${info?.count||''}<br><span style="color:#64748b">${info?.description||''}</span>`;
    }
    if(p.dataType==='edge') return `<strong>${p.data.name}</strong>`;
    return '';
   }
  },
  legend:[{
   show:true,
   bottom:8,
   left:'center',
   itemWidth:10,
   itemHeight:10,
   textStyle:{fontSize:10,color:'#64748b'},
   data:['Disease','Gene','Variant','Locus','Drug','Clinical Trial','Clinical Report']
  }],
  series:[{
   type:'graph',
   layout:'none',
   roam:true,
   zoom:1,
   scaleLimit:{min:.55,max:2.2},
   draggable:false,
   data:visibleNodes.map(n=>({
    ...n,
    itemStyle:{
     opacity:!selected || n.name===selected ||
      visibleLinks.some(l=>(l.source===selected&&l.target===n.name)||(l.target===selected&&l.source===n.name))
      ?1:.22
    },
    label:{show:true,color:'#172033',fontSize:11,fontWeight:700}
   })),
   links:visibleLinks.map(l=>({
    ...l,
    lineStyle:{
     width:1.7,
     opacity:!selected || l.source===selected || l.target===selected ? .72:.10,
     curveness:l.curve||0
    },
    label:{
     show:true,
     formatter:l.name,
     fontSize:9,
     color:'#64748b',
     backgroundColor:'rgba(255,255,255,.82)',
     padding:[2,3],
     borderRadius:3
    }
   })),
   categories:[
    {name:'Disease',itemStyle:{color:'#2563eb'}},
    {name:'Gene',itemStyle:{color:'#0ea5e9'}},
    {name:'Variant',itemStyle:{color:'#8b5cf6'}},
    {name:'Locus',itemStyle:{color:'#a855f7'}},
    {name:'Drug',itemStyle:{color:'#10b981'}},
    {name:'Clinical Trial',itemStyle:{color:'#f59e0b'}},
    {name:'Clinical Report',itemStyle:{color:'#ec4899'}}
   ],
   emphasis:{focus:'adjacency',lineStyle:{width:3,opacity:1}},
   edgeSymbol:['none','arrow'],
   edgeSymbolSize:[0,7],
   lineStyle:{color:'source'}
  }]
 };
}

function render(){
 chart.setOption(option(),true);
}

function renderDetail(name){
 const box=document.getElementById('modelDetail');
 const info=ENTITY_INFO[name];
 if(!info){
  box.innerHTML=`
   <div class="model-detail-eyebrow">Select an entity</div>
   <h3 class="h5">ODDB v1 relational model</h3>
   <p>Click or tap a node to inspect its role and the relationships that connect it to other ODDB entities.</p>
   <div class="model-detail-note">The relationship table below provides a complete text-accessible description of the same model.</div>`;
  return;
 }

 box.innerHTML=`
  <div class="model-detail-eyebrow">Entity detail</div>
  <h3 class="h5">${name}</h3>
  <div class="fw-bold text-primary small mb-2">${info.count}</div>
  <p>${info.description}</p>
  <p><strong class="text-dark">Identity:</strong> ${info.identifiers}</p>
  <div class="model-rel-list">
   ${info.relations.map(([rel,count])=>`
    <div class="model-rel-item"><strong>${rel}</strong><span>${count}</span></div>`).join('')}
  </div>
  <div class="model-detail-note">Click the selected node again or use Reset view to restore the complete model.</div>`;
}

chart.on('click',params=>{
 if(params.dataType!=='node') return;
 selectedEntity=selectedEntity===params.name?null:params.name;
 renderDetail(selectedEntity);
 render();
});

document.querySelectorAll('[data-model-filter]').forEach(btn=>{
 btn.addEventListener('click',()=>{
  activeFilter=btn.dataset.modelFilter;
  selectedEntity=null;
  document.querySelectorAll('[data-model-filter]').forEach(b=>b.classList.toggle('active',b===btn));
  renderDetail(null);
  render();
 });
});

document.getElementById('resetModel').addEventListener('click',()=>{
 activeFilter='all';
 selectedEntity=null;
 document.querySelectorAll('[data-model-filter]').forEach(b=>b.classList.toggle('active',b.dataset.modelFilter==='all'));
 renderDetail(null);
 render();
 chart.dispatchAction({type:'restore'});
});

let resizeTimer=null;
window.addEventListener('resize',()=>{
 clearTimeout(resizeTimer);
 resizeTimer=setTimeout(()=>chart.resize(),140);
});

const sections=[...document.querySelectorAll('.doc-section[id]')];
const tocLinks=[...document.querySelectorAll('.toc-card a[href^="#"]')];

if('IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>{
  const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
  if(!visible) return;
  const id=visible.target.id;
  tocLinks.forEach(a=>a.classList.toggle('active',a.getAttribute('href')===`#${id}`));
 },{rootMargin:'-18% 0px -62% 0px',threshold:[0,.15,.5]});
 sections.forEach(s=>observer.observe(s));
}

render();
})();
