<?php declare(strict_types=1); ?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="ODDB v1 documentation, data model, relationship semantics, identifiers, taxonomies and evidence interpretation guidance.">
<title>Documentation — ODDB v1</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="assets/documentation.css" rel="stylesheet">
<link href="assets/site-nav.css" rel="stylesheet">
<link href="assets/visual-refresh.css?v=0.8.0" rel="stylesheet">
</head>
<body class="oddb-visual oddb-documentation">
<?php require __DIR__ . "/partials/site_nav.php"; ?>

<header class="docs-hero">
 <div class="container py-4 py-md-5">
  <div class="row align-items-end g-4">
   <div class="col-lg-8">
    <div class="eyebrow">ODDB v1 documentation</div>
    <h1 class="display-5 fw-bold mb-2">Data model &amp; evidence semantics</h1>
    <p class="lead text-secondary mb-0">
     How ODDB represents ocular diseases, genes, variants, loci, drugs and clinical evidence without collapsing distinct biological or evidentiary concepts.
    </p>
   </div>
   <div class="col-lg-4">
    <div class="hero-callout">
     <strong>Current documented model</strong>
     <span>ODDB v1 enrichment release · 15 October 2026</span>
    </div>
   </div>
  </div>
 </div>
</header>

<main>
 <section class="container docs-shell mt-4">
  <aside class="docs-toc" aria-label="Documentation sections">
   <div class="toc-card">
    <div class="toc-title">On this page</div>
    <nav>
     <a href="#overview">Overview</a>
     <a href="#entities">Core entities</a>
     <a href="#model">Interactive data model</a>
     <a href="#relationships">Relationships</a>
     <a href="#taxonomies">Taxonomies</a>
     <a href="#evidence">Evidence interpretation</a>
     <a href="#identifiers">Identifiers &amp; provenance</a>
     <a href="#clinical-model">Clinical evidence model</a>
     <a href="#versioning">Release &amp; versioning</a>
     <a href="#explore-guide">Using Explore</a>
    </nav>
   </div>
  </aside>

  <div class="docs-content">
   <section id="overview" class="doc-section">
    <div class="eyebrow">Overview</div>
    <h2 class="h3 fw-bold mb-2">What ODDB v1 represents</h2>
    <p>
     ODDB v1 is a relational research resource for ocular diseases and their molecular, variant, therapeutic and clinical evidence. The released model keeps biologically different entities separate and preserves the provenance needed to understand how each relationship was established.
    </p>
    <div class="principle-grid">
     <article class="principle-card">
      <strong>Separate entities</strong>
      <span>Diseases, genes, variants, loci, drugs, trials and clinical reports are modeled independently.</span>
     </article>
     <article class="principle-card">
      <strong>Separate evidence layers</strong>
      <span>Direct disease–drug evidence is not merged with drug–target overlap discovery.</span>
     </article>
     <article class="principle-card">
      <strong>Preserve provenance</strong>
      <span>Source identifiers, evidence context and frozen release provenance are retained.</span>
     </article>
     <article class="principle-card">
      <strong>Do not infer unsupported links</strong>
      <span>For example, a disease–variant link is not created merely because the variant occurs in a disease-associated gene.</span>
     </article>
    </div>
   </section>

   <section id="entities" class="doc-section">
    <div class="eyebrow">Core entities</div>
    <h2 class="h3 fw-bold mb-2">Current released entity layers</h2>
    <p class="text-secondary">Counts below describe the deployed ODDB v1 enrichment release. Counts are captured from its database when this deployment image is built.</p>

    <div class="entity-grid">
     <article class="entity-card entity-disease">
      <div class="entity-icon">D</div>
      <div>
       <h3>Disease</h3>
       <div class="entity-count">185 canonical diseases</div>
       <p>Canonical ocular disease concepts used as the central disease layer for genetics, variants, therapeutics and clinical evidence.</p>
      </div>
     </article>

     <article class="entity-card entity-gene">
      <div class="entity-icon">G</div>
      <div>
       <h3>Gene</h3>
       <div class="entity-count">1,249 genes</div>
       <p>HGNC-aligned gene entities. Non-gene loci and regulatory labels are not treated as genes.</p>
      </div>
     </article>

     <article class="entity-card entity-variant">
      <div class="entity-icon">V</div>
      <div>
       <h3>Variant</h3>
       <div class="entity-count">707,315 variants</div>
       <p>Canonical variant records connected to genes and, where explicit evidence exists, to diseases.</p>
      </div>
     </article>

     <article class="entity-card entity-locus">
      <div class="entity-icon">L</div>
      <div>
       <h3>Locus</h3>
       <div class="entity-count">2 structural loci</div>
       <p>Non-gene genetic entities retained outside the HGNC gene layer to prevent contamination of gene comparisons.</p>
      </div>
     </article>

     <article class="entity-card entity-drug">
      <div class="entity-icon">Rx</div>
      <div>
       <h3>Drug</h3>
       <div class="entity-count">893 canonical drugs</div>
       <p>Canonical therapeutic entities with explicit drug-form relationships and separate disease and target evidence.</p>
      </div>
     </article>

     <article class="entity-card entity-trial">
      <div class="entity-icon">T</div>
      <div>
       <h3>Clinical Trial</h3>
       <div class="entity-count">1,255 trials</div>
       <p>Trial entities linked independently to diseases and drugs, avoiding unsupported disease×drug cross-products.</p>
      </div>
     </article>

     <article class="entity-card entity-report">
      <div class="entity-icon">R</div>
      <div>
       <h3>Clinical Report</h3>
       <div class="entity-count">1,382 reports</div>
       <p>Clinical evidence report entities modeled separately from trials and linked through many-to-many disease/drug associations.</p>
      </div>
     </article>
    </div>
   </section>

   <section id="model" class="doc-section">
    <div class="section-heading-row">
     <div>
      <div class="eyebrow">Interactive data model</div>
      <h2 class="h3 fw-bold mb-2">How the released layers connect</h2>
      <p class="text-secondary mb-0">Choose a layer or select a node. Pan and zoom the diagram on desktop or touch devices.</p>
     </div>
     <button id="resetModel" type="button" class="btn btn-outline-secondary btn-sm">Reset view</button>
    </div>

    <div class="model-filter" role="group" aria-label="Filter data model">
     <button class="model-chip active" type="button" data-model-filter="all">All layers</button>
     <button class="model-chip" type="button" data-model-filter="genetics">Genetics</button>
     <button class="model-chip" type="button" data-model-filter="therapeutics">Therapeutics</button>
     <button class="model-chip" type="button" data-model-filter="clinical">Clinical evidence</button>
    </div>

    <div class="model-layout">
     <div class="model-canvas-wrap">
      <div id="oddbModelChart" class="model-chart" role="img"
           aria-label="Interactive graph of ODDB v1 entities and relationships"></div>
     </div>

     <aside id="modelDetail" class="model-detail" aria-live="polite">
      <div class="model-detail-eyebrow">Select an entity</div>
      <h3 class="h5">ODDB v1 relational model</h3>
      <p>Click or tap a node to inspect its role and the relationships that connect it to other ODDB entities.</p>
      <div class="model-detail-note">The relationship table below provides a complete text-accessible description of the same model.</div>
     </aside>
    </div>
   </section>

   <section id="relationships" class="doc-section">
    <div class="eyebrow">Relationships</div>
    <h2 class="h3 fw-bold mb-2">Released association layers</h2>
    <p class="text-secondary">Association counts are row counts in the deployed enrichment release unless otherwise stated.</p>

    <div class="table-responsive relationship-table-wrap">
     <table class="table relationship-table align-middle mb-0">
      <thead>
       <tr>
        <th>Relationship</th>
        <th>Count</th>
        <th>Meaning</th>
        <th>Interpretation rule</th>
       </tr>
      </thead>
      <tbody>
       <tr><td>Disease–Gene Association</td><td>1,662</td><td>Links a disease to a supported gene.</td><td>Stable association identity includes DiseaseID + HGNC_ID + inheritance context.</td></tr>
       <tr><td>Gene–Variant Association</td><td>707,315</td><td>Links a variant to its associated gene.</td><td>Does not by itself establish disease relevance.</td></tr>
       <tr><td>Disease–Variant Association</td><td>106,838</td><td>Explicit disease–variant evidence.</td><td>Never inferred solely from disease–gene membership.</td></tr>
       <tr><td>Disease–Locus Association</td><td>2</td><td>Links disease to a non-gene locus.</td><td>Locus entities remain separate from HGNC genes.</td></tr>
       <tr><td>Drug–Target Association</td><td>1,009</td><td>Molecular pharmacology between drug and gene target.</td><td>Target evidence is not equivalent to disease-specific therapeutic evidence.</td></tr>
       <tr><td>Disease–Drug Association</td><td>424</td><td>Disease-specific evidence, including registered clinical investigation. Efficacy is not implied.</td><td>Kept separate from target-overlap discovery.</td></tr>
       <tr><td>Disease–Drug Evidence</td><td>1,299</td><td>Evidence records supporting disease–drug context.</td><td>Evidence records should not be reduced to target overlap alone.</td></tr>
       <tr><td>Drug Form Relationship</td><td>99</td><td>Connects parent drugs with salts/forms.</td><td>Drug forms are not silently collapsed into a parent entity.</td></tr>
       <tr><td>Disease–Clinical Trial</td><td>1,342</td><td>Many-to-many disease links to trial entities.</td><td>A trial association does not prove efficacy or approval.</td></tr>
       <tr><td>Drug–Clinical Trial</td><td>1,566</td><td>Many-to-many drug links to trial entities.</td><td>Do not cross-product trial diseases and drugs into asserted treatment pairs.</td></tr>
       <tr><td>Disease–Clinical Report</td><td>1,370</td><td>Many-to-many disease links to clinical reports.</td><td>Source context is retained at report level.</td></tr>
       <tr><td>Drug–Clinical Report</td><td>1,575</td><td>Many-to-many drug links to clinical reports.</td><td>Source drug IDs and names remain preserved after canonical mapping.</td></tr>
      </tbody>
     </table>
    </div>
   </section>

   <section id="taxonomies" class="doc-section">
    <div class="eyebrow">Taxonomies</div>
    <h2 class="h3 fw-bold mb-2">Web-facing classification systems</h2>

    <div class="taxonomy-grid">
     <article class="taxonomy-card">
      <span class="taxonomy-badge">Disease</span>
      <h3>Anatomy / localization</h3>
      <p>Diseases may belong to more than one curated ocular localization group. Counts by category can therefore exceed the number of distinct diseases.</p>
      <div class="taxonomy-foot">12 localization categories · 185/185 diseases classified · 187 memberships</div>
     </article>

     <article class="taxonomy-card">
      <span class="taxonomy-badge">Disease</span>
      <h3>Inheritance</h3>
      <p>Inheritance is evidence-supported and may be multi-valued. Missing support is shown as not classified rather than guessed.</p>
      <div class="taxonomy-foot">AD · AR · mitochondrial · other · XLD · XLR</div>
     </article>

     <article class="taxonomy-card">
      <span class="taxonomy-badge">Gene</span>
      <h3>Gene category</h3>
      <p>Gene categories are applied to true gene entities only. Structural/regulatory loci remain outside the gene category layer.</p>
      <div class="taxonomy-foot">Used in gene landscape and relationship visualizations</div>
     </article>

     <article class="taxonomy-card">
      <span class="taxonomy-badge">Variant</span>
      <h3>Variant consequence</h3>
      <p>Variant annotations are normalized into the ODDB consequence taxonomy while retaining zero-count categories in the taxonomy itself.</p>
      <div class="taxonomy-foot">21 consequence categories · 1,400 canonical variants currently annotated</div>
     </article>

     <article class="taxonomy-card">
      <span class="taxonomy-badge">Drug</span>
      <h3>Clinical development stage</h3>
      <p>Source-reported trial/development stage is displayed conservatively and is not converted into an independent claim of regulatory approval.</p>
      <div class="taxonomy-foot">Includes explicit unknown/no-stage states</div>
     </article>
    </div>
   </section>

   <section id="evidence" class="doc-section">
    <div class="eyebrow">Evidence interpretation</div>
    <h2 class="h3 fw-bold mb-2">Rules that prevent over-interpretation</h2>

    <div class="evidence-rule-list">
     <article>
      <div class="rule-number">01</div>
      <div><h3>Target overlap is discovery, not treatment evidence</h3><p>A disease-associated gene that is also a drug target creates a discovery relationship only. It does not automatically establish that the drug treats the disease.</p></div>
     </article>
     <article>
      <div class="rule-number">02</div>
      <div><h3>Target action direction matters</h3><p>Agonism, antagonism, inhibition and other target actions cannot be assumed to be therapeutically compatible merely because the same gene appears in disease and drug-target layers.</p></div>
     </article>
     <article>
      <div class="rule-number">03</div>
      <div><h3>Variant classification is not gene–disease validity</h3><p>Variant-level clinical interpretation and gene–disease validity are distinct evidence concepts and are not substituted for one another.</p></div>
     </article>
     <article>
      <div class="rule-number">04</div>
      <div><h3>Parent disease mapping is not subtype mapping</h3><p>Disease hierarchy or parent mapping does not automatically justify assigning all evidence to a more specific subtype.</p></div>
     </article>
     <article>
      <div class="rule-number">05</div>
      <div><h3>Clinical investigation is not approval or efficacy</h3><p>A clinical trial, report or source-reported maximum development phase indicates investigation context, not proof of therapeutic benefit or independent regulatory approval.</p></div>
     </article>
     <article>
      <div class="rule-number">06</div>
      <div><h3>Conflicts remain visible</h3><p>Source identifier conflicts and unresolved canonical mappings are flagged for review rather than silently overwritten.</p></div>
     </article>
    </div>
   </section>

   <section id="identifiers" class="doc-section">
    <div class="eyebrow">Identifiers &amp; provenance</div>
    <h2 class="h3 fw-bold mb-2">Traceable source-aware records</h2>

    <div class="identifier-grid">
     <article class="identifier-card">
      <h3>Disease identifiers</h3>
      <p>Canonical ODDB disease IDs provide stable internal references while source names, aliases and history are preserved.</p>
     </article>
     <article class="identifier-card">
      <h3>Gene identifiers</h3>
      <p>HGNC identifiers anchor canonical gene entities. Non-gene labels from legacy sources are classified separately using genetic entity type.</p>
     </article>
     <article class="identifier-card">
      <h3>Variant identifiers</h3>
      <p>Variant records retain source identifiers and can link outward to resources such as dbSNP, Ensembl and gnomAD where available.</p>
     </article>
     <article class="identifier-card">
      <h3>Drug identifiers</h3>
      <p>Canonical drug identity can be enriched from sources such as ChEMBL while original source drug IDs and names remain preserved.</p>
     </article>
     <article class="identifier-card">
      <h3>Publication evidence</h3>
      <p>PMID/DOI and evidence-source information are retained where available to keep curation traceable to source evidence.</p>
     </article>
     <article class="identifier-card">
      <h3>Frozen source record</h3>
      <p>Normalized MySQL rows retain the complete frozen TSV source row in <code>source_record_json</code> together with source file and source release metadata.</p>
     </article>
    </div>
   </section>

   <section id="clinical-model" class="doc-section">
    <div class="eyebrow">Clinical evidence model</div>
    <h2 class="h3 fw-bold mb-2">Reports and trials are relational entities</h2>
    <div class="clinical-model-card">
     <div class="clinical-example">
      <div class="clinical-node">Disease A</div>
      <div class="clinical-node">Disease B</div>
      <div class="clinical-center">Clinical trial / report</div>
      <div class="clinical-node">Drug X</div>
      <div class="clinical-node">Drug Y</div>
     </div>
     <div>
      <h3 class="h5">Why ODDB does not create a cross-product</h3>
      <p>A single trial or report may mention multiple diseases and multiple drugs. ODDB stores disease→report/trial and drug→report/trial links independently.</p>
      <p class="mb-0">This avoids asserting four disease–drug treatment relationships merely because two diseases and two drugs co-occur in the same source record.</p>
     </div>
    </div>
   </section>

   <section id="versioning" class="doc-section">
    <div class="eyebrow">Release &amp; versioning</div>
    <h2 class="h3 fw-bold mb-2">Frozen releases remain immutable</h2>

    <div class="version-flow">
     <div class="version-step">
      <span>1</span><div><strong>Source ingestion &amp; curation</strong><small>Normalize entities, preserve evidence and flag unresolved conflicts.</small></div>
     </div>
     <div class="version-arrow">→</div>
     <div class="version-step">
      <span>2</span><div><strong>Validation</strong><small>Run structural and semantic checks before release freeze.</small></div>
     </div>
     <div class="version-arrow">→</div>
     <div class="version-step">
      <span>3</span><div><strong>Frozen ODDB v1 release</strong><small>Release files are not modified after validation.</small></div>
     </div>
     <div class="version-arrow">→</div>
     <div class="version-step">
      <span>4</span><div><strong>Derived web curation</strong><small>Display/taxonomy corrections can evolve without rewriting frozen data.</small></div>
     </div>
    </div>

    <div class="release-links mt-3">
     <a class="btn btn-primary btn-sm" href="data.php">View Data &amp; release</a>
     <a class="btn btn-outline-secondary btn-sm" href="statistics.php">View Statistics</a>
    </div>
   </section>

   <section id="explore-guide" class="doc-section">
    <div class="eyebrow">Using Explore</div>
    <h2 class="h3 fw-bold mb-2">How to interpret an ODDB search result</h2>
    <div class="explore-steps">
     <article><span>1</span><div><strong>Search a canonical entity</strong><p>Start with a disease, gene, variant or drug name/identifier.</p></div></article>
     <article><span>2</span><div><strong>Read direct associations first</strong><p>Use explicit disease–gene, disease–variant and direct disease–drug evidence before discovery-only relationships.</p></div></article>
     <article><span>3</span><div><strong>Inspect provenance</strong><p>Use source identifiers and evidence context to understand where the relationship came from.</p></div></article>
     <article><span>4</span><div><strong>Treat target overlap as hypothesis-generating</strong><p>Target-overlap paths can suggest opportunities for investigation but are not equivalent to disease-specific treatment evidence.</p></div></article>
    </div>
    <a class="btn btn-primary mt-3" href="explore.php">Open Explore</a>
   </section>

   <section class="doc-section doc-end">
    <div>
     <div class="eyebrow">Scope note</div>
     <h2 class="h4 fw-bold">Research resource, not clinical guidance</h2>
     <p class="mb-0">ODDB is designed for research exploration and evidence organization. Database relationships should not be used as a substitute for clinical diagnosis, treatment recommendations or regulatory information.</p>
    </div>
   </section>
  </div>
 </section>
</main>

<footer class="site-footer">
 <div class="container py-4 d-flex flex-column flex-md-row justify-content-between gap-2">
  <div class="small text-secondary">ODDB v1 · Ocular Disease Database</div>
  <div class="small text-secondary">Documentation for the released relational model</div>
 </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>
<script src="assets/documentation.js?v=23"></script>
<script src="assets/site-nav.js"></script>
</body>
</html>
