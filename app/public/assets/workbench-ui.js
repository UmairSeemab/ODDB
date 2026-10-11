/* ODDB v1 simplified Graph Workbench v0.7.5. Presentation only. */
(() => {
 'use strict';
 function initWorkbenchUI() {
  const card=document.querySelector('.wb-simplified');
  if(!card)return;
  const buttons=[...card.querySelectorAll('[data-wb-panel]')];
  const panels=[...card.querySelectorAll('.wb-panel')];
  let active=null;
  function resizeGraph() {
   requestAnimationFrame(()=>{if(typeof cy!=='undefined'&&cy&&typeof cy.resize==='function')cy.resize();});
  }
  function setPanel(id) {
   active=id||null;
   buttons.forEach(button=>button.setAttribute('aria-expanded',String(button.dataset.wbPanel===active)));
   panels.forEach(panel=>{panel.hidden=panel.id!==active;});
   resizeGraph();
  }
  function closePanel() {
   const previous=active;
   setPanel(null);
   const opener=buttons.find(b=>b.dataset.wbPanel===previous);
   if(opener)opener.focus();
  }
  buttons.forEach(button=>button.addEventListener('click',()=>setPanel(active===button.dataset.wbPanel?null:button.dataset.wbPanel)));
  card.querySelectorAll('[data-wb-close]').forEach(button=>button.addEventListener('click',closePanel));
  card.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&active&&panels.some(panel=>!panel.hidden&&panel.contains(event.target))){event.preventDefault();closePanel();}
  });
  const pins=document.getElementById('pinnedEntityChips');
  const pinBar=pins?.closest('.pinned-workbench-bar');
  const layerStatus=document.getElementById('hiddenLayerCount');
  const selected=document.getElementById('selectedDiseaseSummary');
  const comparisonBadge=document.getElementById('wbComparisonBadge');
  const pathBadge=document.getElementById('wbPathBadge');
  const comparisonResults=document.getElementById('comparisonResults');
  const pathResults=document.getElementById('pathFinderResults');
  function syncStatus() {
   if(pinBar)pinBar.hidden=!pins.querySelector('[data-pinned-select]');
   if(layerStatus)layerStatus.hidden=!layerStatus.textContent.trim()||layerStatus.textContent.trim()==='All layers visible';
   const count=Number((selected?.textContent||'').match(/^\s*(\d+)/)?.[1]||0);
   const hasComparison=!!comparisonResults&&!comparisonResults.classList.contains('d-none')&&!!comparisonResults.textContent.trim();
   if(comparisonBadge){comparisonBadge.hidden=!count&&!hasComparison;comparisonBadge.textContent=hasComparison?'Results':`${count} selected`;}
   const hasPaths=!!pathResults&&!pathResults.classList.contains('d-none')&&!!pathResults.textContent.trim();
   if(pathBadge){pathBadge.hidden=!hasPaths;pathBadge.textContent='Results';}
  }
  const observer=new MutationObserver(syncStatus);
  [pins,layerStatus,selected,comparisonResults,pathResults].filter(Boolean).forEach(el=>observer.observe(el,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['class']}));
  const graph=document.getElementById('cy');
  if(graph&&typeof ResizeObserver!=='undefined')new ResizeObserver(resizeGraph).observe(graph);
  syncStatus();
  setPanel(null);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initWorkbenchUI);
 else initWorkbenchUI();
})();
