<?php declare(strict_types=1); ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Explore ODDB v1 — Ocular Disease Database</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/style.css" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/explore-search-layout.css?v=0.7.4b" rel="stylesheet">
<link href="assets/workbench-ui.css?v=0.7.5" rel="stylesheet">
<link href="assets/analysis-tools.css?v=0.7.6" rel="stylesheet">
<link href="assets/publication.css?v=0.7.7" rel="stylesheet">
<link href="assets/evidence-filters.css?v=0.7.8" rel="stylesheet">
<link href="assets/drug-comparison.css?v=0.7.9" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
</head>
<body class="oddb-visual oddb-explore">
<?php require __DIR__ . "/partials/site_nav.php"; ?>

<main class="container-fluid px-3 px-lg-4 py-3">
 <section class="card shadow-sm border-0 browse-header mb-3">
  <div class="card-body p-3 p-lg-4">
<!-- ODDB integrated entity search v0.7.4b: start -->
<div class="oddb-explore-search-strip entity-search-strip entity-search-integrated">
 <div class="oddb-explore-search-inner">
  <div class="entity-search-title-row">
   <h1 id="entitySearchHeading" class="entity-search-heading">Explore ODDB</h1>
   <p id="entitySearchDescription" class="entity-search-description">Search diseases, genes, variants, drugs and clinical evidence. Add a result to your workbench or start an analysis.</p>
  </div>
  <div class="entity-search-field">
   <svg class="entity-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" focusable="false"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 4.5 4.5"></path></svg>
   <input id="globalSearch" class="form-control" type="search" autocomplete="off" aria-label="Search ODDB entities" aria-describedby="entitySearchDescription globalSearchStatus" placeholder="Search disease, HGNC gene, variant, drug, trial or report…">
   <button id="clearGlobalSearch" class="entity-search-clear" type="button" aria-label="Clear search">Clear</button>
   <div id="searchResults" class="search-results entity-search-results d-none"></div>
  </div>
  <div id="globalSearchTypeFilters" class="entity-search-filters" role="group" aria-label="Entity type filters">
   <button type="button" class="entity-search-filter active" data-global-search-type="">All</button>
   <button type="button" class="entity-search-filter" data-global-search-type="disease">Disease</button>
   <button type="button" class="entity-search-filter" data-global-search-type="gene">Gene</button>
   <button type="button" class="entity-search-filter" data-global-search-type="variant">Variant</button>
   <button type="button" class="entity-search-filter" data-global-search-type="drug">Drug</button>
   <button type="button" class="entity-search-filter" data-global-search-type="trial">Clinical Trial</button>
   <button type="button" class="entity-search-filter" data-global-search-type="report">Clinical Report</button>
  </div>
  <div id="globalSearchStatus" class="entity-search-status" role="status" aria-live="polite" aria-atomic="true"></div>
 </div>
</div>
<!-- ODDB integrated entity search v0.7.4b: end -->
   <div class="d-flex flex-column flex-lg-row justify-content-between gap-3">
    <div>
     <div class="small text-uppercase fw-bold text-secondary mb-2">Disease categorization</div>
     <div class="btn-group mode-toggle">
      <button class="btn btn-primary active" data-category-system="anatomy">Anatomy Based Categorization</button>
      <button class="btn btn-light" data-category-system="inheritance">Inheritance Based Categorization</button>
     </div>
    </div>
    <div class="text-lg-end">
     <div class="small text-uppercase fw-bold text-secondary mb-2">Starting data view</div>
     <div class="btn-group mode-toggle">
      <button class="btn btn-primary active" data-data-mode="gene">Gene Based</button>
      <button class="btn btn-light" data-data-mode="variant">Variant Based</button>
     </div>
    </div>
   </div>

   <hr class="my-3">
   <div id="categoryStrip" class="category-grid"></div>

   <div class="mt-3">
    <div id="subtypeTitle" class="small text-uppercase fw-bold text-secondary mb-2">Gene type</div>
    <div id="subtypeChips" class="chip-wrap"></div>
   </div>

   <div class="mt-3">
    <div class="small text-uppercase fw-bold text-secondary mb-2">Drug clinical phase / stage</div>
    <div id="drugPhaseChips" class="chip-wrap"></div>
   </div>
  </div>
 </section>

 <div class="row g-3">
  <section class="col-12 col-xl-3">
   <div class="card shadow-sm app-card">
    <div class="card-header bg-white">
     <div class="d-flex justify-content-between align-items-start gap-2">
      <div>
       <div class="fw-semibold">Diseases</div>
       <div id="diseaseCount" class="small text-secondary">Choose a category.</div>
      </div>
      <button id="clearSelection" class="btn btn-sm btn-outline-secondary">Clear</button>
     </div>

     <input id="diseaseSearch" class="form-control form-control-sm mt-2" placeholder="Filter disease names…">

     <div class="disease-selection-toolbar mt-2">
      <button id="selectAllShown" class="btn btn-sm btn-light border">Select shown</button>
      <button id="updateNetwork" class="btn btn-sm btn-primary">Update network</button>
     </div>
     <div id="selectedDiseaseSummary" class="small text-secondary mt-2">0 diseases selected</div>
    </div>

    <div id="diseaseList" class="list-group list-group-flush disease-list">
     <div class="p-4 text-center text-secondary small">Select a category above.</div>
    </div>
   </div>
  </section>

  <section class="col-12 col-xl-6">
   <div class="card shadow-sm app-card explorer-workbench-card wb-simplified" data-workbench-layout="0.7.5" data-analysis-tools="0.7.6" data-publication-export="0.7.7" data-evidence-filters="0.7.8" data-drug-comparison="0.7.9" data-graph-zoom="0.7.9a">
<div class="card-header bg-white">
     <div class="network-head">
      <div>
       <div class="fw-semibold">ODDB Graph Workbench</div>
       <div id="networkSummary" class="small text-secondary">Select one or more diseases.</div>
      </div>

      <div class="network-actions">
       <button id="saveAnalysis" type="button" class="btn btn-sm btn-outline-secondary">Save analysis</button>
       <button id="restoreAnalysis" type="button" class="btn btn-sm btn-outline-secondary">Restore analysis</button>

       <button id="fitGraph" class="btn btn-sm btn-outline-secondary">Fit</button>
       <button id="relayoutGraph" class="btn btn-sm btn-outline-secondary">Relayout</button>

       <details class="network-export">
        <summary class="btn btn-sm btn-outline-secondary">Export ▾</summary>
        <div class="network-export-menu">
 <div class="export-menu-title">Publication</div>
 <button id="publicationOpen" type="button">Publication figure and evidence…</button>
         <div class="export-menu-title">Vector images</div>
         <button type="button" data-analysis-export="viewport">Current viewport SVG</button>
         <button type="button" data-analysis-export="full">Full shown network SVG</button>
         <button type="button" data-analysis-export="selected">Selected subgraph SVG</button>

         <div class="export-menu-title">Images</div>
         <button type="button" data-export="viewport-png">Current viewport PNG</button>
         <button type="button" data-export="full-png">Full shown network PNG</button>
         <button type="button" data-export="selected-png">Selected subgraph PNG</button>
         <div class="export-menu-title">Data</div>
         <button type="button" data-export="shown-csv">Shown network CSV</button>
         <button type="button" data-export="selected-csv">Selected subgraph CSV</button>
        </div>
       </details>
      </div>
     </div>
    </div>
<div class="history-workbench-bar border-bottom">
     <div class="history-controls">
      <button id="historyBack" class="btn btn-sm btn-outline-secondary" disabled aria-label="Back to previous graph state">← Back</button>
      <button id="historyForward" class="btn btn-sm btn-outline-secondary" disabled aria-label="Forward to next graph state">Forward →</button>
      <span id="historyCount" class="history-count">0 steps</span>
     </div>
     <div class="history-trail-wrap">
      <span class="history-trail-label">Exploration history</span>
      <div id="historyBreadcrumb" class="history-breadcrumb"><span>Start</span></div>
     </div>
    </div>
<div class="pinned-workbench-bar border-bottom" hidden>
     <div class="workbench-bar-label">Pinned</div>
     <div id="pinnedEntityChips" class="workbench-chip-list">
      <span class="text-secondary small">No pinned entities.</span>
     </div>
    </div>
<div class="graph-action-bar border-bottom">
     <div class="graph-action-copy">
      <strong id="graphSelectionSummary">0 graph nodes selected</strong>
      <span>Ctrl/Cmd/Shift+click selects multiple nodes.</span>
     </div>
     <div class="graph-action-controls">
      <select id="expandAction" class="form-select form-select-sm" disabled>
       <option value="">Select node(s) first</option>
      </select>
      <button id="expandSelected" class="btn btn-sm btn-primary" disabled>Expand selected</button>
      <button id="pinSelected" class="btn btn-sm btn-outline-primary" disabled>Pin</button>
      <button id="unpinSelected" class="btn btn-sm btn-outline-secondary" disabled>Unpin</button>
      
      
      
      
     </div>
    </div>
<div id="workbenchNotice" class="workbench-notice d-none" role="status"></div>
<div id="analysisFeedback" class="analysis-feedback" role="status" aria-live="polite" hidden>
 <span id="analysisBusy" hidden></span><span id="analysisError"></span>
 <button id="analysisRetry" type="button" hidden>Retry last action</button>
 <button id="analysisDismiss" type="button" hidden>Dismiss</button>
</div>

<div class="wb-tools" role="group" aria-label="Workbench analysis tools">
 <button id="wbLayersButton" class="wb-tool-button" type="button" data-wb-panel="wbLayersPanel" aria-controls="wbLayersPanel" aria-expanded="false">Evidence layers</button>
<button id="wbEvidenceButton" class="wb-tool-button" type="button" data-wb-panel="wbEvidencePanel" aria-controls="wbEvidencePanel" aria-expanded="false">Evidence filters <span id="wbEvidenceBadge" class="wb-tool-badge" hidden></span></button>
 <button id="wbComparisonButton" class="wb-tool-button" type="button" data-wb-panel="wbComparisonPanel" aria-controls="wbComparisonPanel" aria-expanded="false">Compare diseases <span id="wbComparisonBadge" class="wb-tool-badge" hidden></span></button>
<button id="wbDrugComparisonButton" class="wb-tool-button" type="button" data-wb-panel="wbDrugComparisonPanel" aria-controls="wbDrugComparisonPanel" aria-expanded="false">Compare drugs <span id="wbDrugComparisonBadge" class="wb-tool-badge" hidden></span></button>
 <button id="wbPathButton" class="wb-tool-button" type="button" data-wb-panel="wbPathPanel" aria-controls="wbPathPanel" aria-expanded="false">Find paths <span id="wbPathBadge" class="wb-tool-badge" hidden></span></button>
 <button id="wbOptionsButton" class="wb-tool-button" type="button" data-wb-panel="wbOptionsPanel" aria-controls="wbOptionsPanel" aria-expanded="false">More controls</button>
 <span id="hiddenLayerCount" class="hidden-layer-count wb-layer-status" hidden>All layers visible</span>
</div>
<div class="wb-tool-panels">
<section id="wbDrugComparisonPanel" class="wb-panel dc-panel" role="region" aria-labelledby="wbDrugComparisonTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbDrugComparisonTitle" class="wb-panel-title">Compare drugs</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close drug comparison">Close</button></div>
 <p class="dc-intro">Compare 2–5 drugs using validated relationships loaded in this graph. Evidence filters and hidden layers apply. Expand each drug first to include its available connections.</p>
 <div class="dc-layout">
  <div class="dc-picker">
   <label for="drugComparisonSearch">Find a loaded drug</label><input id="drugComparisonSearch" class="form-control form-control-sm" type="search" placeholder="Name or identifier" autocomplete="off">
   <div id="drugComparisonOptions" class="dc-options" role="group" aria-label="Drugs to compare"></div>
   <div id="drugComparisonPickerCount" class="dc-small"></div>
   <button id="drugComparisonUseSelection" type="button" class="btn btn-sm btn-outline-secondary">Use graph selection</button>
   <label for="drugComparisonDisease">Disease context</label><select id="drugComparisonDisease" class="form-select form-select-sm"><option value="">All loaded diseases</option></select>
  </div>
  <div class="dc-content">
   <div id="drugComparisonChips" class="dc-chips" aria-label="Comparison drugs"></div>
   <div class="dc-actions"><button id="drugComparisonUpdate" type="button" class="btn btn-sm btn-primary">Update comparison</button><button id="drugComparisonClear" type="button" class="btn btn-sm btn-outline-secondary">Clear</button><button id="drugComparisonCSV" type="button" class="btn btn-sm btn-outline-secondary" disabled>Comparison CSV</button><button id="drugComparisonEvidenceCSV" type="button" class="btn btn-sm btn-outline-secondary" disabled>Evidence CSV</button><button id="drugComparisonSVG" type="button" class="btn btn-sm btn-outline-secondary" disabled>Table SVG</button><button id="drugComparisonPrint" type="button" class="btn btn-sm btn-outline-secondary" disabled>Printable table</button></div>
   <p id="drugComparisonStatus" class="dc-status" role="status" aria-live="polite">Choose 2–5 drugs, then update the comparison.</p>
   <p id="drugComparisonScope" class="dc-small"></p>
   <div id="drugComparisonTable" class="dc-table-wrap" tabindex="0" aria-label="Drug evidence comparison"></div>
   <div id="drugComparisonDetails" class="dc-details"></div>
   <p class="dc-semantics">Counts describe the loaded graph. A zero does not establish absence from ODDB. Recorded clinical stage is drug-level information. Target overlap, trial investigation and report links remain separate from direct therapeutic evidence.</p>
  </div>
 </div>
</section>

<section id="wbEvidencePanel" class="wb-panel" role="region" aria-labelledby="wbEvidenceTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbEvidenceTitle" class="wb-panel-title">Evidence filters</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close evidence filters">Close</button></div>
 <p class="ef-help">Choose any values within a group. Groups combine with AND. Source and class must match the same provenance record. Association-level classes apply to all its primary evidence records. Trial status applies only to trial connections. Classes use recorded values without ranking them.</p>
 <div class="ef-actions"><button id="evidenceReset" type="button" class="btn btn-sm btn-outline-secondary">Reset evidence filters</button><button id="evidenceRefresh" type="button" class="btn btn-sm btn-outline-secondary">Refresh evidence</button><label class="ef-check"><input id="evidenceHideDisconnected" type="checkbox"> Hide disconnected entities</label></div>
 <p class="ef-help">Pinned, selected and seed entities stay visible when disconnected entities are hidden.</p>
 <div id="evidenceFilterCounts" class="ef-counts" role="status" aria-live="polite"></div>
 <p id="evidenceValidationStatus" class="ef-status" role="status" aria-live="polite"></p>
 <div class="ef-grid">
  <fieldset><legend>Data source</legend><label class="visually-hidden" for="evidenceSourceSearch">Find a data source</label><input id="evidenceSourceSearch" class="form-control form-control-sm" type="search" placeholder="Find a source"><div id="evidenceSourceOptions" class="ef-options"></div><small id="evidenceSourceCount"></small></fieldset>
  <fieldset><legend>Recorded evidence class</legend><label class="visually-hidden" for="evidenceClassSearch">Find an evidence class</label><input id="evidenceClassSearch" class="form-control form-control-sm" type="search" placeholder="Find a class"><div id="evidenceClassOptions" class="ef-options"></div><small id="evidenceClassCount"></small></fieldset>
  <fieldset><legend>Clinical trial status</legend><label class="visually-hidden" for="evidenceStatusSearch">Find a trial status</label><input id="evidenceStatusSearch" class="form-control form-control-sm" type="search" placeholder="Find a trial status"><div id="evidenceStatusOptions" class="ef-options"></div><small id="evidenceStatusCount"></small></fieldset>
 </div>
</section>
<section id="wbLayersPanel" class="wb-panel" role="region" aria-labelledby="wbLayersTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbLayersTitle" class="wb-panel-title">Evidence layers</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close Evidence layers">Close</button></div>
 <div class="evidence-layer-bar border-bottom">
     <div class="evidence-layer-heading">
      <div>
       <strong>Visible evidence layers</strong>
       <span>Hide or reveal loaded evidence without deleting it from the analysis.</span>
      </div>
      
     </div>
     <div class="evidence-layer-controls">
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="disease" checked><span>Disease <b data-layer-count="disease">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="gene" checked><span>Gene <b data-layer-count="gene">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="variant" checked><span>Variant <b data-layer-count="variant">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="direct" checked><span>Direct therapeutic <b data-layer-count="direct">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="target" checked><span>Drug–target <b data-layer-count="target">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="overlap" checked><span>Target overlap <b data-layer-count="overlap">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="trial" checked><span>Clinical trial <b data-layer-count="trial">0</b></span></label>
      <label class="layer-toggle"><input type="checkbox" data-layer-toggle="report" checked><span>Clinical report <b data-layer-count="report">0</b></span></label>
     </div>
    </div>
</section>
<section id="wbComparisonPanel" class="wb-panel" role="region" aria-labelledby="wbComparisonTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbComparisonTitle" class="wb-panel-title">Compare diseases</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close Compare diseases">Close</button></div>
 <section id="comparisonWorkbench" class="comparison-workbench border-bottom">
     <div class="comparison-head">
      <div>
       <div class="fw-semibold">Disease Comparison + Shared-Neighbor Discovery</div>
       <div class="small text-secondary">Compare 2–5 selected diseases using explicit ODDB relationships. Therapeutic discovery is kept separate from direct disease–drug evidence.</div>
      </div>
      <div class="comparison-head-actions">
       <button id="runComparison" class="btn btn-sm btn-primary" disabled>Compare selected diseases</button>
       <button id="clearComparison" class="btn btn-sm btn-outline-secondary">Clear comparison</button>
      </div>
     </div>
     <div id="comparisonSelection" class="comparison-selection small text-secondary">Select 2–5 diseases in the disease panel.</div>
     <div id="comparisonSummary" class="comparison-summary d-none"></div>
     <div id="comparisonTabs" class="comparison-tabs d-none"></div>
     <div id="comparisonResults" class="comparison-results d-none"></div>
    </section>
</section>
<section id="wbPathPanel" class="wb-panel" role="region" aria-labelledby="wbPathTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbPathTitle" class="wb-panel-title">Find evidence paths</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close Find evidence paths">Close</button></div>
 <section id="pathFinderWorkbench" class="pathfinder-workbench border-bottom">
     <div class="pathfinder-head">
      <div>
       <div class="fw-semibold">Evidence-aware Path Finder</div>
       <div class="small text-secondary">Find explicit, interpretable paths between diseases, genes, variants and drugs. Direct therapeutic evidence, target-overlap discovery and clinical co-occurrence are never treated as equivalent.</div>
      </div>
      <button id="clearPathFinder" class="btn btn-sm btn-outline-secondary">Clear paths</button>
     </div>

     <div class="pathfinder-controls">
      <div class="path-endpoint">
       <label class="form-label small fw-bold">From</label>
       <div class="path-search-wrap position-relative">
        <input id="pathFromSearch" class="form-control form-control-sm" autocomplete="off" placeholder="Search disease, gene, variant or drug…">
        <div id="pathFromResults" class="search-results path-search-results d-none"></div>
       </div>
       <div id="pathFromChosen" class="path-chosen small text-secondary">No start entity selected.</div>
       <button id="pathUseSelectedFrom" class="btn btn-sm btn-light border mt-1">Use selected graph node</button>
      </div>

      <button id="swapPathEndpoints" class="btn btn-sm btn-outline-secondary path-swap" title="Swap From and To">⇄</button>

      <div class="path-endpoint">
       <label class="form-label small fw-bold">To</label>
       <div class="path-search-wrap position-relative">
        <input id="pathToSearch" class="form-control form-control-sm" autocomplete="off" placeholder="Search disease, gene, variant or drug…">
        <div id="pathToResults" class="search-results path-search-results d-none"></div>
       </div>
       <div id="pathToChosen" class="path-chosen small text-secondary">No destination entity selected.</div>
       <button id="pathUseSelectedTo" class="btn btn-sm btn-light border mt-1">Use selected graph node</button>
      </div>

      <div class="path-options">
       <label class="form-label small fw-bold">Maximum relationships</label>
       <select id="pathMaxLength" class="form-select form-select-sm">
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3" selected>3</option>
        <option value="4">4</option>
       </select>
       <button id="findPaths" class="btn btn-sm btn-primary mt-2" disabled>Find paths</button>
      </div>
     </div>

     <div class="pathfinder-meaning">
      <span class="path-badge direct">DIRECT THERAPEUTIC EVIDENCE</span>
      <span class="path-badge discovery">TARGET-OVERLAP DISCOVERY</span>
      <span class="path-badge clinical">CLINICAL CO-OCCURRENCE</span>
      <span class="path-badge supported">EVIDENCE-SUPPORTED PATH</span>
     </div>

     <div id="pathFinderSummary" class="small text-secondary mt-2">Choose a From and To entity.</div>
     <div id="pathFinderResults" class="pathfinder-results d-none"></div>
    </section>
</section>
<section id="wbOptionsPanel" class="wb-panel" role="region" aria-labelledby="wbOptionsTitle" hidden>
 <div class="wb-panel-top"><h2 id="wbOptionsTitle" class="wb-panel-title">Network options and graph key</h2><button class="wb-panel-close" type="button" data-wb-close aria-label="Close Network options and graph key">Close</button></div>
 <div class="network-options retrieval-options px-3 py-2 border-bottom small">
     <strong>Initial disease-network retrieval</strong>
     <label><input type="checkbox" id="showDirect" checked> Include direct disease–drug evidence</label>
     <label><input type="checkbox" id="showOverlap"> Include target-overlap discovery</label>
    </div>
<div class="wb-extra-actions"><button id="focusSelected" class="btn btn-sm btn-outline-secondary" disabled>Focus</button>
<button id="showAllNodes" class="btn btn-sm btn-outline-secondary">Show all</button>
<button id="clearUnpinned" class="btn btn-sm btn-outline-secondary">Clear unpinned</button>
<button id="resetAnalysis" class="btn btn-sm btn-outline-danger">Reset</button></div>
<div class="legend legend-v071 px-3 py-2 border-bottom">
     <span><i class="dot disease"></i>Disease</span>
     <span><i class="dot gene"></i>Gene</span>
     <span><i class="dot locus"></i>Locus</span>
     <span><i class="dot variant"></i>Variant</span>
     <span><i class="dot drug"></i>Drug</span>
     <span><i class="dot trial"></i>Trial</span>
     <span><i class="dot report"></i>Report</span>
     <span class="legend-divider"></span>
     <span><i class="state-ring selected"></i>Selected</span>
     <span><i class="state-ring pinned"></i>Pinned</span>
     <span><i class="state-ring expanded"></i>Expanded / discovered</span>
     <span class="legend-divider"></span>
     <span><i class="line disease-gene"></i>Disease–gene</span>
     <span><i class="line direct"></i>Direct therapeutic evidence</span>
     <span><i class="line target"></i>Drug–target</span>
     <span><i class="line discovery"></i>Target-overlap discovery</span>
     <span><i class="line clinical"></i>Clinical evidence</span>
    </div>
<div class="network-export-note">
     <strong>Generic expansion:</strong> diseases, genes, variants, drugs, trials and clinical reports can all be expanded in evidence-aware directions.
     <strong>Pinned entities</strong> stay in the workbench during further expansion and disease-network refreshes.
    </div>
</section></div>
<div class="wb-graph-key" aria-label="Relationship key">
 <span><i class="line direct" aria-hidden="true"></i>Direct therapeutic evidence</span>
 <span><i class="line discovery" aria-hidden="true"></i>Target-overlap discovery</span>
 <span><i class="line clinical" aria-hidden="true"></i>Clinical evidence</span>
</div>
<div class="wb-canvas"><div id="cy"></div>
<section id="entityStarter" class="entity-starter border-bottom">
     <div class="entity-starter-copy">
      <div class="small text-uppercase fw-bold text-secondary">Start an entity-first analysis</div>
      <div class="fw-semibold mt-1">Begin with any core ODDB entity</div>
      <div class="small text-secondary">The selected entity is added as the starting node. Its evidence-aware expansion actions then appear in the details panel.</div>
     </div>
     <div class="entity-starter-grid mt-2">
      <button data-entity-starter="disease"><strong>Disease</strong><span>genes · variants · direct drugs · trials · reports</span></button>
      <button data-entity-starter="gene"><strong>Gene</strong><span>diseases · variants · targeting drugs</span></button>
      <button data-entity-starter="variant"><strong>Variant</strong><span>gene · explicit disease links · consequence</span></button>
      <button data-entity-starter="drug"><strong>Drug</strong><span>direct diseases · targets · trials · reports</span></button>
      <button data-entity-starter="trial"><strong>Clinical Trial</strong><span>linked diseases · investigated drugs</span></button>
      <button data-entity-starter="report"><strong>Clinical Report</strong><span>linked diseases · linked drugs</span></button>
     </div>
    </section></div>
</div>
  </section>

  <aside class="col-12 col-xl-3">
   <div class="card shadow-sm app-card details-card">
    <div class="card-header bg-white">
     <div class="fw-semibold">Entity / evidence details</div>
     <div class="small text-secondary">Click a node or relationship for details and expansion actions.</div>
    </div>
    <div id="detailsPanel" class="card-body">
     <div class="empty-state">
      <div class="empty-symbol">◎</div>
      <div class="fw-semibold">No entity selected</div>
      <div class="small text-secondary">Choose diseases and update the network.</div>
     </div>
    </div>
   </div>
  </aside>
 </div>
</main>

<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js"></script>
<script src="assets/explore.js?v=0.7.9a"></script>
<script src="assets/site-nav.js"></script>
<script src="assets/workbench-ui.js?v=0.7.5"></script>
<input id="analysisFile" type="file" accept=".json,application/json" hidden>
<dialog id="analysisDialog" class="analysis-dialog" aria-labelledby="analysisDialogTitle" aria-describedby="analysisDialogSummary">
 <div class="analysis-dialog-header"><h2 id="analysisDialogTitle">Restore analysis</h2><p id="analysisDialogSummary" role="status" aria-live="polite"></p></div>
 <div id="analysisDialogDetails" class="analysis-dialog-details"></div>
 <div class="analysis-dialog-actions">
  <button id="analysisReportDownload" type="button" class="btn btn-outline-secondary" hidden>Download validation report</button>
  <button id="analysisCancel" type="button" class="btn btn-outline-secondary">Cancel</button>
  <button id="analysisApply" type="button" class="btn btn-primary" disabled>Restore validated analysis</button>
 </div>
</dialog>

<script src="assets/analysis-tools.js?v=0.7.9"></script>
<dialog id="publicationDialog" class="publication-dialog" aria-labelledby="publicationTitle">
 <header class="publication-head"><div><h2 id="publicationTitle">Publication export</h2><p>Prepare a vector figure and its supporting evidence table.</p></div><button id="publicationClose" type="button" class="btn btn-sm btn-outline-secondary" aria-label="Close publication export">Close</button></header>
 <div class="publication-layout">
  <form id="publicationForm" class="publication-settings">
   <label for="publicationScope">Network to export</label><select id="publicationScope" class="form-select"><option value="full">Full shown network</option><option value="selected">Selected subgraph</option><option value="viewport">Current viewport</option></select>
   <label for="publicationFigureTitle">Figure title</label><input id="publicationFigureTitle" class="form-control" type="text" value="ODDB evidence network" maxlength="120">
   <label for="publicationPreset">Figure size</label><select id="publicationPreset" class="form-select"><option value="double">Double column · 180 × 180 mm</option><option value="single">Single column · 85 × 230 mm</option><option value="custom">Custom dimensions</option></select>
   <div class="publication-field-pair"><div><label for="publicationWidth">Width (mm)</label><input id="publicationWidth" type="number" class="form-control" min="60" max="600" step="1" value="180" required></div><div><label for="publicationHeight">Height (mm)</label><input id="publicationHeight" type="number" class="form-control" min="60" max="600" step="1" value="180" required></div></div>
   <div class="publication-field-pair"><div><label for="publicationFont">Font</label><select id="publicationFont" class="form-select"><option value="Arial">Arial</option><option value="sans-serif">Sans serif</option><option value="serif">Serif</option></select></div><div><label for="publicationLabelSize">Labels (pt)</label><input id="publicationLabelSize" type="number" class="form-control" min="5" max="18" step="0.5" value="8" required></div></div>
   <label class="publication-check"><input id="publicationLabels" type="checkbox" checked> Show entity labels</label>
   <label class="publication-check"><input id="publicationLegend" type="checkbox" checked> Show scientific legend</label>
   <label class="publication-check"><input id="publicationMetadata" type="checkbox" checked> Show release and export date</label>
   <label class="publication-check"><input id="publicationTransparent" type="checkbox"> Transparent background</label>
   <p class="publication-help">Sizes are starting points. Match your journal’s figure requirements. SVG labels remain editable.</p>
  </form>
  <section class="publication-preview-panel" aria-label="Figure preview">
   <p id="publicationStatus" class="publication-status" role="status" aria-live="polite">Preparing export…</p>
   <div class="publication-preview"><img id="publicationPreview" alt="Preview of the publication evidence network" hidden></div>
   <details id="publicationIssues" class="publication-issues" hidden><summary>Validation report</summary><ul id="publicationIssueList"></ul></details>
  </section>
 </div>
 <footer class="publication-actions"><span id="publicationDimensions"></span><button id="publicationRetry" type="button" class="btn btn-outline-secondary" hidden>Retry validation</button><button id="publicationEvidence" type="button" class="btn btn-outline-secondary" disabled>Download evidence CSV</button><button id="publicationPNG" type="button" class="btn btn-outline-secondary" disabled>PNG · 300 dpi</button><button id="publicationSVG" type="button" class="btn btn-primary" disabled>Download SVG</button></footer>
</dialog>

<script src="assets/publication.js?v=0.7.8"></script>
<script src="assets/evidence-filters.js?v=0.7.9"></script>
<script src="assets/drug-comparison.js?v=0.7.9"></script>
</body>
</html>
