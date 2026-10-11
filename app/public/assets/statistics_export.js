(() => {
'use strict';

/*
 * ODDB Statistics export system v0.4.5c
 * --------------------------------------
 * Fixes:
 *  1. One correctly aligned Export control per visualization.
 *  2. Cards containing multiple charts receive a local toolbar per chart.
 *  3. PNG/SVG are re-rendered off-screen in a publication-friendly layout
 *     rather than simply enlarging the on-screen responsive canvas.
 *  4. Pie/donut exports contain the full currently-visible category list.
 *  5. Treemap exports contain a side table so small categories are not lost.
 *  6. Current legend selections and current Sankey/relationship-map state
 *     are preserved.
 */

const CHARTS = [
  {id:'anatomyDonut',             file:'oddb-anatomy-distribution',               local:'Anatomy distribution'},
  {id:'inheritanceDonut',         file:'oddb-inheritance-distribution',           local:'Inheritance memberships'},
  {id:'inheritanceCoverageDonut', file:'oddb-inheritance-coverage',               local:'Inheritance classification coverage'},
  {id:'geneTreemap',              file:'oddb-gene-locus-categories',              local:'Gene / locus categories'},
  {id:'variantTreemap',           file:'oddb-variant-consequence-annotations',    local:'Variant consequences'},
  {id:'drugStageDonut',           file:'oddb-drug-development-stage',             local:'Drug development stage'},
  {id:'therapeuticSankey',        file:'oddb-therapeutic-evidence-flow',          local:'Disease–drug relationship space'},
  {id:'trialEvidenceOrbit',       file:'oddb-clinical-trials-relationship-profile',local:'Clinical trials'},
  {id:'reportEvidenceOrbit',      file:'oddb-clinical-reports-relationship-profile',local:'Clinical reports'},
  {id:'relationshipRing',         file:'oddb-relationship-map',                   local:'Relationship map'},
  {id:'knowledgeFlowChartInner',  file:'oddb-knowledge-flow',                     local:'Knowledge flow'}
];

const FALLBACK_COLORS = [
  '#5470c6','#91cc75','#fac858','#ee6666','#73c0de','#3ba272',
  '#fc8452','#9a60b4','#ea7ccc','#2f4554','#61a0a8','#d48265',
  '#749f83','#ca8622','#bda29a','#6e7074','#546570','#c4ccd3'
];

const byId = id => document.getElementById(id);

const safeFile = value => String(value ?? 'oddb-chart')
  .normalize('NFKD')
  .replace(/[^\w\-]+/g, '-')
  .replace(/-+/g, '-')
  .replace(/^-|-$/g, '')
  .toLowerCase()
  .slice(0, 120) || 'oddb-chart';

const csvEscape = value => {
  const s = String(value ?? '');
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"','""')}"` : s;
};

function configFor(id) {
  return CHARTS.find(c => c.id === id);
}

function instanceFor(id) {
  const el = byId(id);
  if (!el || typeof echarts === 'undefined') return null;
  return echarts.getInstanceByDom(el);
}

function cardFor(id) {
  return byId(id)?.closest('.viz-card, .clinical-profile-card, .knowledge-flow-card, article') || null;
}

function visibleTitle(id) {
  if (id === 'relationshipRing') {
    return byId('relationshipTitle')?.textContent?.trim()
      || configFor(id)?.local
      || 'ODDB relationship map';
  }

  if (id === 'knowledgeFlowChartInner') {
    return byId('knowledgeFlowTitle')?.textContent?.trim()
      || configFor(id)?.local
      || 'ODDB knowledge flow';
  }

  const card = cardFor(id);
  return card?.querySelector('.viz-head h3, .knowledge-flow-head h3, h3')?.textContent?.trim()
    || configFor(id)?.local
    || id;
}

function visibleSubtitle(id) {
  if (id === 'knowledgeFlowChartInner') {
    return byId('knowledgeFlowSubtitle')?.textContent?.trim() || '';
  }

  const card = cardFor(id);
  return card?.querySelector('.viz-head .small.text-secondary, .small.text-secondary')?.textContent?.trim()
    || '';
}

function filenameFor(id, ext) {
  const dynamic = (id === 'relationshipRing' || id === 'knowledgeFlowChartInner')
    ? safeFile(visibleTitle(id))
    : configFor(id)?.file;
  return `${dynamic || safeFile(visibleTitle(id))}.${ext}`;
}

function legendState(option) {
  const selected = {};
  (option.legend || []).forEach(legend => {
    Object.entries(legend?.selected || {}).forEach(([name, state]) => {
      selected[name] = state !== false;
    });
  });
  return selected;
}

function isSelected(name, selected) {
  return selected[name] !== false;
}

function nodeLabel(node) {
  return node?.full_label
    || node?.fullLabel
    || node?.full
    || node?.display
    || node?.label
    || node?.name
    || '';
}

function nodeMap(data=[]) {
  const map = new Map();
  data.forEach(node => {
    if (node?.name !== undefined) map.set(String(node.name), nodeLabel(node));
  });
  return map;
}

/* ------------------------------------------------------------------
 * CSV
 * ------------------------------------------------------------------ */

function pieRows(series, selected) {
  return (series.data || [])
    .filter(item => isSelected(item?.name ?? '', selected))
    .map(item => ({
      category:item?.name ?? '',
      value:item?.value ?? ''
    }));
}

function treemapRows(series) {
  const rows = [];

  const walk = (items, parent='') => {
    (items || []).forEach(item => {
      const raw = Array.isArray(item?.value) ? item.value[0] : item?.value;

      if (Number(raw ?? 0) > 0) {
        rows.push({
          parent,
          category:item?.name ?? '',
          value:raw
        });
      }

      if (item?.children?.length) {
        walk(item.children, item?.name ?? parent);
      }
    });
  };

  walk(series.data || []);
  return rows;
}

function graphRows(series) {
  const names = nodeMap(series.data || []);
  const links = series.links || series.edges || [];

  return links.map(link => ({
    source:link?.left_full || names.get(String(link?.source)) || link?.source || '',
    target:link?.right_full || names.get(String(link?.target)) || link?.target || '',
    value:link?.value ?? '',
    source_id:link?.source ?? '',
    target_id:link?.target ?? ''
  }));
}

function graphNodes(series) {
  return (series.data || []).map(node => ({
    node:nodeLabel(node),
    value:Array.isArray(node?.value) ? node.value[0] : (node?.value ?? ''),
    layer:node?.layer ?? node?.category ?? '',
    id:node?.ref_id ?? node?.name ?? ''
  }));
}

function cartesianRows(option, selected) {
  const xData = option?.xAxis?.[0]?.data || [];
  const visibleSeries = (option.series || []).filter(series =>
    isSelected(series?.name ?? '', selected)
  );

  return xData.map((x, i) => {
    const row = {category:x};

    visibleSeries.forEach((series, idx) => {
      const key = series?.name || `series_${idx+1}`;
      const raw = series?.data?.[i];

      row[key] = (raw && typeof raw === 'object')
        ? (raw.value ?? '')
        : (raw ?? '');
    });

    return row;
  });
}

function extractCsv(instance) {
  const option = instance.getOption();
  const selected = legendState(option);
  const primary = option?.series?.[0];

  if (!primary) return {rows:[], nodes:[], kind:'empty'};

  if (primary.type === 'pie') {
    return {rows:pieRows(primary, selected), nodes:[], kind:'pie'};
  }

  if (primary.type === 'treemap') {
    return {rows:treemapRows(primary), nodes:[], kind:'treemap'};
  }

  if (primary.type === 'sankey' || primary.type === 'graph') {
    return {
      rows:graphRows(primary),
      nodes:graphNodes(primary),
      kind:primary.type
    };
  }

  if (primary.type === 'bar' || primary.type === 'line') {
    return {
      rows:cartesianRows(option, selected),
      nodes:[],
      kind:primary.type
    };
  }

  return {
    rows:(primary.data || []).map((item, i) => ({
      index:i+1,
      category:item?.name ?? '',
      value:item?.value ?? item ?? ''
    })),
    nodes:[],
    kind:primary.type || 'generic'
  };
}

function rowsToCsv(rows) {
  if (!rows.length) return '';

  const headers = [];
  rows.forEach(row => {
    Object.keys(row).forEach(key => {
      if (!headers.includes(key)) headers.push(key);
    });
  });

  return [
    headers.map(csvEscape).join(','),
    ...rows.map(row => headers.map(h => csvEscape(row[h] ?? '')).join(','))
  ].join('\r\n');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');

  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();

  setTimeout(() => URL.revokeObjectURL(url), 1200);
}

function exportCsv(id) {
  const chart = instanceFor(id);

  if (!chart) {
    alert('This chart has not finished loading yet.');
    return;
  }

  const {rows, nodes, kind} = extractCsv(chart);

  if (!rows.length && !nodes.length) {
    alert('There is no currently visible chart data to export.');
    return;
  }

  let csv = rowsToCsv(rows);

  if (nodes.length && (kind === 'sankey' || kind === 'graph')) {
    csv += '\r\n\r\nNODE TABLE\r\n';
    csv += rowsToCsv(nodes);
  }

  downloadBlob(
    new Blob(['\ufeff', csv], {type:'text/csv;charset=utf-8'}),
    filenameFor(id, 'csv')
  );
}

/* ------------------------------------------------------------------
 * Publication-style PNG / SVG rendering
 * ------------------------------------------------------------------ */

function cloneOption(option) {
  if (echarts?.util?.clone) return echarts.util.clone(option);

  /*
   * Fallback is only used on ECharts distributions that do not expose
   * util.clone. Standard ODDB ECharts currently exposes it.
   */
  return JSON.parse(JSON.stringify(option));
}

function exportDimensions(type, id) {
  if (type === 'treemap') return {width:1900, height:1100};
  if (type === 'sankey') return {width:2100, height:1250};
  if (type === 'graph') return {width:1900, height:1250};
  if (type === 'pie') return {width:1800, height:1050};
  if (type === 'bar' || type === 'line') return {width:1900, height:1050};
  return {width:1800, height:1050};
}

function paletteFor(option) {
  const colors = Array.isArray(option.color) && option.color.length
    ? option.color
    : FALLBACK_COLORS;

  return colors;
}

function colorForItem(item, index, option) {
  return item?.itemStyle?.color
    || paletteFor(option)[index % paletteFor(option).length]
    || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

function chartUnit(id) {
  const map = {
    anatomyDonut:'Diseases',
    inheritanceDonut:'Memberships',
    inheritanceCoverageDonut:'Diseases',
    drugStageDonut:'Drugs'
  };
  return map[id] || 'Records';
}

function cleanBaseOption(option, id) {
  const out = cloneOption(option);

  out.animation = false;
  out.backgroundColor = '#ffffff';

  out.tooltip = {
    ...(out.tooltip || {}),
    show:false
  };

  out.toolbox = {show:false};

  /*
   * Export title/subtitle are placed inside the image itself, making the
   * downloaded figure self-explanatory outside ODDB.
   */
  out.title = [{
    text:visibleTitle(id),
    subtext:visibleSubtitle(id),
    left:42,
    top:26,
    textStyle:{
      color:'#172033',
      fontSize:30,
      fontWeight:700
    },
    subtextStyle:{
      color:'#64748b',
      fontSize:17,
      lineHeight:24
    },
    itemGap:8
  }];

  return out;
}

function selectedPieData(option, series) {
  const selected = legendState(option);
  return (series.data || []).filter(item =>
    isSelected(item?.name ?? '', selected)
  );
}

function pieGraphics(option, data, width, height, id) {
  const total = data.reduce((sum, item) => sum + Number(item?.value || 0), 0);
  const centerX = Math.round(width * 0.34);
  const centerY = Math.round(height * 0.54);
  const listX = Math.round(width * 0.66);
  const listTop = 145;
  const usable = height - listTop - 95;
  const rowH = Math.min(42, Math.max(27, Math.floor(usable / Math.max(data.length, 1))));
  const fontSize = rowH < 32 ? 15 : 18;

  const graphics = [
    {
      type:'text',
      silent:true,
      left:centerX,
      top:centerY,
      style:{
        text:`${total.toLocaleString()}\n${chartUnit(id)}`,
        textAlign:'center',
        textVerticalAlign:'middle',
        fill:'#172033',
        font:`700 28px sans-serif`,
        lineHeight:38
      }
    },
    {
      type:'text',
      silent:true,
      left:listX,
      top:105,
      style:{
        text:'Visible categories',
        fill:'#334155',
        font:'700 18px sans-serif'
      }
    }
  ];

  data.forEach((item, index) => {
    const y = listTop + index * rowH;
    const color = colorForItem(item, index, option);

    graphics.push({
      type:'rect',
      silent:true,
      shape:{x:listX, y, width:18, height:18, r:3},
      style:{fill:color}
    });

    graphics.push({
      type:'text',
      silent:true,
      left:listX + 30,
      top:y - 1,
      style:{
        text:`${item?.name ?? ''}   ${Number(item?.value || 0).toLocaleString()}`,
        fill:'#334155',
        font:`${fontSize}px sans-serif`
      }
    });
  });

  return graphics;
}

function optimizePie(option, id, dims) {
  const series = option.series?.[0];
  if (!series) return option;

  const data = selectedPieData(option, series);

  series.data = data;
  series.center = ['34%','54%'];
  series.radius = ['27%','51%'];
  series.avoidLabelOverlap = true;

  /*
   * The custom side key includes every visible category and value.
   * This removes ECharts' paginated on-screen legend from the exported image.
   */
  option.legend = [{show:false}];
  option.graphic = pieGraphics(option, data, dims.width, dims.height, id);

  return option;
}

function flattenTreemap(items, parent='', rows=[]) {
  (items || []).forEach(item => {
    const raw = Array.isArray(item?.value) ? item.value[0] : item?.value;

    if (Number(raw ?? 0) > 0) {
      rows.push({
        name:item?.name ?? '',
        value:Number(raw || 0),
        parent,
        item
      });
    }

    if (item?.children?.length) {
      flattenTreemap(item.children, item?.name ?? parent, rows);
    }
  });

  return rows;
}

function optimizeTreemap(option, id, dims) {
  const series = option.series?.[0];
  if (!series) return option;

  const rows = flattenTreemap(series.data || [])
    .sort((a,b) => b.value - a.value);

  /*
   * Reserve the right third for a complete category/value list.
   * Tiny treemap rectangles may not have room for text, but their values
   * are therefore never lost in the downloaded figure.
   */
  series.left = 42;
  series.top = 112;
  series.right = '35%';
  series.bottom = 55;

  series.label = {
    ...(series.label || {}),
    show:true,
    fontSize:20,
    lineHeight:25,
    overflow:'truncate'
  };

  series.upperLabel = {
    ...(series.upperLabel || {}),
    show:true,
    fontSize:18,
    height:28
  };

  const listX = Math.round(dims.width * 0.69);
  const listTop = 120;
  const usable = dims.height - listTop - 75;
  const rowH = Math.min(39, Math.max(26, Math.floor(usable / Math.max(rows.length, 1))));
  const fontSize = rowH < 31 ? 14 : 17;

  const graphics = [{
    type:'text',
    silent:true,
    left:listX,
    top:82,
    style:{
      text:'Category counts',
      fill:'#334155',
      font:'700 18px sans-serif'
    }
  }];

  rows.forEach((row, index) => {
    const y = listTop + index * rowH;
    const color = colorForItem(row.item, index, option);

    graphics.push({
      type:'rect',
      silent:true,
      shape:{x:listX, y, width:17, height:17, r:2},
      style:{fill:color}
    });

    graphics.push({
      type:'text',
      silent:true,
      left:listX + 28,
      top:y - 1,
      style:{
        text:`${row.name}   ${row.value.toLocaleString()}`,
        fill:'#334155',
        font:`${fontSize}px sans-serif`
      }
    });
  });

  option.graphic = graphics;
  option.legend = [{show:false}];

  return option;
}

function optimizeSankey(option) {
  const series = option.series?.[0];
  if (!series) return option;

  series.left = 80;
  series.right = 80;
  series.top = 120;
  series.bottom = 60;
  series.nodeWidth = 24;
  series.nodeGap = Math.max(10, Number(series.nodeGap || 10));

  series.label = {
    ...(series.label || {}),
    show:true,
    fontSize:16,
    color:'#334155'
  };

  series.lineStyle = {
    ...(series.lineStyle || {}),
    opacity:0.38
  };

  option.legend = [{show:false}];

  return option;
}

function optimizeGraph(option) {
  const series = option.series?.[0];
  if (!series) return option;

  series.top = 115;
  series.bottom = 55;
  series.left = 60;
  series.right = 60;

  series.label = {
    ...(series.label || {}),
    show:true,
    fontSize:16,
    lineHeight:20
  };

  series.edgeLabel = {
    ...(series.edgeLabel || {}),
    fontSize:13
  };

  option.legend = (option.legend || []).map(legend => ({
    ...legend,
    type:'plain',
    textStyle:{...(legend.textStyle || {}), fontSize:15}
  }));

  return option;
}

function optimizeCartesian(option) {
  option.grid = (option.grid || []).map(grid => ({
    ...grid,
    left:100,
    right:55,
    top:125,
    bottom:100,
    containLabel:true
  }));

  option.legend = (option.legend || []).map(legend => ({
    ...legend,
    type:'plain',
    bottom:24,
    left:'center',
    textStyle:{...(legend.textStyle || {}), fontSize:16}
  }));

  (option.xAxis || []).forEach(axis => {
    axis.axisLabel = {
      ...(axis.axisLabel || {}),
      fontSize:15
    };
  });

  (option.yAxis || []).forEach(axis => {
    axis.axisLabel = {
      ...(axis.axisLabel || {}),
      fontSize:15
    };
  });

  return option;
}

function makeExportOption(id, chart) {
  const original = chart.getOption();
  const primaryType = original?.series?.[0]?.type || 'generic';
  const dims = exportDimensions(primaryType, id);

  let option = cleanBaseOption(original, id);

  if (primaryType === 'pie') option = optimizePie(option, id, dims);
  else if (primaryType === 'treemap') option = optimizeTreemap(option, id, dims);
  else if (primaryType === 'sankey') option = optimizeSankey(option);
  else if (primaryType === 'graph') option = optimizeGraph(option);
  else if (primaryType === 'bar' || primaryType === 'line') option = optimizeCartesian(option);

  return {option, dims, type:primaryType};
}

function makeOffscreenHost(width, height) {
  const holder = document.createElement('div');

  holder.style.cssText = [
    'position:fixed',
    'left:-100000px',
    'top:0',
    `width:${width}px`,
    `height:${height}px`,
    'background:#fff',
    'pointer-events:none',
    'opacity:0'
  ].join(';');

  document.body.appendChild(holder);
  return holder;
}

function renderOptimized(id, renderer, callback) {
  const source = instanceFor(id);

  if (!source) {
    alert('This chart has not finished loading yet.');
    return;
  }

  const {option, dims} = makeExportOption(id, source);
  const holder = makeOffscreenHost(dims.width, dims.height);

  let temp = null;

  try {
    temp = echarts.init(holder, null, {
      renderer,
      width:dims.width,
      height:dims.height
    });

    temp.setOption(option, true);
    temp.resize({width:dims.width, height:dims.height});

    callback(temp, holder, dims);
  } catch (err) {
    console.error('ODDB image export failed:', err);
    alert('The image could not be exported in this browser.');
  } finally {
    try {
      temp?.dispose();
    } catch (_) {}
    holder.remove();
  }
}

function exportPng(id) {
  renderOptimized(id, 'canvas', temp => {
    const dataUrl = temp.getDataURL({
      type:'png',
      pixelRatio:1.5,
      backgroundColor:'#ffffff',
      excludeComponents:['toolbox']
    });

    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filenameFor(id, 'png');
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}

function exportSvg(id) {
  renderOptimized(id, 'svg', (temp, holder) => {
    const svgEl = holder.querySelector('svg');

    if (!svgEl) {
      throw new Error('SVG element not found.');
    }

    let svg = svgEl.outerHTML;

    if (!svg.includes('xmlns=')) {
      svg = svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');
    }

    svg = `<?xml version="1.0" encoding="UTF-8"?>\n${svg}`;

    downloadBlob(
      new Blob([svg], {type:'image/svg+xml;charset=utf-8'}),
      filenameFor(id, 'svg')
    );
  });
}

function exportChart(id, format) {
  if (format === 'csv') return exportCsv(id);
  if (format === 'png') return exportPng(id);
  if (format === 'svg') return exportSvg(id);
}

/* ------------------------------------------------------------------
 * Controls / alignment
 * ------------------------------------------------------------------ */

function closeMenus(except=null) {
  document.querySelectorAll('.oddb-export-menu.open').forEach(menu => {
    if (menu === except) return;

    menu.classList.remove('open');
    menu.querySelector('.oddb-export-toggle')
      ?.setAttribute('aria-expanded','false');
  });
}

function buildMenu(id) {
  const wrap = document.createElement('div');
  wrap.className = 'oddb-export-menu';
  wrap.dataset.exportFor = id;

  wrap.innerHTML = `
    <button type="button"
            class="oddb-export-toggle"
            aria-haspopup="menu"
            aria-expanded="false"
            title="Export this visualization">
      <span aria-hidden="true">⇩</span>
      <span>Export</span>
      <span class="oddb-export-chevron" aria-hidden="true">▾</span>
    </button>

    <div class="oddb-export-dropdown" role="menu">
      <button type="button" role="menuitem" data-export-format="csv">
        <span class="oddb-export-ext">CSV</span>
        <span>Visible data</span>
      </button>
      <button type="button" role="menuitem" data-export-format="png">
        <span class="oddb-export-ext">PNG</span>
        <span>Optimized figure</span>
      </button>
      <button type="button" role="menuitem" data-export-format="svg">
        <span class="oddb-export-ext">SVG</span>
        <span>Vector figure</span>
      </button>
    </div>
  `;

  const toggle = wrap.querySelector('.oddb-export-toggle');

  toggle.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();

    const opening = !wrap.classList.contains('open');

    closeMenus(wrap);
    wrap.classList.toggle('open', opening);
    toggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
  });

  wrap.querySelectorAll('[data-export-format]').forEach(button => {
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();

      wrap.classList.remove('open');
      toggle.setAttribute('aria-expanded','false');
      exportChart(id, button.dataset.exportFormat);
    });
  });

  return wrap;
}

function chartElementsInside(card) {
  if (!card) return [];

  return CHARTS
    .map(c => byId(c.id))
    .filter(el => el && card.contains(el));
}

function cardHeader(card) {
  return card?.querySelector('.viz-head')
    || card?.querySelector('.knowledge-flow-head')
    || null;
}

function addLocalToolbar(config, chartEl) {
  const row = document.createElement('div');
  row.className = 'oddb-subchart-export-row';

  const label = document.createElement('div');
  label.className = 'oddb-subchart-export-label';
  label.textContent = config.local;

  row.appendChild(label);
  row.appendChild(buildMenu(config.id));

  chartEl.parentNode.insertBefore(row, chartEl);
}

function installOne(config) {
  const chartEl = byId(config.id);

  if (!chartEl || chartEl.dataset.exportMenuReady === '1') return;

  const card = cardFor(config.id);
  if (!card) return;

  chartEl.dataset.exportMenuReady = '1';

  /*
   * Clean controls from the previous exporter if present.
   */
  card.querySelectorAll(
    `.oddb-export-menu[data-export-for="${config.id}"], .oddb-subchart-export-row[data-export-for="${config.id}"]`
  ).forEach(el => el.remove());

  const chartsInCard = chartElementsInside(card);

  if (chartsInCard.length === 1) {
    const header = cardHeader(card);

    if (header) {
      header.classList.add('oddb-export-header');
      header.appendChild(buildMenu(config.id));
      return;
    }
  }

  /*
   * A card with >1 visualization (e.g. Inheritance evidence) gets one
   * compact local row immediately above each chart. No controls compete
   * for the same card-level header.
   */
  addLocalToolbar(config, chartEl);
}

function installAll() {
  /*
   * Remove v0.4.5b controls before rebuilding the aligned layout.
   * This also makes delayed installation passes idempotent.
   */
  document.querySelectorAll('.oddb-export-menu, .oddb-subchart-export-row')
    .forEach(el => el.remove());

  CHARTS.forEach(c => {
    const el = byId(c.id);
    if (el) delete el.dataset.exportMenuReady;
  });

  CHARTS.forEach(installOne);
}

document.addEventListener('click', event => {
  if (!event.target.closest('.oddb-export-menu')) closeMenus();
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeMenus();
});

document.addEventListener('DOMContentLoaded', () => {
  installAll();

  /*
   * One delayed rebuild handles chart areas created/settled after API data.
   */
  setTimeout(installAll, 1200);
});

})();
