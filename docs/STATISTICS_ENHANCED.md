# ODDB v1 scientific statistics extension

This add-on *extends*, rather than replaces, `app/public/statistics.php`.
It preserves all original overview counts, inheritance, consequence,
clinical, Sankey and relationship maps, plus their existing export functions.

## New charts

1. Disease-associated gene ranking, stacked by gene chromosome
2. Disease-associated variant ranking, stacked by variant chromosome
3. Genes linked to the most distinct diseases
4. Diseases with the most distinct drugs linked through shared trials, stacked by reported phase
5. Drugs with the most diseases linked through shared trials, stacked by reported phase
6. Distinct disease-associated genes by chromosome and disease anatomy category
7. Distinct disease-associated variants by chromosome and disease anatomy category
8. Distinct associated genes per anatomy category, stacked by chromosome
9. Distinct associated variants per anatomy category, stacked by chromosome
10. Unique clinical trials grouped by raw source phase
11. Ocular disease anatomy memberships
12. Distinct disease–drug pairs by evidence class
13. On-demand disease–gene–drug network, defaulting to retinitis pigmentosa if present

All five ranking charts provide Top 20 / Top 30 / Top 40 / Custom / All,
search, ascending/descending sorting, and PNG / SVG / CSV export.
The other category-level charts display all relevant categories by default.

## Why snapshots?

Canonical ODDB records are source data, while the graphs are derived summaries.
Create static JSON **once per validated database release** using
`app/public/api/build_statistics_cli.php`. This PHP file rejects HTTP access
and is designed to run inside the ODDB web container, which has PDO MySQL,
read-only credentials and a network connection to the running MariaDB service.
The generated JSON must be committed/deployed alongside matching source.

Snapshot output lives in `app/public/assets/statistics_data/`:

- `rankings.json` — complete ranked entity arrays with breakdowns
- `chromosomes.json` — distinct gene/variant category/chromosome matrices
- `clinical.json` — unique trials, source phases, memberships, evidence types, disease menu
- `index.json` — release identity, canonical counts, import release keys, creation timestamp and SHA-256 hashes of the three data files

**Never** substitute invented sample data for a production statistics snapshot.

## Generating a new snapshot: staging first

Work on a copy or reviewed branch of the deployment source. Do not edit the
live application before reviewing the generated files and testing a separate
web container. The container build copies `app/public`, not `app/scripts`.

On **CSC cPouta**, after staging the new source under the deployment folder
but before replacing the live web container:

```bash
cd /srv/oddb/deployment/ODDB_cpouta
mkdir -p app/public/assets/statistics_data
sudo docker compose build web
sudo docker compose run --rm --no-deps \
  -v "$PWD/app/public/assets/statistics_data:/srv/oddb/app/public/assets/statistics_data" \
  web php /srv/oddb/app/public/api/build_statistics_cli.php
```

The one-off container uses the existing compose DB connection and runs the
read-only aggregation without switching the production web service. It writes
JSON to the staging bind mount. **Do not invoke `ops/manage.py publish`**:
production uses host Nginx and Certbot, not the optional Caddy service.

Copy generated JSON files back to the local Git working tree using `scp`
or `rsync`. Validate on **local Ubuntu**:

```bash
python3 scripts/verify_statistics_json.py app/public/assets/statistics_data
sha256sum --check --quiet SHA256SUMS.txt
```

The SHA256SUMS file must be regenerated once the JSON is added to the Git
release inventory (the second check is only meaningful after that step).
Do a final Gitleaks scan and review the SQL-derived totals against the
frozen September 30 release before pushing to GitHub or deploying live.

To test independently, use a temporary web container bound to localhost
without modifying the live public port. Do not run `docker compose up` or
restart Nginx until that acceptance test passes.

## Interpretation / caveats

- **Trials**: `clinical_trial.phase`, not `drug.maximum_clinical_stage`.
  A source `UNKNOWN` is kept separate from a NULL/blank
  `NO_PHASE_REPORTED`; no reinterpretation of raw strings.
- **Trial-linked drug/disease pairs**: co-membership in an NCT record;
  this does **not** assert that a drug was given for a particular disease,
  arm assignment, or evidence of clinical efficacy. The same pair may
  appear under multiple trial phases, so stacked phase counts may repeat.
- **Disease–gene associations**: count *distinct* HGNC gene identifiers,
  not association rows, which may differ by inheritance evidence.
- **Variants**: canonical variants from distinct disease-variant links.
  A reported variant may link to more than one disease.
- **Chromosomes**: fields come from the canonical gene / variant tables;
  unmatched values remain `Unmapped`. No reinterpretation of location.
- **Anatomy memberships**: ODDB's 12 localization categories are not
  necessarily mutually exclusive; per-category counts are not a total
  number of unique genes, variants or diseases.
- **Evidence types**: only direct disease–drug links are therapeutic
  evidence; target-overlap-only pairs are discovery hypotheses.
- **Focused graph**: generated on demand by a bounded read-only API;
  graph edge weights are not experimental effect sizes.

## Verification before source release and Zenodo

- All 12 charts and the network appear in responsive desktop/mobile views
- Ranking controls Top 20/30/40/custom/All, search and sort work
- Counts and CSV rows correspond to selected visible chart rows
- SVG/PNG exports open correctly; no extra browser console errors
- Trial phases exactly partition the 1,164 canonical unique trials
- Disease selector contains the 162 canonical disease records
- The generated JSON SHA-256 matches `index.json` and package checksums
- Old Statistics / Explore / nav features continue to work
- A CSC Allas backup exists and the live production restore procedure is preserved

**DO NOT** publish a Zenodo snapshot until the exact data JSON and source
revision have been included in the GitHub tagged release.
