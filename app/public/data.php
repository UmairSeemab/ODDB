<?php declare(strict_types=1); ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="ODDB v1 data releases, downloadable datasets, release metadata and evidence interpretation guidance.">
<title>Data &amp; release — ODDB v1</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/data.css" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
</head>
<body class="oddb-visual oddb-data">
<?php require __DIR__ . "/partials/site_nav.php"; ?>

<header class="release-hero">
 <div class="container py-4 py-md-5">
  <div class="row align-items-end g-4">
   <div class="col-lg-8">
    <div class="eyebrow">ODDB v1</div>
    <h1 class="display-5 fw-bold mb-2">Data &amp; release</h1>
    <p class="lead text-secondary mb-0">
     Frozen ODDB v1 datasets, validated release counts, downloadable files and guidance for interpreting the evidence layers.
    </p>
   </div>
   <div class="col-lg-4">
    <div class="release-status-card">
     <span class="status-dot" aria-hidden="true"></span>
     <div>
      <strong>Current ODDB v1 release</strong>
      <div class="small text-secondary">Drug &amp; clinical refined · 30 September 2026</div>
     </div>
    </div>
   </div>
  </div>
 </div>
</header>

<main class="pb-5">
 <section class="container mt-4">
  <div id="releaseOverview" class="release-overview" aria-live="polite">
   <div class="metric-card skeleton"></div>
   <div class="metric-card skeleton"></div>
   <div class="metric-card skeleton"></div>
   <div class="metric-card skeleton"></div>
   <div class="metric-card skeleton"></div>
   <div class="metric-card skeleton"></div>
  </div>
 </section>

 <section class="container section-block">
  <div class="section-heading">
   <div class="eyebrow">Release structure</div>
   <h2 class="h3 fw-bold mb-1">Immutable data releases, derived web curation</h2>
   <p class="text-secondary mb-0">
    Frozen ODDB releases remain unchanged after validation. Later interface or taxonomy curation is applied as a derived web layer rather than rewriting historical release files.
   </p>
  </div>

  <div class="release-timeline mt-4">
   <article class="release-card">
    <div class="release-card-top">
     <div>
      <span class="release-tag">Genetics core</span>
      <h3 class="h5 mt-2 mb-1">ODDB v1 genetics core</h3>
      <div class="text-secondary small">Release date: 29 September 2026</div>
     </div>
     <span class="immutable-badge">Frozen</span>
    </div>
    <div class="release-facts">
     <span><strong>162</strong> diseases</span>
     <span><strong>1,249</strong> genes</span>
     <span><strong>1,631</strong> disease–gene associations</span>
     <span><strong>707,315</strong> variants</span>
     <span><strong>106,838</strong> disease–variant associations</span>
     <span><strong>2</strong> loci</span>
    </div>
   </article>

   <article class="release-card">
    <div class="release-card-top">
     <div>
      <span class="release-tag">Drug &amp; clinical refined</span>
      <h3 class="h5 mt-2 mb-1">ODDB v1 drug &amp; clinical refined</h3>
      <div class="text-secondary small">Release date: 30 September 2026</div>
     </div>
     <span class="immutable-badge">Frozen</span>
    </div>
    <div class="release-facts">
     <span><strong>805</strong> drugs</span>
     <span><strong>1,009</strong> drug–target associations</span>
     <span><strong>344</strong> direct disease–drug associations</span>
     <span><strong>1,291</strong> clinical reports</span>
     <span><strong>1,164</strong> clinical trials</span>
     <span><strong>1,203</strong> target-overlap disease–drug pairs</span>
    </div>
   </article>

   <article class="release-card web-layer-card">
    <div class="release-card-top">
     <div>
      <span class="release-tag">Derived web layer</span>
      <h3 class="h5 mt-2 mb-1">Current web taxonomy &amp; curation</h3>
      <div class="text-secondary small">Maintained separately from frozen release files</div>
     </div>
     <span class="derived-badge">Derived</span>
    </div>
    <p class="small text-secondary mb-0">
     Web-facing anatomy, inheritance and display-level curation may be corrected or refined without mutating the frozen ODDB release directories.
    </p>
   </article>
  </div>
 </section>

 <section class="container section-block" id="downloads">
  <div class="section-heading d-flex flex-column flex-lg-row justify-content-between gap-3 align-items-lg-end">
   <div>
    <div class="eyebrow">Downloads</div>
    <h2 class="h3 fw-bold mb-1">Available release files</h2>
    <p class="text-secondary mb-0">
     Download only files explicitly included in an ODDB v1 frozen release.
    </p>
   </div>
   <div class="catalog-status text-lg-end">
    <div id="catalogStatus" class="small text-secondary">Loading release catalog…</div>
   </div>
  </div>

  <div class="download-toolbar mt-4">
   <label class="download-search">
    <span class="visually-hidden">Search release files</span>
    <input id="datasetSearch" class="form-control" type="search"
           placeholder="Search datasets, e.g. disease, variant, drug…" autocomplete="off">
   </label>
   <div class="download-filters" role="group" aria-label="Filter release files">
    <button type="button" class="filter-chip active" data-release-filter="all">All</button>
    <button type="button" class="filter-chip" data-release-filter="genetics">Genetics core</button>
    <button type="button" class="filter-chip" data-release-filter="clinical">Drug &amp; clinical</button>
   </div>
  </div>

  <div id="datasetCatalog" class="dataset-grid mt-3">
   <div class="dataset-card skeleton dataset-skeleton"></div>
   <div class="dataset-card skeleton dataset-skeleton"></div>
   <div class="dataset-card skeleton dataset-skeleton"></div>
  </div>

  <div id="noDatasets" class="empty-state d-none">
   No downloadable files match the current filter.
  </div>
 </section>

 <section class="container section-block">
  <div class="row g-4">
   <div class="col-12 col-xl-7">
    <article class="info-card h-100">
     <div class="eyebrow">Evidence interpretation</div>
     <h2 class="h4 fw-bold mt-1">Read relationship layers conservatively</h2>
     <div class="evidence-list mt-3">
      <div class="evidence-item">
       <strong>Direct therapeutic evidence ≠ target overlap</strong>
       <p>A shared disease gene and drug target is a discovery relationship and must not automatically be interpreted as a treatment assertion.</p>
      </div>
      <div class="evidence-item">
       <strong>Clinical investigation ≠ approval or efficacy</strong>
       <p>A drug appearing in a clinical trial or source-reported development stage does not by itself establish regulatory approval or therapeutic benefit.</p>
      </div>
      <div class="evidence-item">
       <strong>Drug forms remain explicit</strong>
       <p>Parent drugs, salts and other chemical/form relationships are preserved rather than silently collapsed.</p>
      </div>
      <div class="evidence-item mb-0">
       <strong>Variant evidence remains source-specific</strong>
       <p class="mb-0">Variant classification and gene–disease validity are distinct evidence concepts and are not substituted for one another.</p>
      </div>
     </div>
    </article>
   </div>

   <div class="col-12 col-xl-5">
    <article class="info-card h-100">
     <div class="eyebrow">Reproducibility</div>
     <h2 class="h4 fw-bold mt-1">Release-aware downloads</h2>
     <dl class="release-definition mt-3 mb-0">
      <div><dt>Release name</dt><dd>ODDB v1</dd></div>
      <div><dt>Genetics core</dt><dd>2026-09-29</dd></div>
      <div><dt>Drug &amp; clinical</dt><dd>2026-09-30</dd></div>
      <div><dt>File access</dt><dd>Whitelisted frozen-release files only</dd></div>
      <div><dt>License / reuse</dt><dd>To be finalized before public deployment</dd></div>
      <div><dt>Preferred citation</dt><dd>To be added with the ODDB v1 publication</dd></div>
     </dl>
    </article>
   </div>
  </div>
 </section>

 <section class="container section-block">
  <div class="info-card release-notes-card">
   <div class="eyebrow">Release notes</div>
   <h2 class="h4 fw-bold mt-1">Drug &amp; clinical refinement highlights</h2>
   <div class="row g-3 mt-1">
    <div class="col-md-6">
     <ul class="release-note-list mb-0">
      <li>51 ChEMBL identity enrichments were incorporated.</li>
      <li>RETINOL was added as a distinct canonical entity where source evidence required separation from TRETINOIN.</li>
      <li>Clinical report and trial mappings were refined while preserving source identifiers and source names.</li>
     </ul>
    </div>
    <div class="col-md-6">
     <ul class="release-note-list mb-0">
      <li>Source-ID conflicts and unresolved identity cases remain explicitly flagged rather than silently overwritten.</li>
      <li>Direct disease–drug evidence remains separate from target-overlap discovery paths.</li>
      <li>The validated refined release passed with zero reported validation problems.</li>
     </ul>
    </div>
   </div>
  </div>
 </section>
</main>

<footer class="site-footer">
 <div class="container py-4 d-flex flex-column flex-md-row justify-content-between gap-2">
  <div class="small text-secondary">ODDB v1 · Ocular Disease Database</div>
  <div class="small text-secondary">Research resource · release-aware evidence layers</div>
 </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>
<script src="assets/data.js"></script>
<script src="assets/site-nav.js"></script>
</body>
</html>
