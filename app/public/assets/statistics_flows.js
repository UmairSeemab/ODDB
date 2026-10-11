(() => {
'use strict';

const FLOW_API = 'api/flows.php';
const flowState = {
  type: 'disease',
  limit: window.innerWidth < 768 ? '25' : '40',
  cache: new Map(),
  chart: null
};

const flowTypes = {
  disease: {
    label: 'Disease flow',
    icon: 'D'
  },
  gene: {
    label: 'Gene flow',
    icon: 'G'
  },
  variant: {
    label: 'Variant flow',
    icon: 'V'
  },
  therapeutic: {
    label: 'Therapeutic flow',
    icon: 'Rx'
  }
};

const escFlow = s => String(s ?? '')
  .replaceAll('&','&amp;')
  .replaceAll('<','&lt;')
  .replaceAll('>','&gt;')
  .replaceAll('"','&quot;')
  .replaceAll("'","&#039;");

const fmtFlow = n => Number(n || 0).toLocaleString();

function flowCacheKey(type, limit) {
  return `${type}|${limit}`;
}

async function fetchFlow(type, limit) {
  const key = flowCacheKey(type, limit);
  if (flowState.cache.has(key)) return flowState.cache.get(key);

  const qs = new URLSearchParams({type, limit});
  const r = await fetch(`${FLOW_API}?${qs}`);
  const d = await r.json();

  if (!r.ok || d.ok === false) {
    throw new Error(d.error || `HTTP ${r.status}`);
  }

  flowState.cache.set(key, d);
  return d;
}

function layerColor(layer) {
  const map = {
    'Anatomy category': '#7c3aed',
    'Disease': '#5b6fc9',
    'Inheritance category': '#059669',
    'Gene / locus category': '#0284c7',
    'Variant consequence': '#d97706',
    'Drug evidence class': '#dc5a76'
  };
  return map[layer] || '#64748b';
}

function nodeLabelFormatter(params) {
  return params.data.label || params.data.full_label || params.name;
}

function flowTooltip(params, payload) {
  if (params.dataType === 'edge') {
    const source = payload.node_lookup[params.data.source];
    const target = payload.node_lookup[params.data.target];
    return `
      <div class="flow-tooltip">
        <strong>${escFlow(source?.full_label || params.data.source)}</strong>
        <div class="flow-tooltip-arrow">→</div>
        <strong>${escFlow(target?.full_label || params.data.target)}</strong>
        <hr>
        <strong>${fmtFlow(params.data.value)}</strong> ${escFlow(payload.meta.unit)}
      </div>`;
  }

  const d = params.data;
  return `
    <div class="flow-tooltip">
      <strong>${escFlow(d.full_label || d.label || d.name)}</strong>
      <div class="small">${escFlow(d.layer || '')}</div>
    </div>`;
}

function preparePayload(payload) {
  payload.node_lookup = {};
  payload.nodes.forEach(n => payload.node_lookup[n.name] = n);
  return payload;
}

function sankeyOption(payload) {
  const nodes = payload.nodes.map(n => ({
    ...n,
    itemStyle: {
      color: layerColor(n.layer),
      borderColor: '#ffffff',
      borderWidth: 1
    }
  }));

  return {
    animationDuration: 350,
    aria: {enabled: true},
    tooltip: {
      trigger: 'item',
      confine: true,
      appendToBody: false,
      formatter: p => flowTooltip(p, payload)
    },
    series: [{
      type: 'sankey',
      left: 18,
      right: 18,
      top: 18,
      bottom: 18,
      nodeWidth: window.innerWidth < 768 ? 16 : 20,
      nodeGap: window.innerWidth < 768 ? 8 : 10,
      nodeAlign: 'justify',
      draggable: false,
      emphasis: {focus: 'adjacency'},
      label: {
        color: '#334155',
        fontSize: window.innerWidth < 768 ? 9 : 11,
        formatter: nodeLabelFormatter
      },
      lineStyle: {
        color: 'gradient',
        opacity: 0.30,
        curveness: 0.48
      },
      data: nodes,
      links: payload.links
    }]
  };
}

function setFlowHeight(payload) {
  const diseaseNodes = payload.nodes.filter(n => n.layer === 'Disease').length;
  const height = Math.max(
    560,
    Math.min(980, 300 + diseaseNodes * (window.innerWidth < 768 ? 15 : 13))
  );
  const inner = document.getElementById('knowledgeFlowChartInner');
  inner.style.height = `${height}px`;
}

function summaryHtml(payload) {
  const m = payload.meta;
  const therapeutic = payload.type === 'therapeutic';

  const chips = [
    ['Canonical diseases', m.canonical_diseases],
    ['Diseases represented in full flow', m.diseases_with_paths],
    ['Diseases shown', m.disease_nodes_shown],
    [therapeutic ? 'Disease–drug pairs shown' : 'Flow units shown', m.visible_path_units],
    [therapeutic ? 'Disease–drug pairs in full flow' : 'Flow units in full flow', m.total_path_units],
    ['Sankey links shown', m.sankey_links]
  ];

  if (payload.type === 'variant') {
    chips.push([
      'Consequence categories represented',
      `${m.represented_consequence_categories}/${m.all_consequence_categories}`
    ]);
  }

  if (therapeutic) {
    chips.push([
      'Diseases without linked drug evidence',
      Number(m.diseases_without_linked_drug_evidence || 0)
    ]);
  }

  return chips.map(([label,value]) => `
    <div class="flow-summary-chip">
      <strong>${typeof value === 'number' ? fmtFlow(value) : escFlow(value)}</strong>
      <span>${escFlow(label)}</span>
    </div>`).join('');
}

function setLoading() {
  document.getElementById('knowledgeFlowTitle').textContent = 'Loading flow…';
  document.getElementById('knowledgeFlowSubtitle').textContent = '';
  document.getElementById('knowledgeFlowNote').classList.add('d-none');
  document.getElementById('knowledgeFlowSummary').innerHTML =
    '<div class="flow-loading">Loading ODDB relationships…</div>';
}

function setError(err) {
  document.getElementById('knowledgeFlowSummary').innerHTML =
    `<div class="alert alert-danger mb-0">Could not load the knowledge flow: ${escFlow(err.message)}</div>`;
}

async function renderFlow() {
  setLoading();

  try {
    const payload = preparePayload(await fetchFlow(flowState.type, flowState.limit));

    document.getElementById('knowledgeFlowTitle').textContent = payload.title;
    document.getElementById('knowledgeFlowSubtitle').textContent = payload.subtitle;

    const shown=Number(payload.meta.disease_nodes_shown||0);
    const represented=Number(payload.meta.diseases_with_paths||0);
    const allSelected=String(payload.meta.disease_limit)==='all';
    const selection=document.getElementById('knowledgeFlowSelection');
    selection.innerHTML=allSelected
      ? `<strong>Showing all ${fmtFlow(represented)} diseases represented in this flow.</strong> ${escFlow(payload.ranking||'')}`
      : `<strong>Showing ${fmtFlow(shown)} of ${fmtFlow(represented)} diseases represented in this flow.</strong> ${escFlow(payload.ranking||'')} Diseases outside the selected view are excluded rather than collapsed into an “other diseases” node.`;

    const note = document.getElementById('knowledgeFlowNote');
    note.textContent = payload.note || '';
    note.classList.toggle('d-none', !payload.note);

    document.getElementById('knowledgeFlowSummary').innerHTML = summaryHtml(payload);

    setFlowHeight(payload);

    const el = document.getElementById('knowledgeFlowChartInner');
    if (!flowState.chart) {
      flowState.chart = echarts.init(el, null, {renderer:'canvas'});
      flowState.chart.on('click', params => {
        if (params.dataType !== 'node') return;
        const url = params.data.url;
        if (url) window.location.href = url;
      });
    } else {
      flowState.chart.resize();
      flowState.chart.clear();
    }

    flowState.chart.setOption(sankeyOption(payload), true);

    document.querySelectorAll('[data-flow-type]').forEach(btn => {
      const active = btn.dataset.flowType === flowState.type;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });

  } catch (err) {
    setError(err);
  }
}

function bindFlowControls() {
  document.querySelectorAll('[data-flow-type]').forEach(btn => {
    btn.addEventListener('click', () => {
      flowState.type = btn.dataset.flowType;
      renderFlow();
    });
  });

  const limit = document.getElementById('knowledgeFlowLimit');
  limit.value = flowState.limit;
  limit.addEventListener('change', () => {
    flowState.limit = limit.value;
    renderFlow();
  });

  document.getElementById('knowledgeFlowReset').addEventListener('click', () => {
    if (flowState.chart) {
      flowState.chart.dispatchAction({type:'restore'});
      flowState.chart.resize();
    }
  });

  document.getElementById('knowledgeFlowPrev').addEventListener('click', () => {
    const keys = Object.keys(flowTypes);
    const i = keys.indexOf(flowState.type);
    flowState.type = keys[(i - 1 + keys.length) % keys.length];
    renderFlow();
  });

  document.getElementById('knowledgeFlowNext').addEventListener('click', () => {
    const keys = Object.keys(flowTypes);
    const i = keys.indexOf(flowState.type);
    flowState.type = keys[(i + 1) % keys.length];
    renderFlow();
  });
}

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (flowState.chart) flowState.chart.resize();
  }, 150);
});

document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('knowledgeFlowChartInner')) return;
  bindFlowControls();
  renderFlow();
});

})();
