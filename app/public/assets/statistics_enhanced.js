/* ODDB v1 precomputed scientific charts and bounded on-demand network.
   Existing ECharts, site navigation, statistics.js and export tools remain intact. */
(() => {
  'use strict';
  const ROOT = 'assets/statistics_data/';
  const ech = window.echarts;
  const $ = id => document.getElementById(id);
  const number = n => Number(n || 0).toLocaleString();
  const html = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const titles = {
    diseases_genes: ['Disease–gene associations by chromosome','Distinct associated HGNC genes per disease. Chromosome labels come from canonical gene records or an HGNC-approved annotation overlay. Unmatched genes remain Unmapped.'],
    diseases_variants: ['Disease–variant associations by chromosome','Distinct canonical variants per disease, stacked by reported chromosome.'],
    genes_diseases: ['Genes associated with the most diseases','Distinct disease associations per HGNC gene; each gene counted once per disease.'],
    diseases_trial_drugs: ['Diseases with drugs linked through trials','Unique drugs co-occurring with diseases in shared clinical trial records; each pair assigned to its highest observed phase. Not treatment claims.'],
    drugs_trial_diseases: ['Drugs with diseases linked through trials','Unique diseases co-occurring with each drug through shared trials; each pair assigned to its highest observed phase.'],
    genes_by_chromosome_category: ['Genes across chromosomes by disease category','Distinct associated genes in each anatomy category per chromosome. A gene can occur in multiple categories.'],
    variants_by_chromosome_category: ['Variants across chromosomes by disease category','Distinct disease-associated variants per chromosome and anatomy category.'],
    genes_by_category_chromosome: ['Associated genes per ocular disease category','Within-category distinct associated genes by chromosome. Membership categories can overlap.'],
    variants_by_category_chromosome: ['Associated variants per ocular disease category','Within-category distinct variants by chromosome. Membership categories can overlap.'],
    trial_phases: ['Clinical trial phase distribution','Unique NCT clinical trial records grouped by their source-reported phase; missing and literal unknown are distinct.'],
    disease_categories: ['Ocular disease distribution','Distinct diseases in each of the 12 anatomical localization categories; memberships can overlap.'],
    evidence_classes: ['Direct evidence versus target-overlap discovery','Unique disease–drug pairs. Target-overlap-only pairs are hypotheses, not treatments.']
  };
  const rankedIds = ['diseases_genes','diseases_variants','genes_diseases','diseases_trial_drugs','drugs_trial_diseases'];
  const genomeIds = ['genes_by_chromosome_category','variants_by_chromosome_category','genes_by_category_chromosome','variants_by_category_chromosome'];
  const clinicalIds = ['trial_phases','disease_categories','evidence_classes'];
  const configs = new Map();
  const instances = new Map();
  const palette = ['#327bb8','#17a8a2','#f0aa4b','#9456b6','#70ad4f','#e3756d','#4f80cf','#bc699a','#8ca03d','#e9c24f','#5096a5','#c7824e','#586988','#ad83ca','#75c1ba','#c87676','#699c61','#b4a34b','#6684be','#db92ba','#5a827e','#998678','#6480a5','#a5bd6f','#7c8791','#b6b9bd'];
  const phases = ['EARLY_PHASE1','PHASE1','PHASE2','PHASE3','PHASE4','PHASE 1','PHASE 2','PHASE 3','PHASE 4','PHASE_1','PHASE_2','PHASE_3','PHASE_4','NO_PHASE_REPORTED','UNKNOWN'];
  const chromosomeNumber = chr => {
    const s = String(chr).replace(/^chr/i,'').toUpperCase();
    const n = Number(s);
    if (Number.isInteger(n) && n >= 1 && n <= 22) return n;
    return ({X:23,Y:24,M:25,MT:25,UNMAPPED:26})[s] ?? 99;
  };
  const chromosomePart = part => /^\s*(chr)?([0-9]{1,2}|X|Y|MT|M)\s*$/i.test(part) || part === 'Unmapped';
  function keys(rows) {
    const all = [...new Set(rows.flatMap(r => Object.keys(r.parts || {})))];
    if (all.length && all.every(chromosomePart)) return all.sort((a,b) => chromosomeNumber(a) - chromosomeNumber(b));
    if (all.some(x => String(x).toUpperCase().includes('PHASE'))) {
      return all.sort((a,b) => {
        const ia=phases.indexOf(a.toUpperCase()),ib=phases.indexOf(b.toUpperCase());
        return (ia===-1?95:ia)-(ib===-1?95:ib) || a.localeCompare(b);
      });
    }
    return all.sort((a,b) => a.localeCompare(b));
  }
  function colorFor(part, index) {
    if (chromosomePart(part)) return palette[Math.max(0, chromosomeNumber(part)-1)%palette.length];
    if (part === 'Count' || part === 'Diseases') return palette[0];
    const ix=phases.indexOf(String(part).toUpperCase());
    if (ix>=0) return palette[ix%palette.length];
    // Stable, dataset-independent category color.
    let hash=0;for(const ch of String(part))hash=((hash*31)+ch.charCodeAt(0))>>>0;
    return palette[hash%palette.length];
  }
  function createCard(id, container, ranked) {
    const [title,description] = titles[id];
    const article = document.createElement('article');
    article.className = 'viz-card';
    article.dataset.scientificChart = id;
    article.innerHTML = `
      <div class="viz-head"><div><h3 class="h5 mb-1">${html(title)}</h3><p class="oddb-enhanced-description mb-0">${html(description)}</p></div></div>
      ${ranked ? `<div class="oddb-enhanced-toolbar">
        <label>Show <select class="form-select form-select-sm" data-action="limit"><option value="20">Top 20</option><option value="30">Top 30</option><option value="40">Top 40</option><option value="custom">Custom</option><option value="all">All</option></select></label>
        <label class="d-none" data-custom-wrap>Custom number <input class="form-control form-control-sm oddb-custom-limit" data-action="custom" type="number" min="1" value="50" step="1"></label>
        <label>Sort <select class="form-select form-select-sm" data-action="sort"><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label>
        <label>Search <input data-action="search" type="search" class="form-control form-control-sm oddb-chart-search" placeholder="Search names"></label>
      </div>` : ''}
      <div class="oddb-enhanced-summary" aria-live="polite"></div>
      <div class="oddb-enhanced-scroll" style="max-height:720px;overflow:auto"><div class="oddb-enhanced-plot" role="img" aria-label="${html(title)} chart"></div></div>
      <div class="oddb-enhanced-actions"><button class="btn btn-sm btn-outline-secondary" data-export="png" type="button">PNG</button><button class="btn btn-sm btn-outline-secondary" data-export="svg" type="button">SVG</button><button class="btn btn-sm btn-outline-secondary" data-export="csv" type="button">CSV</button></div>`;
    $(container).appendChild(article);
    const config = {id, article, ranked, rows:[], allRows:[], visible:[], dataKeys:[]};
    configs.set(id, config);
    article.addEventListener('change', event => {
      if (!event.target.matches('[data-action]')) return;
      config.update();
    });
    article.addEventListener('input', event => {
      if (!event.target.matches('[data-action="search"],[data-action="custom"]')) return;
      config.update();
    });
    article.addEventListener('click', event => {
      const button = event.target.closest('[data-export]');
      if (button) exportChart(config,button.dataset.export);
    });
    return config;
  }
  function fromSimple(rows,key,value) {
    return rows.map((r,i) => ({id:String(r.id ?? r[key] ?? i),name:String(r[key]),total:Number(r[value]),parts:{Count:Number(r[value])}}));
  }
  function axisOption(config) {
    const rows = config.visible;
    const isRanked = config.ranked;
    const selectedKeys = config.dataKeys;
    // For ranked charts, chart height grows with visible items (scrolling handles large N).
    const height = Math.max(300, Math.min(18000, 85 + rows.length * (isRanked ? 27 : 33)));
    const plot = config.article.querySelector('.oddb-enhanced-plot');
    plot.style.height = `${height}px`;
    let graph = instances.get(config.id);
    if (!graph) { graph=ech.init(plot,null,{renderer:'canvas'});instances.set(config.id,graph); }
    const colors=new Map(selectedKeys.map((s,i)=>[s,colorFor(s,i)]));
    const maxTotal = Math.max(1,...rows.map(x=>Number(x.total)||0));
    const option = {
      animationDuration:180,aria:{enabled:true},
      color:selectedKeys.map(k=>colors.get(k)),
      tooltip:{trigger:'axis',confine:true,axisPointer:{type:'shadow'},formatter: params => {
        if (!params?.length) return '';
        const row=rows[params[0].dataIndex];
        if (!row) return '';
        const parts = selectedKeys.filter(k=>Number(row.parts[k]||0)>0).map(k=>`${html(k)}: ${number(row.parts[k])}`);
        return `<strong>${html(row.name)}</strong><br>Total: ${number(row.total)}<br>${parts.join('<br>')}`;
      }},
      legend:{type:'scroll',top:0,left:10,right:10,textStyle:{fontSize:10}},
      grid:{left:isRanked?12:14,right:65,top:selectedKeys.length>1?53:32,bottom:10,containLabel:true},
      xAxis:{type:'value',min:0,max:Math.max(1,Math.ceil(maxTotal*1.09)),axisLabel:{fontSize:10},splitLine:{lineStyle:{color:'#eef1f6'}}},
      yAxis:{type:'category',inverse:true,data:rows.map(r=>r.name),axisLabel:{width:Math.min(window.innerWidth < 600 ? 130 : 245,245),overflow:'truncate',fontSize:11},axisTick:{show:false}},
      series:selectedKeys.map(k => ({name:k,type:'bar',stack:'total',barMaxWidth:23,itemStyle:{color:colors.get(k)},emphasis:{focus:'series'},data:rows.map(r=>Number(r.parts[k]||0))}))
    };
    graph.clear(); graph.setOption(option,true); graph.resize();
  }
  function render(config) {
    const $a = action => config.article.querySelector(`[data-action="${action}"]`);
    const search = config.ranked ? ($a('search').value.trim().toLowerCase()) : '';
    const sort = config.ranked ? $a('sort').value : 'desc';
    let rows = config.allRows.filter(r => r.name.toLowerCase().includes(search));
    rows = [...rows].sort((a,b) => (sort==='asc'?a.total-b.total:b.total-a.total) || a.name.localeCompare(b.name));
    let limit=rows.length;
    if (config.ranked) {
      const selected=$a('limit').value;
      const wrap=config.article.querySelector('[data-custom-wrap]');
      wrap.classList.toggle('d-none',selected!=='custom');
      if (selected === 'custom') {
        limit=Math.max(1,Math.min(rows.length,Math.floor(Number($a('custom').value)||1)));
        $a('custom').max=String(config.allRows.length);
      } else if (selected !== 'all') limit=Number(selected);
    }
    config.visible=rows.slice(0,Math.max(0,limit));
    config.dataKeys=keys(config.allRows);
    config.article.querySelector('.oddb-enhanced-summary').textContent =
      `Showing ${number(config.visible.length)} of ${number(config.allRows.length)} records${search?' matching the search':''}. Values are computed from the ODDB v1 release snapshot.`;
    axisOption(config);
  }
  function download(name,blob){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);}
  function csvValue(v) {
    let s=String(v??'');
    if (/^[\s]*[=+\-@]/.test(s)) s="'"+s;
    return `"${s.replaceAll('"','""')}"`;
  }
  function csvFile(name,columns,rows) {
    const content=[columns.map(csvValue).join(','),...rows.map(r=>r.map(csvValue).join(','))].join('\r\n')+'\r\n';
    download(name,new Blob(['\ufeff',content],{type:'text/csv;charset=utf-8'}));
  }
  function exportChart(config,type) {
    const graph=instances.get(config.id);
    if (!graph) return;
    const id=`oddb-v1-${config.id}`;
    if (type==='csv') {
      const columns=['Entity ID','Entity name','Total',...config.dataKeys];
      const rows=config.visible.map(r=>[r.id,r.name,r.total,...config.dataKeys.map(k=>r.parts[k]||0)]);
      csvFile(id+'.csv',columns,rows);
      return;
    }
    if (type==='png') {
      const a=document.createElement('a');a.href=graph.getDataURL({type:'png',pixelRatio:2,backgroundColor:'#ffffff'});
      a.download=id+'.png';document.body.append(a);a.click();a.remove();return;
    }
    // SVG requires an SVG renderer. Build it temporarily from the current ECharts option.
    const hidden=document.createElement('div');hidden.style.cssText=`position:fixed;left:-100000px;top:0;width:${Math.max(900,graph.getWidth())}px;height:${Math.max(400,graph.getHeight())}px;`;
    document.body.append(hidden);
    let svg;
    try {
      svg=ech.init(hidden,null,{renderer:'svg'});
      const opt=graph.getOption(); opt.animation=false;
      svg.setOption(opt,true);
      const encoded=svg.getDataURL({type:'svg',backgroundColor:'#ffffff'});
      const a=document.createElement('a');a.href=encoded;a.download=id+'.svg';document.body.append(a);a.click();a.remove();
    } finally {if(svg)svg.dispose();hidden.remove();}
  }
  // Separate fixed-layout SVG exporter: every name remains readable even for
  // 80–200 selected nodes. The interactive force graph remains unchanged.
  function publicationNetworkSvg(data) {
    const width = 2400;
    const centerX = width / 2;
    const leftX = 915;
    const rightX = 1485;
    const geneNodes = data.nodes.filter(n => n.type === 'gene').sort((a,b) => a.label.localeCompare(b.label));
    const drugNodes = data.nodes.filter(n => n.type === 'drug').sort((a,b) => a.label.localeCompare(b.label));
    const diseaseNode = data.nodes.find(n => n.type === 'disease');
    const longest = Math.max(geneNodes.length, drugNodes.length, 1);
    const gap = 37;
    const height = Math.max(980, 650 + (longest - 1) * gap);
    const midY = height / 2;
    const positions = new Map();
    positions.set(diseaseNode.id, {x:centerX,y:midY});
    function place(nodes, x) {
      const top = midY - ((nodes.length - 1) * gap) / 2;
      nodes.forEach((node,i) => positions.set(node.id,{x,y:top+i*gap}));
    }
    place(geneNodes,leftX);
    place(drugNodes,rightX);
    const attrs = s => html(s);
    const segments = data.edges.map(e => {
      const a=positions.get(e.source), b=positions.get(e.target);
      if (!a || !b) return '';
      const overlap=e.type==='target_overlap_only';
      const target=e.type==='drug_target';
      const color=overlap?'#dc994b':target?'#7caaa2':'#b8c8d6';
      const dash=overlap?' stroke-dasharray="9 7"':target?' stroke-dasharray="3 7"':'';
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${color}" stroke-width="${target?1.5:2.1}"${dash} opacity="0.72"/>`;
    }).join('');
    const textForNode = (n, pos, left) => {
      const fill=n.type==='gene'?'#22a287':'#e39f37';
      const anchor=left?'end':'start';
      const tx=left?pos.x-22:pos.x+22;
      // SVG text is escaped to prevent node labels altering the document.
      return `<circle cx="${pos.x}" cy="${pos.y}" r="10.5" fill="${fill}" stroke="#fff" stroke-width="2"/>`+
        `<text x="${tx}" y="${pos.y}" text-anchor="${anchor}" dominant-baseline="middle" font-size="17" fill="#283548">${attrs(n.label)}</text>`;
    };
    const geneXml=geneNodes.map(n=>textForNode(n,positions.get(n.id),true)).join('');
    const drugXml=drugNodes.map(n=>textForNode(n,positions.get(n.id),false)).join('');
    const diseaseName=String(data.disease?.name || diseaseNode.label);
    const nodeCount=data.nodes.length, edgeCount=data.edges.length;
    const subtitle=`${nodeCount} nodes · ${edgeCount} edges · All selected node labels included`;
    const footerY=height-55;
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="ODDB disease gene drug network for ${attrs(diseaseName)}">
      <rect width="${width}" height="${height}" fill="#ffffff"/>
      <rect x="44" y="38" width="2312" height="${height-76}" rx="26" fill="none" stroke="#e1e8ef" stroke-width="2"/>
      <text x="92" y="100" font-size="36" font-weight="700" fill="#172033">ODDB v1 · Disease–gene–drug connectivity</text>
      <text x="92" y="143" font-size="23" fill="#53657c">${attrs(diseaseName)} · ${attrs(subtitle)}</text>
      <circle cx="125" cy="195" r="11" fill="#2979bc"/><text x="148" y="203" font-size="21" fill="#344054">Disease</text>
      <circle cx="326" cy="195" r="11" fill="#22a287"/><text x="350" y="203" font-size="21" fill="#344054">Gene</text>
      <circle cx="485" cy="195" r="11" fill="#e39f37"/><text x="508" y="203" font-size="21" fill="#344054">Drug</text>
      <line x1="665" x2="731" y1="195" y2="195" stroke="#dc994b" stroke-dasharray="9 7" stroke-width="3"/>
      <text x="747" y="203" font-size="21" fill="#53657c">Target overlap only (discovery hypothesis)</text>
      <text x="${leftX}" y="265" text-anchor="end" font-size="21" font-weight="700" fill="#148e78">ASSOCIATED GENES (${geneNodes.length})</text>
      <text x="${rightX}" y="265" text-anchor="start" font-size="21" font-weight="700" fill="#b47b28">DRUG ENTITIES (${drugNodes.length})</text>
      ${segments}
      ${geneXml}${drugXml}
      <circle cx="${centerX}" cy="${midY}" r="29" fill="#2979bc" stroke="#ffffff" stroke-width="4"/>
      <rect x="${centerX-220}" y="${midY+42}" width="440" height="40" rx="12" fill="#fff" opacity="0.94"/>
      <text x="${centerX}" y="${midY+70}" text-anchor="middle" font-size="20" font-weight="700" fill="#172033">${attrs(diseaseName)}</text>
      <text x="92" y="${footerY}" font-size="19" fill="#53657c">Solid edges: recorded associations · Dashed edges: discovery-only overlap; not evidence of clinical benefit.</text>
    </svg>`;
    return {svg,width,height};
  }
  function network() {
    const select=$('oddb-network-disease');if(!select || !window.echarts)return;
    let graph=null, data=null, reqNo=0;
    const note=$('oddb-network-note');
    const labelSwitch=$('oddb-network-labels');
    const layoutSwitch=$('oddb-network-organized');
    window.ODDBStatsNetworkSnapshot = () => data;
    const colors={disease:'#2979bc',gene:'#22a287',drug:'#e39f37'};
    // Deterministic two-sector layout. Each category occupies its own columns,
    // preventing genes and drugs from mixing around the central disease.
    function organizedPositions(nodes) {
      const positions = new Map();
      const diseases=nodes.filter(n=>n.type==='disease');
      const genes=nodes.filter(n=>n.type==='gene').sort((a,b)=>a.label.localeCompare(b.label));
      const drugs=nodes.filter(n=>n.type==='drug').sort((a,b)=>a.label.localeCompare(b.label));
      diseases.forEach(n=>positions.set(n.id,{x:1000,y:900}));
      const place=(items,side)=>{
        const cols=Math.max(1,Math.ceil(items.length/30));
        const perCol=Math.ceil(items.length/cols);
        items.forEach((n,i)=>{
          const col=Math.floor(i/perCol),row=i%perCol;
          positions.set(n.id,{x:1000+side*(310+col*310),y:900+(row-(perCol-1)/2)*51});
        });
      };
      place(genes,-1);place(drugs,1);
      return positions;
    }
    const updateGraph = () => {
      if(!graph || !data)return;
      const showNames=labelSwitch ? labelSwitch.checked : true;
      const amount=data.nodes.length;
      const positions=layoutSwitch?.checked ? organizedPositions(data.nodes) : null;
      const host=$('oddb-network-graph');
      host.style.height=`${Math.max(620,Math.min(1650,Math.round(400+amount*12)))}px`;
      graph.clear();graph.setOption({
        animationDuration:250,aria:{enabled:true},
        tooltip:{confine:true,formatter:p => p.dataType==='edge'?html(p.data.description):`${html(p.data.fullLabel)}<br>${html(p.data.type)}`},
        legend:[{data:['Disease','Gene','Drug'],top:0}],
        series:[{type:'graph',layout:positions?'none':'force',roam:true,draggable:true,focusNodeAdjacency:true,
          top:55,bottom:65,left:45,right:80,
          force:{repulsion:amount>140?280:amount>65?260:185,gravity:.12,edgeLength:amount>65?[85,185]:[70,150],friction:.65},
          label:{show:showNames,position:'right',distance:7,fontSize:amount>120?10:11,color:'#344054',formatter:'{b}'},
          emphasis:{focus:'adjacency',label:{show:true}},
          categories:[{name:'Disease'},{name:'Gene'},{name:'Drug'}],
          data:data.nodes.map(n=>({id:n.id,name:n.label,fullLabel:n.label,type:n.type,x:positions?.get(n.id)?.x,y:positions?.get(n.id)?.y,label:positions?{position:n.type==='gene'?'left':'right'}:undefined,category:['disease','gene','drug'].indexOf(n.type),symbolSize:n.type==='disease'?55:n.type==='gene'?17:22,itemStyle:{color:colors[n.type]}})),
          links:data.edges.map((e,i)=>({id:'e'+i,source:e.source,target:e.target,type:e.type,description:e.label,
            lineStyle:{color:e.type==='target_overlap_only'?'#c98d53':'#9cb2c3',type:e.type==='target_overlap_only'?'dashed':'solid',width:e.type==='direct_disease_drug'?2.6:1.5,curveness:.10}}))
        }]},true);
      graph.resize();
    };
    const render = async () => {
      if (!select.value) return;
      const request=++reqNo;
      note.textContent='Loading focused disease–gene–drug network…';
      const p=new URLSearchParams({disease_id:select.value,limit:$('oddb-network-limit').value,target_overlap:$('oddb-network-overlap').checked?'1':'0'});
      try {
        const r=await fetch(`api/stats_network_extra.php?${p}`,{headers:{Accept:'application/json'}});
        const d=await r.json(); if(!r.ok||!d.ok)throw new Error(d.error||`HTTP ${r.status}`);
        if(request!==reqNo)return;
        data=d;
        note.textContent=`${d.disease.name}: ${number(d.nodes.length)} nodes, ${number(d.edges.length)} links. Names are shown on the interactive graph; exports always contain all selected names. Dashed links indicate target-overlap-only hypotheses.`;
        const el=$('oddb-network-graph');if(!graph)graph=ech.init(el);
        updateGraph();
      } catch(err) {if(request===reqNo) note.textContent=`Network unavailable: ${err.message}`;}
    };
    ['oddb-network-disease','oddb-network-limit','oddb-network-overlap'].forEach(id=>$(id).addEventListener('change',render));
    labelSwitch?.addEventListener('change',updateGraph);
    layoutSwitch?.addEventListener('change',updateGraph);
    $('oddb-network-reset').addEventListener('click',()=>{graph?.dispatchAction({type:'restore'});graph?.resize();});
    const pickRP=()=>Array.from(select.options).find(x=>/^retinitis pigmentosa$/i.test(x.textContent.trim())) ||
      Array.from(select.options).find(x=>/retinitis pigmentosa/i.test(x.textContent));
    $('oddb-network-rp').addEventListener('click',()=>{const found=pickRP();if(found){select.value=found.value;render()}else note.textContent='No retinitis pigmentosa entry found in this release.';});
    const filename = ext => {
      const disease = String(data?.disease?.name || 'disease').normalize('NFKD').replace(/[^a-zA-Z0-9]+/g,'-').replace(/^-|-$/g,'').toLowerCase().slice(0,72);
      return `oddb-v1-${disease}-${data.nodes.length}-nodes.${ext}`;
    };
    $('oddb-network-export').addEventListener('click',()=>{
      if(!graph || !data)return;
      // Always export *all* node names, regardless of the on-screen checkbox.
      const onScreen=labelSwitch?.checked ?? true;
      if(!onScreen) {
        // Temporarily force labels into the capture, restoring the user's choice.
        graph.setOption({series:[{label:{show:true}}]});
      }
      const a=document.createElement('a');
      a.href=graph.getDataURL({type:'png',pixelRatio:3,backgroundColor:'#ffffff'});
      a.download=filename('png');document.body.append(a);a.click();a.remove();
      if(!onScreen)graph.setOption({series:[{label:{show:false}}]});
    });
    $('oddb-network-svg')?.addEventListener('click',()=>{
      if(!data)return;
      const {svg}=publicationNetworkSvg(data);
      download(filename('svg'),new Blob([svg],{type:'image/svg+xml;charset=utf-8'}));
    });
    $('oddb-network-csv').addEventListener('click',()=>{if(data)csvFile('oddb-v1-disease-gene-drug-links.csv',['Source','Target','Type','Meaning'],data.edges.map(e=>[e.source,e.target,e.type,e.label]));});
    return {updateDiseases(list) {
      select.replaceChildren();
      list.forEach(d=>{const opt=document.createElement('option');opt.value=d.id;opt.textContent=d.name;select.append(opt);});
      const rp=pickRP();if(rp)select.value=rp.value;
      render();
    },resize(){graph?.resize()}};
  }
  async function fetchData(path) {
    const r=await fetch(ROOT+path,{cache:'no-cache'});
    if(!r.ok)throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  }
  async function init() {
    if(!ech)return;
    for(const id of rankedIds) createCard(id,'oddb-enhanced-rankings',true);
    for(const id of genomeIds) createCard(id,'oddb-enhanced-chromosomes',false);
    for(const id of clinicalIds) createCard(id,'oddb-enhanced-clinical',false);
    const net=network();
    try {
      const [index,rankings,chromosomes,clinical]=await Promise.all(['index.json','rankings.json','chromosomes.json','clinical.json'].map(fetchData));
      const hashes=new Map(index.files.map(f=>[f.file,f.sha256]));
      for(const file of ['rankings.json','chromosomes.json','clinical.json']) if(!hashes.has(file))throw new Error('Snapshot manifest incomplete');
      $('oddb-enhanced-status').textContent=`ODDB v1 statistics snapshot: ${index.database_release} · Generated ${new Date(index.generated_utc).toLocaleDateString()} · Gene chromosomes annotated: ${number(index.gene_chromosome_annotation?.annotated || 0)}/${number(index.gene_chromosome_annotation?.total_genes || 0)}.`;
      for(const id of rankedIds) configs.get(id).allRows=rankings[id] || [];
      for(const id of genomeIds) configs.get(id).allRows=chromosomes[id] || [];
      for(const id of clinicalIds) {
        const c=clinical[id] || [];
        const fields=id==='trial_phases'?['phase','trials']:id==='disease_categories'?['name','count']:['name','count'];
        configs.get(id).allRows=fromSimple(c,fields[0],fields[1]);
      }
      for(const config of configs.values()) {config.update=()=>render(config);render(config);}
      window.ODDBStatsChartSnapshot = id => {
        const config=configs.get(id);
        return config ? {
          columns:['Entity ID','Entity name','Total',...config.dataKeys],
          rows:config.visible.map(r=>[r.id,r.name,r.total,...config.dataKeys.map(k=>r.parts[k]||0)]),
          count:config.visible.length
        } : null;
      };
      net?.updateDiseases(clinical.diseases_for_network || []);
      let timer;window.addEventListener('resize',()=>{clearTimeout(timer);timer=setTimeout(()=>{instances.forEach(c=>c.resize());net?.resize()},160);});
    } catch(err) {
      $('oddb-enhanced-status').className='oddb-enhanced-failure mt-3';
      $('oddb-enhanced-status').textContent=`Scientific charts not yet generated: ${err.message}. Run the CLI JSON snapshot builder and deploy its output. Existing Statistics charts remain available.`;
      for(const config of configs.values())config.article.querySelector('.oddb-enhanced-summary').textContent='Awaiting validated precomputed data';
    }
  }
  document.addEventListener('DOMContentLoaded',init);
})();
