<?php declare(strict_types=1); ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="ODDB — Ocular Disease Database. Explore ocular diseases, genes, variants, drugs, therapeutic evidence and clinical trials.">
<title>ODDB — Ocular Disease Database</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/landing.css" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/intro-short-v0.8.5.css" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
<noscript><style>body.oddb-home.oddb-intro-lock{overflow:auto!important}body.oddb-home #oddbIntro{display:none!important}</style></noscript>
<link href="assets/home-banner.css?v=0.8.2" rel="stylesheet">
<!-- ODDB two-second intro v0.8.5 -->
<script>
(() => {
 'use strict';
 try {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || window.location.hash) return;
  const replay = new URLSearchParams(window.location.search).get('intro') === '1';
  let seen = false;
  try {seen = sessionStorage.getItem('oddbIntroSeenThisSession') === '1';} catch (_) {}
  if (seen && !replay) return;
  try {sessionStorage.setItem('oddbIntroSeenThisSession','1');} catch (_) {}
  window.__oddbIntroDeadline = performance.now() + 2000;
  document.documentElement.classList.add('oddb-intro-pending');
  // This independent timer also uncovers Home if the external script fails.
  window.__oddbIntroFallback = window.setTimeout(() => {
   if (window.__oddbFinishIntro) window.__oddbFinishIntro();
   else {
    document.documentElement.classList.remove('oddb-intro-pending');
    const intro = document.getElementById('oddbIntro');
    if (intro) intro.setAttribute('aria-hidden','true');
   }
  },2000);
 } catch (_) {document.documentElement.classList.remove('oddb-intro-pending');}
})();
</script>
<link rel="stylesheet" href="assets/visitors23.css?v=23">
</head>
<body class="oddb-visual oddb-home">
<div id="oddbIntro" class="oddb-short-intro" role="dialog" aria-modal="true" aria-labelledby="oddbIntroTitle" aria-hidden="true">
 <button type="button" class="intro-skip" data-intro-skip>Skip intro</button>
 <div class="oddb-short-shell">
  <h2 id="oddbIntroTitle" class="oddb-short-title">Ocular Disease Database</h2>
  <img class="oddb-short-eye" src="assets/oddb-eye-front.svg?v=0.8.5" width="800" height="520" alt="" fetchpriority="high">
  <p class="oddb-short-caption">Diseases · genes · variants · therapeutics · clinical evidence</p>
  <div class="oddb-short-progress" aria-hidden="true"><span></span></div>
 </div>
</div>

<?php require __DIR__ . "/partials/site_nav.php"; ?>

<header class="hero oddb-image-banner">
 <div class="container py-5 py-lg-6">
  <div class="row align-items-center g-5">
   <div class="col-lg-6 oddb-banner-content">
    <div class="eyebrow">Ocular Disease Database</div>
    <h1 class="display-4 fw-bold mt-2">Connect ocular diseases with genetics, variants and therapeutic evidence.</h1>
    <p class="lead text-secondary mt-3 mb-4">
     ODDB is an evidence-aware resource integrating ocular diseases, genes, variants,
     drugs, molecular targets and clinical trials in a unified platform.
    </p>

    <div class="d-flex flex-wrap gap-2">
     <a href="explore.php" class="btn btn-primary btn-lg px-4">Explore ODDB</a>
     <a href="#release" class="btn btn-outline-secondary btn-lg px-4">Data & release</a>
    </div>
   </div>


  </div>
 </div>
</header>
<section class="oddb-banner-summary" aria-label="ODDB knowledge graph overview">
 <div class="container py-4">
   <div class="oddb-banner-overview">
    <div class="hero-panel">
     <div class="small text-uppercase fw-bold text-secondary mb-3">ODDB knowledge graph</div>
     <div class="mini-network" aria-hidden="true">
      <div class="net-node disease">Disease</div>
      <div class="net-node gene">Gene</div>
      <div class="net-node variant">Variant</div>
      <div class="net-node drug">Drug</div>
      <div class="net-node trial">Trial</div>
      <span class="net-line l1"></span>
      <span class="net-line l2"></span>
      <span class="net-line l3"></span>
      <span class="net-line l4"></span>
     </div>
     <p class="small text-secondary mb-0 mt-3">
      Direct disease–drug evidence is kept distinct from target-overlap discovery relationships.
     </p>
    </div>
   </div>
 </div>
</section>

<section id="stats" class="stats-band border-top border-bottom">
 <div class="container py-4">
  <div class="row g-3 text-center">
   <div class="col-6 col-md-4 col-xl"><div class="stat-card"><div class="stat-number" data-stat="diseases">—</div><div class="stat-label">Diseases</div></div></div>
   <div class="col-6 col-md-4 col-xl"><div class="stat-card"><div class="stat-number" data-stat="genes">—</div><div class="stat-label">Genes</div></div></div>
   <div class="col-6 col-md-4 col-xl"><div class="stat-card"><div class="stat-number" data-stat="variants">—</div><div class="stat-label">Variants</div></div></div>
   <div class="col-6 col-md-4 col-xl"><div class="stat-card"><div class="stat-number" data-stat="drugs">—</div><div class="stat-label">Drugs</div></div></div>
   <div class="col-6 col-md-4 col-xl"><div class="stat-card"><div class="stat-number" data-stat="trials">—</div><div class="stat-label">Clinical trials</div></div></div>
   
  </div>
 </div>
</section>

<main>
 <section class="section-space">
  <div class="container">
   <div class="section-heading">
    <div class="eyebrow">Explore the database</div>
    <h2 class="h1 fw-bold">Start with the scientific question you have.</h2>
    <p class="text-secondary">Move between diseases, genes, variants, drugs, clinical trials and supporting evidence.</p>
   </div>
   <div class="row g-3">
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php"><span class="explore-icon disease">D</span><span><strong>Diseases</strong><small>Browse by anatomy or inheritance.</small></span><span class="arrow">→</span></a></div>
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php?mode=gene"><span class="explore-icon gene">G</span><span><strong>Genes</strong><small>Explore disease genes and molecular targets.</small></span><span class="arrow">→</span></a></div>
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php?mode=variant"><span class="explore-icon variant">V</span><span><strong>Variants</strong><small>Browse disease-linked variants and consequences.</small></span><span class="arrow">→</span></a></div>
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php"><span class="explore-icon drug">Rx</span><span><strong>Drugs & therapeutics</strong><small>Direct evidence and molecular targets.</small></span><span class="arrow">→</span></a></div>
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php"><span class="explore-icon trial">CT</span><span><strong>Clinical trials</strong><small>Investigational drugs and disease links.</small></span><span class="arrow">→</span></a></div>
    <div class="col-md-6 col-xl-4"><a class="explore-card" href="explore.php"><span class="explore-icon network">◎</span><span><strong>Network explorer</strong><small>Visualize evidence-connected entities.</small></span><span class="arrow">→</span></a></div>
   </div>
  </div>
 </section>

 <section class="section-space bg-white border-top border-bottom">
  <div class="container">
   <div class="row g-5">
    <div class="col-lg-7">
     <div class="eyebrow">Explore ocular diseases</div>
     <h2 class="h2 fw-bold">Browse by anatomy</h2>
     <p class="text-secondary">The canonical disease universe organized by ocular localization.</p>
     <div id="anatomyPreview" class="taxonomy-preview"><span class="text-secondary small">Loading…</span></div>
    </div>
    <div class="col-lg-5">
     <div class="eyebrow">Genetic classification</div>
     <h2 class="h2 fw-bold">Browse by inheritance</h2>
     <p class="text-secondary">Only directly supported disease-level inheritance memberships are shown.</p>
     <div id="inheritancePreview" class="taxonomy-preview"><span class="text-secondary small">Loading…</span></div>
     <p class="small text-secondary mt-3 mb-0">
      Diseases without a direct supported inheritance classification remain in ODDB and are not forced into a category.
     </p>
    </div>
   </div>
  </div>
 </section>

 <section id="release" class="section-space">
  <div class="container">
   <div class="release-card">
    <div class="row align-items-center g-4">
     <div class="col-lg-8">
      <div class="eyebrow text-info">Current data release</div>
      <h2 class="h2 fw-bold mb-2">ODDB v1</h2>
      <p class="mb-2 release-muted">Validated genetics, variant, drug, therapeutic-evidence and clinical-trial layers.</p>
      <div class="small release-muted">Refined drug/clinical release: 30 September 2026</div>
     </div>
     <div class="col-lg-4 text-lg-end">
      <a href="explore.php" class="btn btn-light">Explore current data</a>
      <span class="d-block small release-muted mt-2">Downloads and documentation will be added next.</span>
     </div>
    </div>
   </div>
  </div>
 </section>

 <section id="about" class="section-space bg-white border-top">
  <div class="container">
   <div class="row g-5 align-items-start">
    <div class="col-lg-7">
     <div class="eyebrow">About ODDB</div>
     <h2 class="h2 fw-bold">Evidence-aware ocular disease data.</h2>
     <p class="text-secondary">
      ODDB brings together disease genetics, variants, therapeutic evidence, drug targets and clinical trials.
      The platform preserves provenance and distinguishes direct therapeutic evidence from target-overlap discovery.
     </p>
    </div>
    <div class="col-lg-5">
     <div class="usage-placeholder">
      <div class="eyebrow">ODDB around the world</div>
      <h3 class="h5 fw-bold mt-2">Visitor analytics will be added after production deployment.</h3>
      <p class="small text-secondary mb-0">
       The public site can later show privacy-conscious, aggregated visitor counts and country-level usage.
      </p>
     </div>
    </div>
   </div>

   <details id="oddbAboutFigures">
    <summary>View eye anatomy and ocular disease groups</summary>
    <div class="oddb-about-figure-grid">
     <figure>
      <img data-src="assets/oddb-eye-anatomy.svg" width="941" height="1672" alt="Eye anatomy: lacrimal apparatus, conjunctiva, cornea, lens, uvea, retina and optic nerve." loading="lazy" decoding="async">
      <figcaption>The human eye and its labelled structures.</figcaption>
     </figure>
     <figure>
      <img data-src="assets/oddb-eye-diseases.svg" width="941" height="1672" alt="Ocular disease groups: lacrimal, conjunctival, corneal, refractive, lens, uveal, retinal, orbital, ocular motility, eye neoplasms, ocular hypertension and others." loading="lazy" decoding="async">
      <figcaption>Ocular disease groups displayed by anatomy.</figcaption>
     </figure>
    </div>
    <noscript><p><a href="assets/oddb-eye-anatomy.svg">Open the anatomy figure</a> · <a href="assets/oddb-eye-diseases.svg">Open the disease-groups figure</a></p></noscript>
   </details>
  </div>
 </section>
<section id="oddbVisitors23" class="visitor23" aria-labelledby="visitorTitle23">
 <div class="container py-5">
  <div class="visitor23-heading"><div><div class="eyebrow">ODDB around the world</div><h2 id="visitorTitle23">A global research community</h2><p>Explore where ODDB is being accessed.</p></div><span class="visitor23-badge">Country-level activity</span></div>
  <div class="visitor23-grid">
   <div class="visitor23-planet"><canvas id="visitorGlobe23" role="img" aria-label="Rotatable globe showing aggregate country activity"></canvas><div class="visitor23-globe-label">Drag to rotate the globe</div><div class="visitor23-controls"><button type="button" id="visitorWest23" aria-label="Rotate globe west">←</button><button type="button" id="visitorReset23">Reset globe</button><button type="button" id="visitorEast23" aria-label="Rotate globe east">→</button></div></div>
   <div><div class="visitor23-counters"><div><strong id="visitorViews23">—</strong><span>Page views since counting started</span></div><div><strong id="visitorToday23">—</strong><span>Estimated visitors today (UTC)</span></div><div><strong id="visitorCountries23">—</strong><span>Countries reached</span></div></div>
    <p id="visitorYou23" class="visitor23-you">Your approximate country: checking…</p>
    <p id="visitorStatus23" role="status">Loading visitor statistics…</p>
    <div class="visitor23-table"><table><caption>Country activity since visitor counting started</caption><thead><tr><th scope="col">Country</th><th scope="col">Page views</th><th scope="col">Today*</th></tr></thead><tbody id="visitorRows23"></tbody></table></div>
   </div>
  </div>
  <details class="visitor23-method"><summary>How these statistics work</summary><p>*Today means estimated daily visitors, based on a daily-changing token derived from an IP address and browser type. Shared networks, VPNs and changing addresses affect this estimate. Daily visitors are not verified individual people. Known bots and rapid repeats are filtered. No historical totals are inferred.</p><p>Only country totals are displayed. Globe dots represent countries, not individual people or precise positions. Raw IP addresses, search terms and referrers are not retained by this feature. Daily deduplication tokens expire at the next day’s first counted visit. Browsers requesting Do Not Track or Global Privacy Control are excluded from counting. Existing hosting access logs are separate.</p><p>Country lookup runs locally using <a href="https://db-ip.com" rel="noopener">IP Geolocation by DB-IP</a> (October 2026, CC BY 4.0). Map: <a href="https://www.naturalearthdata.com/" rel="noopener">Natural Earth</a>. Country locations can be inaccurate, especially with VPNs.</p></details>
 </div>
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
<script src="assets/landing.js?v=23"></script>
<script src="assets/site-nav.js"></script>
<script src="assets/intro-short-v0.8.5.js" defer></script>
<script src="assets/visitors23.js?v=23" defer></script>
</body>
</html>
