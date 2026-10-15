# ODDB: Ocular Disease Database

ODDB brings together ocular diseases, genes, variants, drugs, clinical trials and clinical evidence in an interactive research website. You can browse entities, explore their relationships and inspect the evidence behind individual connections.

**Website:** [www.oculardiseases.fi](https://www.oculardiseases.fi/)  
**Source code:** [UmairSeemab/ODDB](https://github.com/UmairSeemab/ODDB)

## Release overview

Source release: [`oddb-v1-2026-10-15`](https://github.com/UmairSeemab/ODDB/releases/tag/oddb-v1-2026-10-15). See the [release notes](docs/releases/oddb-v1-2026-10-15.md) for scope and reproducibility limits.

This source package captures the enriched application on **15 October 2026**. The following counts come from [the exported database table counts](schema/table_counts.tsv) and agree with the included current statistics snapshot.

| Entity or relationship | Records |
| --- | ---: |
| Diseases | 185 |
| Genes | 1,249 |
| Variants | 707,315 |
| Drugs | 893 |
| Clinical trials | 1,255 |
| Clinical reports | 1,382 |
| Disease–gene associations | 1,662 |
| Disease–variant associations | 106,838 |
| Drug–target associations | 1,009 |
| Direct disease–drug associations | 424 |

The database contains 36 base tables. These are release-specific record counts, rather than counts of independently verified findings or approved treatments. A clinical-report record is not necessarily a distinct publication. The counts for diseases, genes, variants and drugs describe separate entity tables, while association counts describe their links.

## Explore and analyse

- Search by Disease, Gene, Variant, Drug, Clinical Trial or Clinical Report.
- Browse disease anatomy and inheritance categories, gene categories and variant consequences.
- Expand networks and inspect entity details, source identifiers and evidence links.
- Hover over a network node to read its full label and entity type.
- Use buttons to zoom, move the graph and fit the view without a mouse wheel.
- Compare entities, filter evidence and investigate network paths.
- Save sessions and export network figures using the included analysis tools.
- Explore release statistics, rankings, chromosome distributions and clinical summaries.
- Browse current and historical download catalog entries on the Data & Release page.

The home page also includes a country-level visitor globe. The separate visitor service estimates daily visitors using daily tokens. Its counts are estimates, and country lookup is approximate. The web endpoint excludes collection for requests carrying Do Not Track or Global Privacy Control exclusion headers.

## Evidence and provenance

ODDB distinguishes disease-specific drug evidence from drug-target pharmacology and shared-target connections. A shared target supports exploration, rather than establishing a treatment indication. Trial participation does not establish efficacy or regulatory approval. A drug's maximum reported clinical stage does not establish approval for every connected ocular disease.

RetNet enrichment preserves source-reported disease–gene assertions and their acceptance status. Acceptance of an imported row does not establish independent verification of all supporting references. Inspect the source, evidence class and status when interpreting a connection.

The repository includes earlier data-preparation and validation scripts in [retnet_pipeline](retnet_pipeline/README.md), together with available source manifests. These files document parts of the preparation history. They are not a complete executable reconstruction of every subsequent enrichment step. Full reproduction also requires matching source snapshots, mappings, curation decisions and permitted data files.

The historical [PubMed/BioBERT extraction utility](NLP/README.md) is preserved separately. Its inclusion does not establish that its outputs contributed to this database release. See [its provenance statement](NLP/PROVENANCE.md).

## Repository layout

| Path | Contents |
| --- | --- |
| [app/public/](app/public/) | PHP pages and APIs, JavaScript, styles, images and chart snapshots |
| [app/config/](app/config/) | Download catalog, statistics snapshots and verification manifests |
| [services/visitors/](services/visitors/) | Visitor-service source, country labels and Dockerfile |
| [retnet_pipeline/](retnet_pipeline/) | Earlier scientific preparation, harmonisation and validation code |
| [NLP/](NLP/) | Historical literature-extraction utility and provenance |
| [schema/](schema/) | Base-table definitions and exact exported table counts |
| [deploy/](deploy/) and [compose.yaml](compose.yaml) | Earlier deployment definitions and server examples |
| [ops/](ops/) | Earlier deployment-management and validation helpers |
| [scripts/](scripts/) | Statistics verification and publication-inventory helpers |
| [tools/](tools/) | Source packaging and earlier staging/export helpers |
| [docs/](docs/) | Deployment, statistics, testing and publication documentation |
| [PUBLICATION_REPORT.json](PUBLICATION_REPORT.json) | Source-export provenance and packaging results |
| [package_manifest.json](package_manifest.json) and [SHA256SUMS.txt](SHA256SUMS.txt) | Exported file inventory and checksums |

## Architecture and requirements

The website uses PHP APIs with PDO MySQL to query MariaDB. JavaScript renders the interactive interface and Cytoscape networks. Statistics use precomputed release JSON, with hash and manifest checks in the statistics API. Interactive search and network APIs continue to query the database.

The included web Dockerfile uses PHP 8.4 with Apache, PDO MySQL and mbstring. The earlier database deployment definition uses MariaDB 11.4. The visitor-service Dockerfile uses Python 3.12. The publication packager requires Python 3.9 or later. Scientific scripts have their own requirements files. Some browser dependencies are loaded from a CDN.

The production deployment uses CSC cPouta, Docker and Nginx with HTTPS. GitHub hosts the source code. GitHub Pages cannot execute this PHP application.

### Local source review

You need a separately restored, matching database and an explicitly configured read-only database account. From the repository root, run the following in Bash. Set the database name and account to your own local values.

```bash
export ODDB_DB_HOST=127.0.0.1
export ODDB_DB_PORT=3306
export ODDB_DB_NAME=oddb_v1
export ODDB_DB_USER=oddb_reader
read -r -s -p 'Local database password: ' ODDB_DB_PASSWORD
echo
export ODDB_DB_PASSWORD
export ODDB_VISITOR_MODE=preview

php -S 127.0.0.1:8081 -t app/public
```

Open [http://127.0.0.1:8081/](http://127.0.0.1:8081/). This PHP server is for local review. Database-dependent features require the restored data. Downloads and country lookup require their separate assets.

### Deployment status of the packaged files

The included root Compose file and `ops/` helpers describe an earlier deployment. They do not configure the complete enriched application, including the added visitor service, enriched download mount and release-specific database. The optional Caddy profile also references a `deploy/Caddyfile` that is absent from this ZIP. This package has not been tested as a complete deployment on a clean host.

Start with [ENRICHMENT_PUBLICATION.md](docs/ENRICHMENT_PUBLICATION.md) when adapting the deployment. Treat older documentation as historical where it differs from this README or the packaged source.

Serve only `app/public/`. Configure database credentials privately and grant the web account read-only access. Keep download directories outside the document root. The download handler expects historical assets under `/srv/oddb/retnet_pipeline/releases` and current assets under `/srv/oddb/enrichment_downloads`.

The statistics API selects the internal release identifier `2026-10-15-enrichment-candidate`, which remains in the exported filenames. Its manifest is bound to the database name used during deployment. Restoring under a different name requires a correctly regenerated and validated snapshot manifest. Otherwise, the API uses its SQL fallback. Older statistics files in `app/config/` are retained historical snapshots.

Visitor collection additionally requires a private shared token, a writable private data directory, an independently supplied country database and explicitly trusted reverse-proxy addresses. Keep collection disabled during local and preview testing. See the visitor source and enrichment deployment documentation for configuration.

## Data availability and reproducibility

This repository contains application source, base-table schema definitions, release counts, statistics aggregates and download metadata. Full database records, downloadable research datasets, country-lookup ranges, visitor records, credentials and private hosting backups are excluded.

The schema export contains definitions for all 36 base tables. **Four database views are omitted.** Database rows, view definitions and other required assets must be supplied separately to reproduce the complete application. An empty schema cannot reproduce the curated database or its interactive results.

Use the current entries in [app/config/release_catalog.json](app/config/release_catalog.json) to identify matching enriched downloads. The inventory under `retnet_pipeline/releases/` describes historical release assets. Catalog entries do not mean the underlying files are bundled in this source archive.

Upstream data and third-party assets retain their own terms. Record source versions, attribution, access requirements and redistribution permissions when preparing a separate research-data archive.

## Checksums and validation

For the unmodified extracted publication package, run from its root:

```bash
sha256sum -c SHA256SUMS.txt
```

The original ZIP passed its CRC integrity check, and its listed SHA-256 checksums matched during review. These checks establish file integrity, rather than scientific validity or a successful clean-host deployment.

Replacing this README changes its checksum. After reviewing and staging the intended repository files, regenerate the inventory before committing:

```bash
git add README.md
python3 scripts/rebuild_oddb_publication_inventory.py
git add package_manifest.json SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
git diff --cached --stat
```

The inventory helper uses all Git-tracked files. Review that tracked set and the staged diff before publication. `PUBLICATION_REPORT.json` records the original export, not a later Git release or deployment test. See [TESTING.md](docs/TESTING.md) and [STATISTICS_ENHANCED.md](docs/STATISTICS_ENHANCED.md) for additional review guidance.

## Citation and license

Use [CITATION.cff](CITATION.cff) to cite ODDB, and identify the actual release tag or commit used in your research. Archive the reviewed version and cite its archive identifier when one is available. See [PUBLICATION.md](docs/PUBLICATION.md) for publication guidance.

Original ODDB software is distributed under the [MIT License](LICENSE). This license does not replace the licenses of upstream datasets, third-party assets or dependencies.
