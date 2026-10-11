/* ODDB publication exports v0.7.7. Figures and evidence use validated database records. */
(() => {
 'use strict';
 const get=id=>document.getElementById(id),esc=v=>window.ODDBAnalysis.xml(v),n=v=>Number(Number(v).toFixed(4)),PT=96/72,MM=96/25.4;
 const NODE_NAMES={disease:'Disease',gene:'Gene',locus:'Locus',variant:'Variant',drug:'Drug',trial:'Clinical trial',report:'Clinical report',consequence:'Variant consequence'};
 const EDGE_NAMES={disease_gene:'Disease–gene',disease_locus:'Disease–locus',disease_variant:'Explicit disease–variant',gene_variant:'Gene–variant',variant_consequence:'Variant consequence',direct_disease_drug:'Direct therapeutic evidence',drug_target:'Drug–target pharmacology',target_overlap_only:'Target-overlap discovery',disease_trial:'Disease–trial association',drug_trial:'Drug–trial association',disease_report:'Disease–report association',drug_report:'Drug–report association'};
 let dialog,plan=null,output=null,previewURL=null,serial=0,busyPNG=false,timer=null;
 function value(e,key,fallback){const v=e.style(key);return v===undefined||v===null||v===''?fallback:v;}
 function measure(text,size,font){const ctx=document.createElement('canvas').getContext('2d');ctx.font=`${size}px ${font}`;return ctx.measureText(text).width;}
 function wrap(text,width,size,font){
  const lines=[];for(const paragraph of String(text).split('\n')){let line='';for(const word of paragraph.split(/\s+/)){
   if(measure(word,size,font)>width){if(line){lines.push(line);line='';}for(const char of Array.from(word)){if(line&&measure(line+char,size,font)>width){lines.push(line);line='';}line+=char;}}
   else{const next=line?`${line} ${word}`:word;if(line&&measure(next,size,font)>width){lines.push(line);line=word;}else line=next;}
  }lines.push(line);}return lines;
 }
 function textLines(lines,x,y,size,font,fill='#334155',weight='normal'){
  return `<text x="${n(x)}" y="${n(y)}" font-family="${esc(font)}" font-size="${n(size)}" fill="${fill}" font-weight="${weight}">${lines.map((line,i)=>`<tspan x="${n(x)}" dy="${i?n(size*1.3):0}">${esc(line)}</tspan>`).join('')}</text>`;
 }
 function settings(raw){
  const width=Number(raw.width),height=Number(raw.height),labelSize=Number(raw.labelSize);
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<60||height<60||width>600||height>600)throw new Error('Choose a width and height between 60 and 600 mm.');
  if(!Number.isFinite(labelSize)||labelSize<5||labelSize>18)throw new Error('Choose a label size between 5 and 18 pt.');
  if(!['full','selected','viewport'].includes(raw.scope))throw new Error('Choose a supported export scope.');
  return {scope:raw.scope,width,height,labelSize,font:['Arial','sans-serif','serif'].includes(raw.font)?raw.font:'Arial',title:String(raw.title??'').slice(0,120),showLabels:raw.showLabels!==false,showLegend:raw.showLegend!==false,showMetadata:raw.showMetadata!==false,transparent:raw.transparent===true};
 }
 function fromForm(){return settings({scope:get('publicationScope').value,width:get('publicationWidth').value,height:get('publicationHeight').value,labelSize:get('publicationLabelSize').value,font:get('publicationFont').value,title:get('publicationFigureTitle').value,showLabels:get('publicationLabels').checked,showLegend:get('publicationLegend').checked,showMetadata:get('publicationMetadata').checked,transparent:get('publicationTransparent').checked});}
 function graphCollection(scope){
  if(!cy)throw new Error('The network is not ready.');
  let collection=(scope==='selected'?selectedElements():visibleElementCollection()).filter(e=>!e.hasClass('layer-hidden')&&e.visible());
  const ids=new Set(collection.nodes().map(e=>e.id()));collection=collection.filter(e=>e.isNode()||(ids.has(e.data('source'))&&ids.has(e.data('target'))));
  if(!collection.nodes().length)throw new Error(scope==='selected'?'Select at least one visible node for a publication export.':'Add at least one visible entity to the graph first.');
  return collection;
 }
 function references(collection){return {nodes:collection.nodes().map(e=>({type:e.data('type'),entity_id:e.data('entity_id')})),edges:collection.edges().map(e=>({id:e.id(),type:e.data('type'),source:e.data('source'),target:e.data('target')}))};}
 function validated(collection,response,scope){
  if(!Array.isArray(response.nodes)||!Array.isArray(response.edges)||!Array.isArray(response.issues)||!response.metadata?.validated_at)throw new Error('The validation response is incomplete. Retry validation.');
  const nodes=new Map(response.nodes.map(d=>[d.id,d])),edges=new Map(response.edges.map(d=>[d.id,d]));
  let kept=collection.filter(e=>e.isNode()?nodes.has(e.id()):edges.has(e.id())&&nodes.has(e.data('source'))&&nodes.has(e.data('target')));
  const evidenceInfo=window.ODDBEvidence?.exportInfo();
  const before=kept.edges().length;if(evidenceInfo)kept=window.ODDBEvidence.exportCollection(kept,nodes,edges,evidenceInfo.filters);
  const evidenceExcluded=before-kept.edges().length;
  if(!kept.nodes().length)throw new Error('No entities in this export could be validated against the current database.');
  return {collection:kept,nodes,edges,scope,metadata:response.metadata,issues:response.issues,evidenceInfo,evidenceExcluded,exportedAt:new Date().toISOString()};
 }
 function legend(plan,opt,width){
  if(!opt.showLegend)return {height:0,parts:[]};
  const font=opt.font,size=7.5*PT,heading=9*PT,gap=20,columns=width>=500?2:1,colW=(width-gap*(columns-1))/columns;
  const nodeExamples=new Map(),edgeExamples=new Map();plan.collection.nodes().forEach(e=>{if(!nodeExamples.has(e.data('type')))nodeExamples.set(e.data('type'),e);});plan.collection.edges().forEach(e=>{if(!edgeExamples.has(e.data('type')))edgeExamples.set(e.data('type'),e);});
  const groups=[['Entities',Object.keys(NODE_NAMES).filter(type=>nodeExamples.has(type)).map(type=>({type,kind:'node',example:nodeExamples.get(type),label:NODE_NAMES[type]}))],['Relationships',Object.keys(EDGE_NAMES).filter(type=>edgeExamples.has(type)).map(type=>({type,kind:'edge',example:edgeExamples.get(type),label:EDGE_NAMES[type]}))]].filter(g=>g[1].length);
  const parts=[];let bottom=0;
  groups.forEach(([title,items],groupIndex)=>{
   const col=columns===2?groupIndex:0,x=col*(colW+gap);let y=columns===1?bottom+heading:heading;
   parts.push(textLines([title],x,y,heading,font,'#172033','bold'));y+=14;
   for(const item of items){
    const lines=wrap(item.label,colW-42,size,font),cy=y+size/2;
    if(item.kind==='node'){
     const sample={position:()=>({x:x+13,y:cy}),width:()=>17,height:()=>value(item.example,'shape','ellipse')==='round-rectangle'?12:17,style:key=>key==='shape'?value(item.example,'shape','ellipse'):undefined};
     parts.push(window.ODDBAnalysis.nodeShape(sample,`fill="${esc(value(item.example,'background-color','#64748b'))}" stroke="#ffffff" stroke-width="1"`));
    }else{
     const color=value(item.example,'line-color','#94a3b8'),style=value(item.example,'line-style','solid');
     const dash=style==='dotted'?' stroke-dasharray="2,4"':style==='dashed'?' stroke-dasharray="7,5"':'';
     parts.push(`<path d="M ${n(x)} ${n(cy)} L ${n(x+26)} ${n(cy)}" fill="none" stroke="${esc(color)}" stroke-width="${item.type==='direct_disease_drug'?3:2}"${dash}/>`);
     if(value(item.example,'target-arrow-shape','none')==='triangle')parts.push(`<path d="M ${n(x+21)} ${n(cy-4)} L ${n(x+28)} ${n(cy)} L ${n(x+21)} ${n(cy+4)} Z" fill="${esc(color)}"/>`);
    }
    parts.push(textLines(lines,x+36,y+size,size,font));y+=Math.max(23,lines.length*size*1.3+6);
   }
   bottom=Math.max(bottom,y+8);
  });
  const remarks=[];
  if(edgeExamples.has('target_overlap_only'))remarks.push('Target overlap is a discovery connection, not direct therapeutic evidence.');
  if(['disease_trial','drug_trial','disease_report','drug_report'].some(t=>edgeExamples.has(t)))remarks.push('Clinical associations alone do not establish approval or efficacy.');
  if(plan.scope==='viewport')remarks.push('Viewport crop. The evidence table covers the full shown network.');
  if(remarks.length){const lines=wrap(remarks.join(' '),width,size,font);parts.push(textLines(lines,0,bottom+size,size,font,'#475569'));bottom+=lines.length*size*1.3+10;}
  return {height:bottom,parts};
 }
 function parseGraph(svg){
  const match=svg.match(/^(?:<\?xml[^>]*\?>\s*)?<svg\b([^>]*)>([\s\S]*)<\/svg>\s*$/);
  if(!match)throw new Error('The vector graph could not be composed.');
  const boxMatch=match[1].match(/\bviewBox="([^"]+)"/),box=boxMatch?.[1].split(/\s+/).map(Number);
  if(!box||box.length!==4||!box.every(Number.isFinite)||box[2]<=0||box[3]<=0)throw new Error('The vector graph has invalid dimensions.');
  const inner=match[2].replace(/^<title>[\s\S]*?<\/title><desc>[\s\S]*?<\/desc><metadata>[\s\S]*?<\/metadata>/,'').replace(/<rect\b[^>]*fill="#ffffff"\/>/,'');
  return {box,inner};
 }
 function compose(plan,raw){
  const opt=settings(raw),W=opt.width*MM,H=opt.height*MM,margin=18,innerW=W-margin*2,font=opt.font;
  const legendBlock=legend(plan,opt,innerW),parts=[];let top=margin;
  if(opt.title.trim()){const lines=wrap(opt.title,innerW,14*PT,font);parts.push(textLines(lines,margin,top+14*PT,14*PT,font,'#172033','bold'));top+=lines.length*14*PT*1.3+12;}
  if(opt.showMetadata){
   const line=`Release: ${plan.metadata.release_id||'Not configured'}  ·  Exported (UTC): ${plan.exportedAt.replace('T',' ').replace(/\.\d+Z$/,'')}`;
   const lines=wrap(line,innerW,7*PT,font);parts.push(textLines(lines,margin,top+7*PT,7*PT,font,'#64748b'));top+=lines.length*7*PT*1.3+12;
  }
  if(plan.evidenceInfo&&window.ODDBEvidence.active(plan.evidenceInfo.filters)){
   const full=plan.evidenceInfo.description,caption=full.length>240?full.slice(0,220)+'… (full filters in metadata/CSV)':full;
   const lines=wrap('Evidence filters · '+caption,innerW,7*PT,font);parts.push(textLines(lines,margin,top+7*PT,7*PT,font,'#475569'));top+=lines.length*7*PT*1.3+10;
  }
  const graphH=H-top-margin-(legendBlock.height?legendBlock.height+20:0);
  if(graphH<85)throw new Error('The title and legend leave too little graph space. Increase figure height or hide the legend.');
  let graph=parseGraph(window.ODDBAnalysis.svgDocument(plan.scope,{collection:plan.collection,nodeData:plan.nodes,showLabels:false,labelSize:opt.labelSize*PT,fontFamily:font}));
  let scale=Math.min(innerW/graph.box[2],graphH/graph.box[3]),converged=!opt.showLabels,labelBoxes=[];
  if(opt.showLabels){
   for(let i=0;i<20;i++){
    labelBoxes=[];
    graph=parseGraph(window.ODDBAnalysis.svgDocument(plan.scope,{collection:plan.collection,nodeData:plan.nodes,labelSize:opt.labelSize*PT/scale,labelWidth:100/scale,fontFamily:font,showLabels:true,labelHalo:!opt.transparent,labelBoxes}));
    const next=Math.min(innerW/graph.box[2],graphH/graph.box[3]);
    if(Math.abs(next-scale)/scale<0.0001){scale=next;converged=true;break;}scale=next;
   }
   if(!converged||!Number.isFinite(scale)||scale<=0)throw new Error('The labels cannot fit at this size. Increase figure dimensions or hide entity labels.');
  }
  let overlaps=0;const ordered=labelBoxes.sort((a,b)=>a.x1-b.x1);
  outer:for(let i=0;i<ordered.length;i++)for(let j=i+1;j<ordered.length&&ordered[j].x1<ordered[i].x2;j++)if(ordered[j].y1<ordered[i].y2&&ordered[j].y2>ordered[i].y1){overlaps++;if(overlaps>=1000)break outer;}
  parts.push(`<svg x="${n(margin)}" y="${n(top)}" width="${n(innerW)}" height="${n(graphH)}" viewBox="${graph.box.map(n).join(' ')}" preserveAspectRatio="xMidYMid meet" overflow="hidden">${graph.inner}</svg>`);
  if(legendBlock.height){const y=top+graphH+20;parts.push(`<g transform="translate(${n(margin)} ${n(y)})">${legendBlock.parts.join('')}</g>`);}
  const metadata={application:'ODDB v1',export_version:'0.7.8',evidence_filters:plan.evidenceInfo||null,evidence_revalidation_excluded:plan.evidenceExcluded||0,title:opt.title,scope:plan.scope,evidence_scope:plan.scope==='viewport'?'full_shown_network':plan.scope,width_mm:opt.width,height_mm:opt.height,label_size_pt:opt.labelSize,labels_visible:opt.showLabels,font:opt.font,legend_visible:opt.showLegend,transparent:opt.transparent,exported_at:plan.exportedAt,validated_at:plan.metadata.validated_at,release_id:plan.metadata.release_id||null,release_status:plan.metadata.release_status||'unknown',graph_checksum:plan.metadata.graph_checksum||null,label_overlap_count:overlaps,label_overlap_count_capped:overlaps>=1000,entities:plan.collection.nodes().map(e=>({id:e.id(),type:e.data('type')})),relationships:plan.collection.edges().map(e=>({id:e.id(),type:e.data('type'),source:e.data('source'),target:e.data('target')})),entity_ids:plan.collection.nodes().map(e=>e.id()),relationship_ids:plan.collection.edges().map(e=>e.id()),validation_issues:plan.issues,viewport_crop:plan.scope==='viewport'};
  const svg=`<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${n(opt.width)}mm" height="${n(opt.height)}mm" viewBox="0 0 ${n(W)} ${n(H)}"><title>${esc(opt.title||'ODDB evidence network')}</title><desc>Validated ODDB evidence network. Relationship types, record identifiers and validation details are embedded in metadata.</desc><metadata>${esc(JSON.stringify(metadata))}</metadata>${opt.transparent?'':`<rect width="${n(W)}" height="${n(H)}" fill="#ffffff"/>`}${parts.join('')}</svg>`;
  return {svg,opt,metadata,scale,overlaps,labelSizeOutput:opt.showLabels?opt.labelSize*PT:0};
 }
 function csvCell(value){let s=value===null||value===undefined?'':typeof value==='object'?JSON.stringify(value):String(value);if(/^[\s]*[=+@-]/.test(s)||/^[\t\r\n]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
 const COLUMNS=['figure_title','scope','evidence_scope','exported_at','validated_at','database_release','database_release_status','active_evidence_filters','evidence_filters_description','graph_checksum','relationship_id','relationship_type','relationship_label','source_node_id','source_entity_id','source_entity_type','source_label','target_node_id','target_entity_id','target_entity_type','target_label','provenance_row','record_origin','source_name','source_record_id','pmid','doi','evidence_subtype','association_evidence_class','association_evidence_strength_class','evidence_class','evidence_status','association_class','evidence_strength_class','action_type','mechanism_of_action','mapping_method','identity_resolution_status','inheritance','clinical_stage','trial_phase','trial_status','target_gene_count','target_genes','provenance_status','interpretation'];
 function evidenceRows(plan,opt){
  const rows=[];
  plan.collection.edges().forEach(e=>{
   const d=plan.edges.get(e.id()),a=plan.nodes.get(d.source),b=plan.nodes.get(d.target);
   const primary=Array.isArray(d.evidence_rows)&&d.evidence_rows.length,provenance=Array.isArray(d.provenance_rows)&&d.provenance_rows.length;
   const records=plan.evidenceInfo?window.ODDBEvidence.matchingRecords(d,plan.evidenceInfo.filters):(primary?d.evidence_rows:provenance?d.provenance_rows:[d]);
   records.forEach((r,i)=>{
    const source=(primary||provenance?(r.source_name??r.source):(d.source_name??d.evidence_sources))??'',sourceId=r.source_id??(!primary&&!provenance?d.evidence_source_ids:'')??'';
    const pmid=r.pmid??'',doi=r.doi??'';
    const row={figure_title:opt.title,scope:plan.scope,evidence_scope:plan.scope==='viewport'?'full_shown_network':plan.scope,exported_at:plan.exportedAt,validated_at:plan.metadata.validated_at,database_release:plan.metadata.release_id??'',database_release_status:plan.metadata.release_status??'unknown',active_evidence_filters:plan.evidenceInfo?JSON.stringify(plan.evidenceInfo.filters):'',evidence_filters_description:plan.evidenceInfo?.description||'',graph_checksum:plan.metadata.graph_checksum??'',relationship_id:d.id,relationship_type:d.type,relationship_label:EDGE_NAMES[d.type]||d.label||d.type,source_node_id:d.source,source_entity_id:a?.entity_id,source_entity_type:a?.type,source_label:a?.label,target_node_id:d.target,target_entity_id:b?.entity_id,target_entity_type:b?.type,target_label:b?.label,provenance_row:i+1,record_origin:primary?'primary_evidence':provenance?'association_provenance':'association_only',source_name:source,source_record_id:sourceId,pmid,doi,evidence_subtype:r.evidence_subtype??'',association_evidence_class:primary?(d.evidence_class??''):'',association_evidence_strength_class:primary?(d.evidence_strength_class??''):'',clinical_stage:d.clinical_stage??'',trial_phase:d.phase??'',trial_status:d.overall_status??'',target_gene_count:d.target_gene_count??'',target_genes:d.target_genes??'',provenance_status:[source,sourceId,pmid,doi].some(v=>String(v).trim())?'recorded':'not recorded',interpretation:d.warning??''};
    for(const key of ['evidence_class','evidence_status','association_class','evidence_strength_class','action_type','mechanism_of_action','mapping_method','identity_resolution_status','inheritance'])row[key]=r[key]??d[key]??'';
    rows.push(row);
   });
  });return rows;
 }
 function evidenceCSV(plan,opt){return '\ufeff'+[COLUMNS.map(csvCell).join(','),...evidenceRows(plan,opt).map(row=>COLUMNS.map(key=>csvCell(row[key])).join(','))].join('\r\n')+'\r\n';}
 function crc32(bytes){let crc=0xffffffff;for(const b of bytes){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
 async function pngDensity(blob,dpi=300){
  const bytes=new Uint8Array(await blob.arrayBuffer()),signature=[137,80,78,71,13,10,26,10];if(!signature.every((b,i)=>bytes[i]===b))throw new Error('The PNG encoder returned an invalid image.');
  const phys=new Uint8Array(21),view=new DataView(phys.buffer);view.setUint32(0,9);phys.set([112,72,89,115],4);view.setUint32(8,Math.round(dpi/0.0254));view.setUint32(12,Math.round(dpi/0.0254));phys[16]=1;view.setUint32(17,crc32(phys.subarray(4,17)));
  const parts=[bytes.subarray(0,8)];let offset=8,inserted=false;
  while(offset<bytes.length){if(offset+12>bytes.length)throw new Error('The PNG image is incomplete.');const len=new DataView(bytes.buffer,bytes.byteOffset+offset,4).getUint32(0),end=offset+len+12;if(end>bytes.length)throw new Error('The PNG image is incomplete.');const type=String.fromCharCode(...bytes.subarray(offset+4,offset+8));if(type!=='pHYs')parts.push(bytes.subarray(offset,end));if(type==='IHDR'){parts.push(phys);inserted=true;}offset=end;}
  if(!inserted)throw new Error('The PNG image has no dimensions.');return new Blob(parts,{type:'image/png'});
 }
 function status(message,error=false){get('publicationStatus').textContent=message;get('publicationStatus').classList.toggle('is-error',error);}
 function buttons(enabled){for(const id of ['publicationSVG','publicationPNG','publicationEvidence'])get(id).disabled=!enabled;}
 function clearPreview(){if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}get('publicationPreview').removeAttribute('src');get('publicationPreview').hidden=true;output=null;}
 function draw(){
  if(!plan)return;try{
   const opt=fromForm();if(opt.scope!==plan.scope)return;
   const next=compose(plan,opt);clearPreview();output=next;previewURL=URL.createObjectURL(new Blob([next.svg],{type:'image/svg+xml;charset=utf-8'}));get('publicationPreview').src=previewURL;get('publicationPreview').hidden=false;buttons(true);
   const pixelsW=Math.round(opt.width/25.4*300),pixelsH=Math.round(opt.height/25.4*300);get('publicationDimensions').textContent=`${opt.width} × ${opt.height} mm · PNG ${pixelsW} × ${pixelsH} px`;
   get('publicationPNG').disabled=busyPNG||pixelsW*pixelsH>32000000;get('publicationPNG').title=pixelsW*pixelsH>32000000?'PNG is limited to 32 megapixels. Reduce dimensions or download SVG.':'300 dpi raster figure';
   status(`${plan.collection.nodes().length} entities · ${plan.collection.edges().length} relationships · ${evidenceRows(plan,opt).length} evidence rows.${plan.issues.length?` ${plan.issues.length} unavailable item(s) omitted.`:''}${plan.evidenceExcluded?` ${plan.evidenceExcluded} relationship(s) excluded after filter revalidation.`:''}${plan.scope==='viewport'?' Viewport crop. CSV covers the full shown network.':''}${next.overlaps?` ${next.overlaps===1000?'1000+':next.overlaps} label overlap(s). Increase dimensions, hide labels or export a smaller subgraph.`:''}`);
  }catch(e){clearPreview();buttons(false);status(e.message,true);}
 }
 async function prepare(){
  const token=++serial;plan=null;buttons(false);clearPreview();get('publicationRetry').hidden=true;get('publicationIssues').hidden=true;status('Waiting for ODDB requests…');
  try{
   await window.ODDBAnalysis.idle();if(window.ODDBEvidence)await window.ODDBEvidence.refresh(true);await new Promise(r=>requestAnimationFrame(r));if(!dialog.open||token!==serial)return;
   const scope=get('publicationScope').value,collection=graphCollection(scope);status('Validating entities, relationships and source records…');
   const response=await window.ODDBAnalysis.request('session_validate.php',{}, {body:references(collection),label:'Preparing publication export',quiet:true,timeout:120000});
   if(!dialog.open||token!==serial)return;plan=validated(collection,response,scope);
   get('publicationIssueList').replaceChildren();get('publicationIssues').hidden=!plan.issues.length;
   for(const issue of plan.issues.slice(0,200)){const li=document.createElement('li');li.textContent=`${issue.kind} ${issue.id}: ${issue.status}. ${issue.reason}`;get('publicationIssueList').append(li);}
   if(plan.issues.length>200){const li=document.createElement('li');li.textContent='Additional issues are recorded in the SVG metadata.';get('publicationIssueList').append(li);}draw();
  }catch(e){if(token===serial&&dialog.open){status(e.message,true);get('publicationRetry').hidden=false;}}
 }
 async function open(){if(!dialog.open)dialog.showModal();await prepare();}
 async function downloadPNG(){
  if(!output||busyPNG)return;const current=output,token=serial;busyPNG=true;get('publicationPNG').disabled=true;status('Rendering the 300 dpi PNG…');
  let url=null,errorMessage=null;
  try{
   const width=Math.round(current.opt.width/25.4*300),height=Math.round(current.opt.height/25.4*300);if(width*height>32000000)throw new Error('This PNG exceeds the 32 megapixel export limit. Choose smaller dimensions or download SVG.');
   const image=new Image();url=URL.createObjectURL(new Blob([current.svg],{type:'image/svg+xml;charset=utf-8'}));
   await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('PNG rendering took too long. Download SVG or retry.')),20000);image.onload=()=>{clearTimeout(timer);resolve();};image.onerror=()=>{clearTimeout(timer);reject(new Error('The figure could not be rendered to PNG. Download SVG or retry.'));};image.src=url;});
   const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('PNG export is not supported by this browser.');ctx.drawImage(image,0,0,width,height);
   const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('The browser could not encode this PNG.')),'image/png'));
   const png=await pngDensity(blob);if(token===serial&&dialog.open)downloadBlob(png,`oddb-publication-${current.opt.scope}-300dpi.png`);
  }catch(e){errorMessage=e.message;}finally{if(url)URL.revokeObjectURL(url);busyPNG=false;if(token===serial&&dialog.open){draw();if(errorMessage)status(errorMessage,true);}}
 }
 function init(){
  dialog=get('publicationDialog');if(!dialog)return;
  get('publicationOpen').onclick=open;get('publicationClose').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{serial++;plan=null;clearTimeout(timer);clearPreview();});
  get('publicationForm').onsubmit=e=>e.preventDefault();get('publicationScope').onchange=prepare;get('publicationRetry').onclick=prepare;
  get('publicationPreset').onchange=()=>{const preset=get('publicationPreset').value;if(preset==='single'){get('publicationWidth').value=85;get('publicationHeight').value=230;}if(preset==='double'){get('publicationWidth').value=180;get('publicationHeight').value=180;}draw();};
  for(const id of ['publicationWidth','publicationHeight','publicationFigureTitle','publicationLabelSize','publicationFont','publicationLabels','publicationLegend','publicationMetadata','publicationTransparent'])get(id).addEventListener('input',()=>{if(id==='publicationWidth'||id==='publicationHeight')get('publicationPreset').value='custom';clearTimeout(timer);output=null;buttons(false);status('Updating preview…');timer=setTimeout(draw,90);});
  get('publicationSVG').onclick=()=>{if(output)downloadBlob(new Blob([output.svg],{type:'image/svg+xml;charset=utf-8'}),`oddb-publication-${output.opt.scope}.svg`);};
  get('publicationEvidence').onclick=()=>{if(plan&&output)downloadBlob(new Blob([evidenceCSV(plan,output.opt)],{type:'text/csv;charset=utf-8'}),`oddb-publication-${plan.scope}-evidence.csv`);};
  get('publicationPNG').onclick=downloadPNG;
 }
 window.ODDBPublication={settings,graphCollection,validated,compose,evidenceRows,evidenceCSV,pngDensity};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
