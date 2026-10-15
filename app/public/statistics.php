<?php declare(strict_types=1); ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="Interactive ODDB v1 statistics for ocular diseases, genes, variants, therapeutics and clinical evidence.">
<title>Statistics — ODDB v1</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/statistics.css" rel="stylesheet">
<link href="assets/statistics_enhanced.css?v=3" rel="stylesheet">
<link href="assets/statistics_publication_export.css?v=1" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
</head>
<body class="oddb-visual oddb-statistics">
<?php require __DIR__ . "/partials/site_nav.php"; ?>

<header class="page-hero">
 <div class="container py-4 py-md-5">
  <div class="row align-items-end g-3">
   <div class="col-lg-8">
    <div class="eyebrow">ODDB v1</div>
    <h1 class="display-5 fw-bold mb-2">Database statistics</h1>
    <p class="lead text-secondary mb-0">
     Interactive views of the current disease, genetics, variant, therapeutic and clinical evidence layers.
    </p>
   </div>
   <div class="col-lg-4 text-lg-end">
    <div class="small text-secondary">Statistics from the ODDB v1 enrichment candidate (2026-10-15).</div>
   </div>
  </div>
 </div>
</header>

<main class="pb-5">
 <section class="container mt-4">
  <div id="overviewGrid" class="overview-grid">
   <div class="overview-card skeleton"></div>
   <div class="overview-card skeleton"></div>
   <div class="overview-card skeleton"></div>
   <div class="overview-card skeleton"></div>
  </div>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Disease landscape</div>
   <h2 class="h3 fw-bold mb-1">How the disease space is organized</h2>
   <p class="text-secondary mb-0">Anatomy-based disease distribution and directly supported inheritance evidence.</p>
  </div>

  <div class="row g-4 mt-1">
   <div class="col-12 col-xl-7">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Ocular disease anatomy memberships</h3>
       <div id="anatomySummaryText" class="small text-secondary">Loading disease count…</div>
      </div>
     </div>
     <div id="anatomyDonut" class="chart chart-lg" role="img" aria-label="Donut chart of ODDB diseases by anatomy category"></div>
    </article>
   </div>

   <div class="col-12 col-xl-5">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Inheritance evidence</h3>
       <div class="small text-secondary">Category counts are memberships; one disease may have multiple supported modes.</div>
      </div>
     </div>
     <div id="inheritanceDonut" class="chart chart-md" role="img" aria-label="Donut chart of supported inheritance memberships"></div>
     <div class="coverage-row">
      <div id="inheritanceCoverageDonut" class="chart chart-compact" role="img" aria-label="Donut chart of inheritance classification coverage"></div>
      <div id="inheritanceCoverageText" class="coverage-copy"></div>
     </div>
    </article>
   </div>
  </div>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Genetics and variants</div>
   <h2 class="h3 fw-bold mb-1">Composition of the molecular data</h2>
   <p class="text-secondary mb-0">Gene/entity categories and consequence annotations mapped to canonical variants.</p>
  </div>

  <div class="row g-4 mt-1">
   <div class="col-12 col-lg-5">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Gene and locus categories</h3>
       <div class="small text-secondary">Treemap area is proportional to the number of entities.</div>
      </div>
     </div>
     <div id="geneTreemap" class="chart chart-lg" role="img" aria-label="Treemap of ODDB gene and locus categories"></div>
    </article>
   </div>

   <div class="col-12 col-lg-7">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Variant consequence annotations</h3>
       <div id="variantCoverageText" class="small text-secondary">Loading consequence coverage…</div>
      </div>
     </div>
     <div id="variantTreemap" class="chart chart-lg" role="img" aria-label="Treemap of ODDB variant consequence categories"></div>
    </article>
   </div>
  </div>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Therapeutics</div>
   <h2 class="h3 fw-bold mb-1">Clinical stage and evidence structure</h2>
   <p class="text-secondary mb-0">Direct therapeutic evidence remains distinct from target-overlap discovery relationships.</p>
  </div>

  <div class="row g-4 mt-1">
   <div class="col-12 col-xl-5">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Source-reported maximum drug development stage</h3>
       <div class="small text-secondary">Highest recorded development stage for each canonical drug entity; missing stage values are shown separately.</div>
      </div>
     </div>
     <div id="drugStageDonut" class="chart chart-lg" role="img" aria-label="Donut chart of drug maximum clinical stage"></div>
    </article>
   </div>

   <div class="col-12 col-xl-7">
    <article class="viz-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Disease–drug relationship space</h3>
       <div class="small text-secondary">Unique disease–drug pairs classified by direct therapeutic evidence and target overlap.</div>
      </div>
     </div>
     <div id="therapeuticSankey" class="chart chart-xl" role="img" aria-label="Sankey chart of ODDB disease-drug relationship classes"></div>
     <div class="alert alert-light border small mb-0">
      Target-overlap-only pairs are discovery connections and must not be interpreted as treatment assertions.
     </div>
    </article>
   </div>
  </div>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Clinical evidence</div>
   <h2 class="h3 fw-bold mb-1">Trials and clinical reports</h2>
   <p class="text-secondary mb-0">
    Unique clinical evidence records are shown as central entities, with their disease and drug association layers around them.
   </p>
  </div>

  <div class="row g-4 mt-1">
   <div class="col-12 col-xl-6">
    <article class="viz-card clinical-profile-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Clinical trials</h3>
       <div class="small text-secondary">Unique trial records and their many-to-many links to diseases and drugs.</div>
      </div>
     </div>
     <div id="trialEvidenceOrbit" class="chart clinical-orbit" role="img"
          aria-label="Relationship profile for clinical trials"></div>
     <div id="trialEvidenceMetrics" class="clinical-metrics"></div>
    </article>
   </div>

   <div class="col-12 col-xl-6">
    <article class="viz-card clinical-profile-card h-100">
     <div class="viz-head">
      <div>
       <h3 class="h5 mb-1">Clinical reports</h3>
       <div class="small text-secondary">Unique report records and their many-to-many links to diseases and drugs.</div>
      </div>
     </div>
     <div id="reportEvidenceOrbit" class="chart clinical-orbit" role="img"
          aria-label="Relationship profile for clinical reports"></div>
     <div id="reportEvidenceMetrics" class="clinical-metrics"></div>
    </article>
   </div>
  </div>

  <div class="clinical-note mt-3">
   <strong>How to read this:</strong>
   “Entities” means unique records in ODDB (one trial or one clinical report).
   Disease associations and drug associations are relationship rows, so their counts can be higher than the number of entities because one record may link to multiple diseases and/or drugs.
  </div>
 </section>

<?php require __DIR__ . '/partials/statistics_extended.php'; ?>

<section class="container section-block" id="knowledge-flows">
  <div class="section-heading">
   <div class="eyebrow">Knowledge flow maps</div>
   <h2 class="h3 fw-bold mb-1">Follow ODDB relationships across data layers</h2>
   <p class="text-secondary mb-0">
    Explore four focused Sankey views rather than one overloaded diagram.
    Select a flow, adjust the number of disease nodes, and tap or hover nodes for full labels.
   </p>
  </div>

  <article class="viz-card mt-3 knowledge-flow-card">
   <div class="knowledge-flow-toolbar">
    <div class="knowledge-flow-tabs" role="tablist" aria-label="Knowledge flow type">
     <button class="flow-tab active" type="button" data-flow-type="disease" role="tab" aria-selected="true">Disease flow</button>
     <button class="flow-tab" type="button" data-flow-type="gene" role="tab" aria-selected="false">Gene flow</button>
     <button class="flow-tab" type="button" data-flow-type="variant" role="tab" aria-selected="false">Variant flow</button>
     <button class="flow-tab" type="button" data-flow-type="therapeutic" role="tab" aria-selected="false">Therapeutic flow</button>
    </div>

    <div class="knowledge-flow-controls">
     <label for="knowledgeFlowLimit" class="small text-secondary">Diseases shown</label>
     <select id="knowledgeFlowLimit" class="form-select form-select-sm">
      <option value="25">25 most connected</option>
      <option value="40">40 most connected</option>
      <option value="50">50 most connected</option>
      <option value="100">100 most connected</option>
      <option value="all">All diseases</option>
     </select>
     <button id="knowledgeFlowReset" type="button" class="btn btn-sm btn-outline-secondary">Reset</button>
    </div>
   </div>

   <div class="knowledge-flow-head">
    <div>
     <h3 id="knowledgeFlowTitle" class="h5 mb-1">Disease classification flow</h3>
     <div id="knowledgeFlowSubtitle" class="small text-secondary"></div>
     <div id="knowledgeFlowSelection" class="flow-selection-note"></div>
    </div>
    <div class="knowledge-flow-arrows">
     <button id="knowledgeFlowPrev" type="button" class="btn btn-sm btn-outline-secondary" aria-label="Previous flow">←</button>
     <button id="knowledgeFlowNext" type="button" class="btn btn-sm btn-outline-secondary" aria-label="Next flow">→</button>
    </div>
   </div>

   <div id="knowledgeFlowNote" class="flow-note d-none"></div>

   <div id="knowledgeFlowChart" class="knowledge-flow-scroll" aria-label="Interactive ODDB Sankey flow">
    <div id="knowledgeFlowChartInner" class="knowledge-flow-chart-inner"></div>
   </div>

   <div id="knowledgeFlowSummary" class="knowledge-flow-summary"></div>

   <div class="knowledge-flow-help">
    <span>Hover or tap for full labels and counts.</span>
    <span>Click a disease or anatomy node to open it in Explore.</span>
    <span>On small screens, swipe horizontally across the chart.</span>
   </div>
  </article>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Relationship maps</div>
   <h2 class="h3 fw-bold mb-1">Explore cross-layer connectivity</h2>
   <p class="text-secondary mb-0">
    Swipe, use the arrows, or choose a map to move through circular relationship views.
    Edge width reflects the number of underlying ODDB associations.
   </p>
  </div>

  <article class="viz-card mt-3 relationship-card">
   <div class="relationship-toolbar">
    <div class="relationship-title-wrap">
     <div class="d-flex align-items-center gap-2 flex-wrap">
      <span id="relationshipCounter" class="map-counter">Map 1 of 6</span>
     </div>
     <h3 id="relationshipTitle" class="h5 mt-2 mb-1">Loading relationship map…</h3>
     <div id="relationshipDescription" class="small text-secondary"></div>
    </div>

    <div class="relationship-actions">
     <label class="visually-hidden" for="relationshipSelect">Choose relationship map</label>
     <select id="relationshipSelect" class="form-select form-select-sm map-select" aria-label="Choose relationship map"></select>
     <button id="relationshipReset" type="button" class="btn btn-sm btn-outline-secondary">Reset view</button>
    </div>
   </div>

   <div id="relationshipViewport" class="relationship-viewport" tabindex="0"
        aria-label="Swipe left or right to change relationship map">
    <button id="relationshipPrev" type="button" class="relationship-arrow relationship-prev"
            aria-label="Previous relationship map">‹</button>

    <div class="relationship-canvas-wrap">
     <div id="relationshipRing" class="chart chart-ring" role="img"
          aria-label="Interactive circular ODDB relationship network"></div>
    </div>

    <button id="relationshipNext" type="button" class="relationship-arrow relationship-next"
            aria-label="Next relationship map">›</button>
   </div>

   <div class="relationship-footer">
    <div id="relationshipDots" class="relationship-dots" aria-label="Relationship map pages"></div>
    <div id="relationshipLegend" class="ring-legend"></div>
   </div>

   <div class="relationship-help">
    <span>Drag to pan · pinch/scroll to zoom · tap/hover for full labels and counts.</span>
    <span id="relationshipMobileHint" class="d-none">Labels are shortened on the circle; full terms are shown in tooltips.</span>
   </div>
  </article>
 </section>
<section class="container section-block">
  <article class="viz-card">
   <div class="row g-4 align-items-center">
    <div class="col-lg-8">
     <div class="eyebrow">Usage statistics</div>
     <h2 class="h4 fw-bold mt-1">ODDB usage and visitors</h2>
     <p class="text-secondary mb-0">
      Visitor counts, country-level usage, downloads and popular records will be added after production analytics are deployed.
      Only aggregated, privacy-conscious public statistics will be shown.
     </p>
    </div>
    <div class="col-lg-4">
     <div class="analytics-placeholder">
      <strong>Production analytics</strong>
      <div class="small text-secondary mt-1">Not enabled on this local development instance.</div>
     </div>
    </div>
   </div>
  </article>
 </section>
</main>

<footer class="site-footer">
 <div class="container py-4">
  <div class="d-flex flex-column flex-md-row justify-content-between gap-2">
   <div><strong>ODDB v1</strong> · Ocular Disease Database</div>
   <div class="small text-secondary">oculardiseases.fi</div>
  </div>
 </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script src="assets/statistics.js"></script>
<script src="assets/statistics_flows.js"></script>
<script src="assets/statistics_export.js"></script>
<script src="assets/statistics_enhanced.js?v=3"></script>
<script src="assets/statistics_publication_export.js?v=1"></script>
<script src="assets/site-nav.js"></script>
</body>
</html>
