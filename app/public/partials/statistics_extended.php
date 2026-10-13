<!-- ODDB v1 scientific statistics extensions; original Statistics features remain intact. -->
<section class="container section-block" id="scientific-landscape">
  <div class="section-heading">
    <div class="eyebrow">Scientific statistics</div>
    <h2 class="h3 fw-bold mb-1">Disease, gene and variant rankings</h2>
    <p class="text-secondary mb-0">Select Top 20, 30, 40 or a custom number, search records, reorder results and export publication-ready charts and tabular data. Stacked chromosome colors show the distribution within each canonical entity.</p>
  </div>
  <div id="oddb-enhanced-status" class="small text-secondary mt-3" role="status" aria-live="polite">Loading ODDB release-based statistics…</div>
  <div id="oddb-enhanced-rankings" class="oddb-enhanced-grid mt-3"></div>
</section>
<section class="container section-block" id="genomic-landscape">
  <div class="section-heading">
    <div class="eyebrow">Genomic landscape</div>
    <h2 class="h3 fw-bold mb-1">Chromosome and ocular disease category distributions</h2>
    <p class="text-secondary mb-0">Distinct disease-associated genes and variants. A gene or variant may contribute to more than one disease category, so totals across category memberships must not be treated as unique entities.</p>
  </div>
  <div id="oddb-enhanced-chromosomes" class="oddb-enhanced-grid mt-3"></div>
</section>
<section class="container section-block" id="clinical-landscape">
  <div class="section-heading">
    <div class="eyebrow">Clinical and therapeutic landscape</div>
    <h2 class="h3 fw-bold mb-1">Trials, candidate therapeutics and evidence</h2>
    <p class="text-secondary mb-0">Trial phases refer to the source clinical trial records, not each drug's maximum development stage. An association inferred from shared trial membership does not prove an indication or trial-arm assignment.</p>
  </div>
  <div id="oddb-enhanced-clinical" class="oddb-enhanced-grid mt-3"></div>
</section>
<section class="container section-block" id="disease-gene-drug-network">
  <div class="section-heading">
    <div class="eyebrow">Retinitis pigmentosa case study and interactive network</div>
    <h2 class="h3 fw-bold mb-1">Disease–gene–drug connectivity</h2>
    <p class="text-secondary mb-0">Select an ocular disease, explore disease–gene associations, direct disease–drug evidence and curated drug targets. Target-overlap-only edges are clearly separated from direct evidence.</p>
  </div>
  <article class="viz-card mt-3 oddb-network-card">
    <div class="oddb-network-controls">
      <label class="small" for="oddb-network-disease">Disease <select id="oddb-network-disease" class="form-select form-select-sm" aria-label="Choose disease for relationship network"></select></label>
      <label class="small" for="oddb-network-limit">Node selection limit <select id="oddb-network-limit" class="form-select form-select-sm"><option value="40">40</option><option value="80" selected>80</option><option value="120">120</option><option value="200">200</option></select></label>
      <label class="small oddb-network-checkbox"><input id="oddb-network-overlap" type="checkbox" checked> Include target-overlap-only hypotheses</label>
      <label class="small oddb-network-checkbox"><input id="oddb-network-labels" type="checkbox" checked> Show node names</label>
      <label class="small oddb-network-checkbox"><input id="oddb-network-organized" type="checkbox" checked> Organized gene/drug layout</label>
      <button type="button" class="btn btn-outline-primary btn-sm" id="oddb-network-rp">Retinitis pigmentosa preset</button>
      <button type="button" class="btn btn-outline-secondary btn-sm" id="oddb-network-reset">Reset view</button>
    </div>
    <div class="oddb-network-legend mt-2 small">
      <span><i class="oddb-dot oddb-dot-disease"></i> Disease</span>
      <span><i class="oddb-dot oddb-dot-gene"></i> Gene</span>
      <span><i class="oddb-dot oddb-dot-drug"></i> Drug</span>
      <span>Solid: observed links · Dashed: target-overlap-only discovery links</span>
    </div>
    <div id="oddb-network-note" class="small text-secondary mt-2" role="status" aria-live="polite"></div>
    <div id="oddb-network-graph" class="oddb-enhanced-network" role="img" aria-label="Interactive disease, gene and drug relationship network"></div>
    <div class="oddb-network-footer"><button type="button" class="btn btn-outline-secondary btn-sm" id="oddb-network-export">Export labeled PNG</button><button type="button" class="btn btn-outline-secondary btn-sm" id="oddb-network-svg">Export readable SVG</button><button type="button" class="btn btn-outline-secondary btn-sm" id="oddb-network-csv">Export links CSV</button></div>
    <p class="small text-secondary mb-0 mt-2">PNG saves the labeled interactive radial view. SVG uses a spacious, publication-friendly layout with all selected node names. Both include only the currently selected network.</p>
    <p class="small text-secondary mb-0 mt-2">Interpretation: target overlap supports candidate discovery only; it is not evidence of clinical benefit. Numbers and node visibility depend on the selected disease and limit.</p>
  </article>
</section>
