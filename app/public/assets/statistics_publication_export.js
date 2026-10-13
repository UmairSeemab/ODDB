/* ODDB v1 — unified scientific figure export for original + enhanced Statistics charts.
   Browser-only; no database writes or external services. SVG is the canonical figure
   format; PNG is rasterized from the same SVG and embeds pHYs DPI metadata. */
(() => {
  'use strict';
  const E = window.echarts;
  if (!E) return;
  const ORIGINAL = [
    'anatomyDonut','inheritanceDonut','inheritanceCoverageDonut','geneTreemap',
    'variantTreemap','drugStageDonut','therapeuticSankey','trialEvidenceOrbit',
    'reportEvidenceOrbit','relationshipRing','knowledgeFlowChartInner'
  ];
  const RANKINGS=['diseases_genes','diseases_variants','genes_diseases','diseases_trial_drugs','drugs_trial_diseases'];
  const CHROMOSOMES=['genes_by_chromosome_category','variants_by_chromosome_category','genes_by_category_chromosome','variants_by_category_chromosome'];
  const CLINICAL=['trial_phases','disease_categories','evidence_classes'];
  const COLOURS=['#3d6fb4','#259d86','#e6a33c','#845db1','#82b263','#d8756f','#38a3c3','#bb6992','#8b9239','#d4a747','#518ba5','#bf8055'];
  const COUNT = new Intl.NumberFormat('en');
  const $ = id => document.getElementById(id);
  let release=null, openChart=null, pending=false, modal=null, lastFocus=null;
  const escapeXML = s => String(s ?? '').replace(/[&<>"']/g, v=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[v]));
  const value = x => typeof x==='object'&&x!==null&&'value' in x?x.value:x;
  const nval = x => Array.isArray(value(x))?Number(value(x)[0]||0):Number(value(x)||0);
  const safeName = s => String(s||'ODDB-v1').normalize('NFKD').replace(/[^A-Za-z0-9-]+/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'').toLowerCase().slice(0,92);
  const seriesList = option => Array.isArray(option.series)?option.series:option.series?[option.series]:[];
  const first = x => Array.isArray(x)?x[0]:x;
  const plain = x => JSON.parse(JSON.stringify(x));
  function selectedName(option,name){return first(option.legend)?.selected?.[name]!==false;}
  const els = (p,s) => [...p.querySelectorAll(s)];
  function info(id){
    if (id==='oddb-network-graph') {
      const disease=$('oddb-network-disease');
      return {title:'Disease–gene–drug connectivity: '+(disease?.selectedOptions?.[0]?.textContent?.trim()||'selected disease'),
        description:'Gene associations, direct therapeutic evidence and curated drug-target connections. Dashed target-overlap-only links are discovery hypotheses, not clinical benefit.',
        kind:'network',id};
    }
    const element=$(id);
    const card=element?.closest('.viz-card, article');
    const heading=card?.querySelector('.viz-head h3,.knowledge-flow-head h3,h3,h2');
    const sub=card?.querySelector('.oddb-enhanced-description,.viz-head .small,.knowledge-flow-head .small');
    return {id,title:(id==='knowledgeFlowChartInner'?$('knowledgeFlowTitle')?.textContent:null) ||
      (id==='relationshipRing'?$('relationshipTitle')?.textContent:null) || heading?.textContent?.trim() || id,
      description:sub?.textContent?.trim() || 'ODDB v1 Statistics visualization',kind:'echarts'};
  }
  function elementFor(id){
    return [...document.querySelectorAll('[data-scientific-chart]')].find(e=>e.dataset.scientificChart===id)
      ?.querySelector('.oddb-enhanced-plot') || $(id);
  }
  function instance(id){const el=elementFor(id);return el?E.getInstanceByDom(el):null;}
  function categories(option){
    const series=seriesList(option), names=[];
    if(series.length>1) series.forEach(s=>{if(s.name&&selectedName(option,s.name)&&!names.includes(s.name))names.push(s.name);});
    else if(series[0]?.type==='pie' || series[0]?.type==='treemap') (series[0].data||[]).forEach(d=>{if(d.name&&selectedName(option,d.name)&&!names.includes(d.name))names.push(d.name);});
    else if(series[0]?.type==='graph') (series[0].categories||[]).forEach(d=>{if(d.name&&!names.includes(d.name))names.push(d.name);});
    return names;
  }
  function extract(id,option) {
    const s=seriesList(option).filter(q=>!q.name||selectedName(option,q.name)), type=s[0]?.type||'unknown';
    if(type==='pie' || type==='treemap' || type==='sunburst') {
      const selected=first(option.legend)?.selected||{};
      const entries=[];
      const visit=(items,parent='')=>(items||[]).forEach(d=>{
        if(selected[d.name]!==false)entries.push({name:String(d.name||''),parent,value:nval(d)});
        if(d.children?.length)visit(d.children,d.name||parent);
      });
      visit(s[0].data);
      return {type,columns:['name','parent','value'],rows:entries.map(x=>[x.name,x.parent,x.value])};
    }
    if(type==='sankey'){
      const links=(s[0].links||s[0].edges||[]).map(x=>[x.source,x.target,nval(x)]);
      return {type,columns:['source','target','association_count'],rows:links};
    }
    if(type==='graph'){
      const nodes=(s[0].data||[]).map(d=>['node',d.id||d.name,d.name||'', '', '',nval(d)]);
      const links=(s[0].links||s[0].edges||[]).map(d=>['edge',d.id||'', '',d.source,d.target,nval(d)]);
      return {type,columns:['record_type','id','label','source','target','value'],rows:[...nodes,...links]};
    }
    const y=first(option.yAxis),x=first(option.xAxis);
    const axis=y?.type==='category'?y:x?.type==='category'?x:null;
    if(axis && Array.isArray(axis.data)) {
      const columns=['entity',...s.map((d,i)=>String(d.name||`Series ${i+1}`))];
      const rows=axis.data.map((v,i)=>[typeof v==='object'?v.value??v.name:v,...s.map(t=>nval((t.data||[])[i]))]);
      return {type,columns,rows};
    }
    // Cartesian XY and other plots: export displayed ECharts series values, never fabricate counts.
    const rows=[];
    s.forEach((t,j)=>(t.data||[]).forEach((v,i)=>rows.push([t.name||`Series ${j+1}`,i,JSON.stringify(value(v))])));
    return {type,columns:['series','index','value'],rows};
  }
  function shownData(id,option) {
    if(id==='oddb-network-graph'){
      const data=window.ODDBStatsNetworkSnapshot?.();
      if(!data?.nodes?.length)throw Error('The selected network has not finished loading.');
      const label=new Map(data.nodes.map(n=>[n.id,n.label]));
      return {type:'network',columns:['source_id','source_name','target_id','target_name','relation_type','description'],
        rows:data.edges.map(e=>[e.source,label.get(e.source)||'',e.target,label.get(e.target)||'',e.type,e.label||'']),
        nodes:data.nodes,edges:data.edges,disease:data.disease};
    }
    const snapshot=window.ODDBStatsChartSnapshot?.(id);
    if(snapshot?.rows)return {...snapshot,type:'ranked'};
    return extract(id,option);
  }
  function csvEscape(v){
    let s=String(v??'');
    // Prevent spreadsheet applications from interpreting downloaded labels as formulas.
    if(typeof v==='string' && /^[\s]*[=+\-@\t\r]/.test(s))s="'"+s;
    return '"'+s.replaceAll('"','""')+'"';
  }
  function csv(data){return [data.columns,...data.rows].map(r=>r.map(csvEscape).join(',')).join('\r\n')+'\r\n';}
  function metadata(id,data){
    const snap=release||{};
    const isPrecomputed=[...RANKINGS,...CHROMOSOMES,...CLINICAL].includes(id);
    const props={figure:info(id).title,description:info(id).description,
      database_release:snap.database_release||'ODDB v1 (live data; release not verified)',
      generated_utc:snap.generated_utc||null,
      hgnc_reference_sha256:/gene/i.test(info(id).title)?(snap.gene_chromosome_annotation?.source_sha256||null):null,
      source:id==='oddb-network-graph'?'On-demand ODDB database query':isPrecomputed?'Validated ODDB v1 precomputed statistics JSON':'Live ODDB Statistics API',
      selected_rows:data.rows.length, selection:RANKINGS.includes(id)?{
        limit:document.querySelector(`[data-scientific-chart="${id}"] [data-action="limit"]`)?.value,
        search:document.querySelector(`[data-scientific-chart="${id}"] [data-action="search"]`)?.value,
        order:document.querySelector(`[data-scientific-chart="${id}"] [data-action="sort"]`)?.value
      }:id==='oddb-network-graph'?{
        disease_id:$('oddb-network-disease')?.value,
        node_limit:$('oddb-network-limit')?.value,
        include_target_overlap:$('oddb-network-overlap')?.checked,
        node_count:data.nodes?.length,
        edge_count:data.edges?.length
      }:null};
    return props;
  }
  function caption(meta){
    const trail=[meta.description,`Source: ${meta.source}.`,`Release: ${meta.database_release}.`];
    if(meta.hgnc_reference_sha256)trail.push(`HGNC reference SHA-256: ${meta.hgnc_reference_sha256}.`);
    if(meta.figure.toLowerCase().includes('trial'))trail.push('Trial-linked pairs represent shared trial co-occurrence, not necessarily an indication or trial arm.');
    if(meta.figure.toLowerCase().includes('network'))trail.push('Target-overlap-only edges are discovery hypotheses, not evidence of clinical benefit.');
    return `${meta.figure}. ${trail.join(' ')}`;
  }
  function textWrap(s,max=105){
    const words=String(s||'').replace(/\s+/g,' ').split(' '),lines=[];let line='';
    for(const word of words){if((line+' '+word).length>max && line){lines.push(line);line=word;}else line=line?line+' '+word:word;}
    if(line)lines.push(line);
    return lines;
  }
  const txt = (x,y,s,size=20,fill='#344054',weight=400) => `<text x="${x}" y="${y}" fill="${fill}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}">${escapeXML(s)}</text>`;
  function keyNames(option,id,withLegend){
    if(!withLegend)return [];
    if(id==='oddb-network-graph')return ['Disease','Gene','Drug','Recorded association','Curated drug target','Target-overlap only'];
    return categories(option).slice(0,120);
  }
  function makeLegend(names,width,option,type){
    if(!names.length)return {svg:'',height:0};
    const cols=Math.min(6,Math.max(1,Math.floor((width-110)/350)));
    const colWidth=(width-110)/cols;
    const colors=option.color||COLOURS;
    const netColours={'Disease':'#3d6fb4','Gene':'#259d86','Drug':'#e6a33c'};
    let y=0,svg='';
    for(let start=0;start<names.length;start+=cols){
      const group=names.slice(start,start+cols);
      const segments=group.map(s=>textWrap(s,Math.max(18,Math.floor((colWidth-28)/8.5))));
      const maxLines=Math.max(...segments.map(x=>x.length));
      group.forEach((name,col)=>{
        const x=60+col*colWidth;
        const matching=seriesList(option).find(e=>e.name===name);
        const color=matching?.itemStyle?.color||netColours[name]||colors[(start+col)%colors.length];
        if(name==='Target-overlap only'||name==='Recorded association'||name==='Curated drug target') {
          svg+=`<line x1="${x}" y1="${y+16}" x2="${x+23}" y2="${y+16}" stroke="${name==='Target-overlap only'?'#c38430':name==='Curated drug target'?'#4f9d8a':'#9db1c6'}" stroke-width="3" ${name==='Target-overlap only'?'stroke-dasharray="7 5"':name==='Curated drug target'?'stroke-dasharray="3 5"':''}/>`;
        }else svg+=`<rect x="${x}" y="${y+8}" width="16" height="16" rx="2" fill="${escapeXML(color)}"/>`;
        segments[col].forEach((line,k)=>svg+=txt(x+24,y+22+k*21,line,15));
      });
      y+=Math.max(34, maxLines*21+13);
    }
    return {svg,height:y+8};
  }
  function chartDimensions(id,option,rows){
    const type=seriesList(option)[0]?.type||'unknown';
    const cats=Math.max(1,rows.length);
    const height=type==='bar'||type==='line'?Math.min(14000,Math.max(770,160+cats*39)):
      type==='graph'||type==='sankey'?1250:950;
    const longest=Math.max(0,...(first(option.yAxis)?.data||[]).map(s=>String(s?.value??s).length));
    return {width:Math.min(2700,Math.max(2000, 1370+Math.min(longest,130)*10)),height,type};
  }
  function prepareOption(option, dims, settings){
    const clone=plain(option);
    clone.animation=false;clone.backgroundColor=settings.background==='transparent'?'transparent':'#ffffff';
    clone.color=clone.color||COLOURS;
    clone.tooltip={show:false};clone.toolbox={show:false};
    // Decorative on-screen annotations can land outside their original bounds in exports.
    clone.graphic=[];
    clone.title=[];
    const selected=first(option.legend)?.selected||{};
    clone.legend=[]; // Complete, non-scrolling legend is drawn outside the chart.
    const s=seriesList(clone).filter(q=>!q.name||selected[q.name]!==false);
    if(s[0]?.type==='pie')s[0].data=(s[0].data||[]).filter(d=>selected[d.name]!==false);
    const type=s[0]?.type;
    if(type==='bar'||type==='line'||type==='scatter'){
      const grid=first(clone.grid)||{};
      const y=first(clone.yAxis)||{};
      const vertical=y.type==='category';
      clone.grid={...grid,left:vertical?35:110,right:75,top:26,bottom:95,containLabel:true};
      [clone.yAxis,clone.xAxis].forEach((axis,i)=>{
        if(!axis)return;
        const ary=Array.isArray(axis)?axis:[axis];
        ary.forEach(a=>{a.axisLabel={...(a.axisLabel||{}),fontSize:18,color:'#334155',interval:0};
          if(a.type==='category'){
            a.axisLabel.overflow='break';a.axisLabel.width=vertical?Math.min(900,dims.width*.36):dims.width*.25;
          }
          if(a.name)a.nameTextStyle={...(a.nameTextStyle||{}),fontSize:21};
        });
      });
      s.forEach(d=>{d.label={...(d.label||{}),show:false};if(d.type==='bar')d.barMaxWidth=30;});
    } else if(type==='pie'){
      s[0].radius=['35%','68%'];s[0].center=['50%','53%'];s[0].label={show:settings.labels,formatter:'{b}: {c}',fontSize:16,overflow:'truncate'};
    } else if(type==='treemap'){
      s[0].left=50;s[0].right=55;s[0].top=40;s[0].bottom=50;
      s[0].label={...(s[0].label||{}),show:settings.labels,fontSize:18};
      s[0].breadcrumb={show:false};
    } else if(type==='sankey'){
      s[0].left=180;s[0].right=190;s[0].top=60;s[0].bottom=70;
      s[0].label={...(s[0].label||{}),show:settings.labels,fontSize:20};
      s[0].nodeGap=25;
    } else if(type==='graph'){
      s[0].top=60;s[0].bottom=75;s[0].left=100;s[0].right=100;
      s[0].label={...(s[0].label||{}),show:settings.labels,fontSize:17};
      s[0].force={...(s[0].force||{}),layoutAnimation:false};
    }
    clone.series=s;
    return clone;
  }
  function renderEchartsSVG(id,option,settings,measure){
    const dims=chartDimensions(id,option,measure.rows);
    const holder=document.createElement('div');
    holder.style.cssText=`position:fixed;left:-100000px;top:0;width:${dims.width}px;height:${dims.height}px;pointer-events:none`;
    document.body.append(holder);let renderer;
    try {
      renderer=E.init(holder,null,{renderer:'svg',width:dims.width,height:dims.height});
      const prepared=prepareOption(option,dims,settings);
      renderer.setOption(prepared,true);
      const svg=holder.querySelector('svg');
      if(!svg)throw Error('The SVG renderer did not create a figure.');
      return {content:svg.outerHTML,width:dims.width,height:dims.height};
    } finally {renderer?.dispose();holder.remove();}
  }
  function networkSVG(data,settings){
    const width=3000,gene=data.nodes.filter(n=>n.type==='gene').sort((a,b)=>a.label.localeCompare(b.label)),
      drug=data.nodes.filter(n=>n.type==='drug').sort((a,b)=>a.label.localeCompare(b.label));
    const disease=data.nodes.find(n=>n.type==='disease');
    if(!disease)throw Error('No disease node in network response.');
    const rowH=58,header=170,usable=Math.max(850,Math.max(gene.length,drug.length)*rowH+210);
    const height=header+usable;
    const mid=header+usable/2,lX=1080,rX=1920,center=1500;
    const positions=new Map([[disease.id,{x:center,y:mid}]]);
    for(const [nodes,x] of [[gene,lX],[drug,rX]]){
      const y0=mid-(nodes.length-1)*rowH/2;
      nodes.forEach((n,i)=>positions.set(n.id,{x,y:y0+i*rowH}));
    }
    let svg='';
    data.edges.forEach(e=>{
      const a=positions.get(e.source),b=positions.get(e.target);if(!a||!b)return;
      const overlap=e.type==='target_overlap_only',target=e.type==='drug_target';
      svg+=`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${overlap?'#c38430':target?'#4f9d8a':'#9db1c6'}" stroke-width="${target?1.8:2.1}" ${overlap?'stroke-dasharray="10 6"':target?'stroke-dasharray="4 7"':''} opacity=".60"/>`;
    });
    const dot=(n,x,y,side)=>{
      const color=n.type==='gene'?'#259d86':'#e6a33c';
      const tx=side==='left'?x-24:x+24, anchor=side==='left'?'end':'start';
      const lines=textWrap(n.label,80);
      const label=lines.map((line,i)=>`<text x="${tx}" y="${y+(i-(lines.length-1)/2)*22+6}" text-anchor="${anchor}" font-size="19" font-family="Arial,Helvetica,sans-serif" fill="#21344c">${escapeXML(line)}</text>`).join('');
      return `<circle cx="${x}" cy="${y}" r="11" fill="${color}" stroke="white" stroke-width="2"/>`+
        (settings.labels?label:'');
    };
    gene.forEach(n=>{const p=positions.get(n.id);svg+=dot(n,p.x,p.y,'left');});
    drug.forEach(n=>{const p=positions.get(n.id);svg+=dot(n,p.x,p.y,'right');});
    svg+=`<circle cx="${center}" cy="${mid}" r="34" fill="#3d6fb4" stroke="white" stroke-width="4"/>`;
    if(settings.labels)svg+=`<rect x="${center-270}" y="${mid+42}" rx="9" width="540" height="40" fill="white" opacity=".9"/>`+
      `<text x="${center}" y="${mid+70}" text-anchor="middle" font-size="24" font-family="Arial,Helvetica,sans-serif" font-weight="bold" fill="#203450">${escapeXML(data.disease?.name||disease.label)}</text>`;
    const headers=txt(lX-20,header+25,`GENES (${gene.length})`,24,'#20866f',700)+txt(rX+20,header+25,`DRUGS (${drug.length})`,24,'#a16b1e',700);
    return {content:`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${headers}${svg}</svg>`,width,height};
  }
  function composeFigure(plot,title,description,meta,settings,option,id){
    const width=plot.width,margin=60;
    const descriptions=textWrap(description,Math.max(75,Math.floor(width/17)) ).slice(0,4);
    const allLegend=keyNames(option,id,settings.legend);
    const legend=makeLegend(allLegend,width,option,seriesList(option)[0]?.type);
    const topHeight=142+descriptions.length*29+legend.height;
    const footerLines=settings.provenance?[meta.database_release,meta.source,meta.hgnc_reference_sha256?`HGNC annotation SHA-256 ${meta.hgnc_reference_sha256}`:''].filter(Boolean):[];
    if(id==='oddb-network-graph')footerLines.push('Target-overlap-only: discovery context, not evidence of clinical benefit.');
    const footerHeight=75+footerLines.length*30;
    const height=topHeight+plot.height+footerHeight;
    const header=txt(margin,62,'ODDB v1 | '+title,35,'#172033',700)+
      descriptions.map((l,i)=>txt(margin,105+i*29,l,19,'#52647b')).join('');
    const lead=115+descriptions.length*29;
    const l=legend.svg?`<g transform="translate(0 ${lead})">${legend.svg}</g>`:'';
    const f=footerLines.map((line,i)=>txt(margin,topHeight+plot.height+42+i*30,line,17,'#53657c')).join('');
    const background=settings.background==='transparent'?'none':'#ffffff';
    return `<?xml version="1.0" encoding="UTF-8"?>\n`+
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeXML(title)}">`+
      `<rect width="${width}" height="${height}" fill="${background}"/>${header}${l}`+
      `<svg x="0" y="${topHeight}" width="${plot.width}" height="${plot.height}" viewBox="0 0 ${plot.width} ${plot.height}">${plot.content.replace(/^<svg\b[^>]*>/,'').replace(/<\/svg>\s*$/,'')}</svg>`+
      `${f}</svg>`;
  }
  function triggerFile(filename,blob){
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),12000);
  }
  function uint32(bytes,index,n){bytes[index]=(n>>>24)&255;bytes[index+1]=(n>>>16)&255;bytes[index+2]=(n>>>8)&255;bytes[index+3]=n&255;}
  function crc32(bytes){let c=0xffffffff;for(const v of bytes){c^=v;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;}
  async function setPngDpi(blob,dpi){
    const src=new Uint8Array(await blob.arrayBuffer());
    if(src.length<33||src.slice(0,8).join(',')!=='137,80,78,71,13,10,26,10')throw Error('Unexpected PNG data');
    const bytes=new Uint8Array(21),ppm=Math.round(dpi/0.0254); // PNG pixels per meter
    uint32(bytes,0,9);bytes.set([112,72,89,115],4); // pHYs
    uint32(bytes,8,ppm);uint32(bytes,12,ppm);bytes[16]=1;
    uint32(bytes,17,crc32(bytes.slice(4,17)));
    const result=new Uint8Array(src.length+21);
    result.set(src.slice(0,33),0);result.set(bytes,33);result.set(src.slice(33),54);
    return new Blob([result],{type:'image/png'});
  }
  function raster(svg,dpi){
    return new Promise((resolve,reject)=>{
      const img=new Image(),blob=new Blob([svg],{type:'image/svg+xml'}),url=URL.createObjectURL(blob);
      const done=()=>URL.revokeObjectURL(url);
      img.onload=async()=>{
        try{
          const w=7*dpi,h=Math.round(w*img.naturalHeight/img.naturalWidth);
          if(w*h>45000000||h>30000)throw Error('This figure is too large for a browser PNG. Choose SVG or 300 DPI, or reduce Top-N.');
          const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
          const ctx=canvas.getContext('2d');if(!ctx)throw Error('Canvas not available');
          ctx.drawImage(img,0,0,w,h);
          const png=await new Promise((yes,no)=>canvas.toBlob(b=>b?yes(b):no(Error('Cannot encode PNG')),'image/png'));
          resolve(await setPngDpi(png,dpi));
          canvas.width=1;canvas.height=1;
        }catch(err){reject(err);}finally{done();}
      };
      img.onerror=()=>{done();reject(Error('The browser could not rasterize this SVG. Try SVG export.'));};
      img.src=url;
    });
  }
  function showModal(id){
    const inf=info(id);
    if(!inf)return;
    openChart=id;lastFocus=document.activeElement;
    const chart=instance(id),data=id==='oddb-network-graph'?window.ODDBStatsNetworkSnapshot?.():chart?.getOption();
    if(!data){alert('The chart is still loading. Please try again.');return;}
    modal.hidden=false;
    $('oddb-pub-title').textContent=`Export: ${inf.title}`;
    $('oddb-pub-feedback').textContent='';
    $('oddb-pub-format').value='svg';
    $('oddb-pub-format').dispatchEvent(new Event('change'));
    $('oddb-pub-format').focus();
  }
  function closeModal(){modal.hidden=true;openChart=null;lastFocus?.focus?.();}
  function settings(){return {
    format:$('oddb-pub-format').value,dpi:Number($('oddb-pub-dpi').value),
    labels:$('oddb-pub-labels').checked,legend:$('oddb-pub-legend').checked,
    provenance:$('oddb-pub-provenance').checked,background:$('oddb-pub-bg').value
  };}
  async function runExport(){
    if(pending||!openChart)return;
    const id=openChart,sets=settings(),feedback=$('oddb-pub-feedback'),btn=$('oddb-pub-submit');
    pending=true;btn.disabled=true;feedback.textContent='Preparing export…';
    try{
      const chart=instance(id);
      if(id!=='oddb-network-graph'&&!chart)throw Error('Chart not ready');
      const option=chart?.getOption()||{},data=shownData(id,option),meta=metadata(id,data),stem=safeName(meta.figure);
      if(sets.format==='csv')triggerFile(stem+'.csv',new Blob(['\ufeff',csv(data)],{type:'text/csv;charset=utf-8'}));
      else if(sets.format==='json')triggerFile(stem+'.json',new Blob([JSON.stringify({metadata:meta,columns:data.columns,rows:data.rows,...(id==='oddb-network-graph'?{network:{disease:data.disease,nodes:data.nodes,edges:data.edges}}:{})},null,2)+'\n'],{type:'application/json;charset=utf-8'}));
      else if(sets.format==='caption'){
        const content=caption(meta);
        await navigator.clipboard.writeText(content);
        feedback.textContent='Figure caption copied to clipboard.';return;
      } else {
        const plot=id==='oddb-network-graph'?networkSVG(data,sets):renderEchartsSVG(id,option,sets,data);
        const svg=composeFigure(plot,meta.figure,meta.description,meta,sets,option,id);
        if(sets.format==='svg')triggerFile(stem+'.svg',new Blob([svg],{type:'image/svg+xml;charset=utf-8'}));
        else triggerFile(`${stem}-${sets.dpi}dpi.png`,await raster(svg,sets.dpi));
      }
      feedback.textContent='Export created for the current chart selection.';
    }catch(err){console.error('ODDB publication export',err);feedback.textContent='Export failed: '+err.message;}
    finally{pending=false;btn.disabled=false;}
  }
  function newButton(id){
    const button=document.createElement('button');button.type='button';button.className='btn btn-outline-primary btn-sm oddb-pub-trigger';
    button.textContent='Publication export';button.dataset.publicationFor=id;
    button.addEventListener('click',()=>showModal(id));return button;
  }
  function installButtons(){
    for(const id of [...ORIGINAL,...RANKINGS,...CHROMOSOMES,...CLINICAL,'oddb-network-graph']){
      if(document.querySelector(`[data-publication-for="${id}"]`))continue;
      const el=elementFor(id);if(!el)continue;
      const card=el.closest('.viz-card,article');if(!card)continue;
      let host;
      if(id==='oddb-network-graph')host=card.querySelector('.oddb-network-footer');
      else if(card.dataset.scientificChart)host=card.querySelector('.oddb-enhanced-actions');
      else {
        host=card.querySelector('.viz-head,.knowledge-flow-head');
        if(!host||card.querySelectorAll('.chart').length>1){
          host=document.createElement('div');host.className='oddb-pub-subchart-row';
          el.parentElement.insertBefore(host,el);
        }
      }
      if(host)host.append(newButton(id));
    }
  }
  function createModal(){
    modal=document.createElement('div');modal.id='oddb-pub-modal';modal.hidden=true;
    modal.innerHTML=`<div class="oddb-pub-backdrop" data-close="1"></div>
    <div class="oddb-pub-dialog" role="dialog" aria-modal="true" aria-labelledby="oddb-pub-title">
      <div class="oddb-pub-head"><h3 id="oddb-pub-title">Export chart</h3><button type="button" class="oddb-pub-close" aria-label="Close export dialog" data-close="1">×</button></div>
      <label>Format<select id="oddb-pub-format" class="form-select"><option value="svg">SVG — editable vector figure</option><option value="png">PNG — high-resolution figure</option><option value="csv">CSV — visible numerical data</option><option value="json">JSON — visible data with release metadata</option><option value="caption">Copy scientific figure caption</option></select></label>
      <div id="oddb-pub-image-options" class="oddb-pub-fields">
        <label id="oddb-pub-dpi-wrap">PNG resolution<select id="oddb-pub-dpi" class="form-select"><option value="300">300 DPI · 2100 px wide (7 inches)</option><option value="600">600 DPI · 4200 px wide (7 inches)</option></select></label>
        <label>Background<select id="oddb-pub-bg" class="form-select"><option value="white">White</option><option value="transparent">Transparent</option></select></label>
        <label><input type="checkbox" id="oddb-pub-labels" checked> Show labels</label>
        <label><input type="checkbox" id="oddb-pub-legend" checked> Include full legend</label>
        <label><input type="checkbox" id="oddb-pub-provenance" checked> Show ODDB release and data source</label>
      </div>
      <p class="oddb-pub-disclaimer">Exports reflect the selected Top-N limit, search and sort controls. PNG contains DPI metadata. For dense plots, SVG usually provides the best journal-editing experience.</p>
      <div class="oddb-pub-foot"><button type="button" class="btn btn-outline-secondary" data-close="1">Cancel</button><button type="button" class="btn btn-primary" id="oddb-pub-submit">Export</button></div>
      <div id="oddb-pub-feedback" role="status" aria-live="polite"></div>
    </div>`;
    document.body.append(modal);
    modal.addEventListener('click',e=>{if(e.target.closest('[data-close]'))closeModal();});
    $('oddb-pub-submit').addEventListener('click',runExport);
    $('oddb-pub-format').addEventListener('change',()=>{
      const f=$('oddb-pub-format').value;
      $('oddb-pub-image-options').hidden=!['svg','png'].includes(f);
      $('oddb-pub-dpi-wrap').hidden=f!=='png';
      $('oddb-pub-submit').textContent=f==='caption'?'Copy caption':'Export';
    });
    document.addEventListener('keydown',e=>{
      if(modal.hidden)return;
      if(e.key==='Escape')closeModal();
      if(e.key==='Tab'){
        const all=els(modal,'.oddb-pub-dialog button:not([disabled]),.oddb-pub-dialog select:not([disabled]),.oddb-pub-dialog input:not([disabled])').filter(x=>x.offsetParent!==null);
        const ix=all.indexOf(document.activeElement);
        if(e.shiftKey&&ix===0){e.preventDefault();all.at(-1).focus();}
        if(!e.shiftKey&&ix===all.length-1){e.preventDefault();all[0].focus();}
      }
    });
  }
  async function init(){
    createModal();installButtons();
    try{const r=await fetch('assets/statistics_data/index.json',{cache:'no-cache'});if(r.ok)release=await r.json();}catch(_){ /* The original charts also support live API data. */ }
    setTimeout(installButtons,450);
    setTimeout(installButtons,1450);
  }
  document.addEventListener('DOMContentLoaded',init);
  // Pure helpers for automated tests; no DOM interaction or private data.
  window.ODDBPublicationExportTest={csv,extract,textWrap,crc32,caption,setPngDpi,networkSVG};
})();
