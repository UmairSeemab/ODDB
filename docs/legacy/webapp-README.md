# ODDB v1 Web App v0.3

This release rebuilds the original ODDB categorization browser on top of the
validated `oddb_v1` MySQL backend.

## Browsing model

Two independent choices:

**Disease categorization**
- Anatomy Based Categorization
- Inheritance Based Categorization

**Data view**
- Gene Based
- Variant Based

### Anatomy categories
1. Refractive Errors
2. Retinal Diseases
3. Others
4. Lens Diseases
5. Ocular Hypertension
6. Ocular Motility Disorders
7. Uveal Diseases
8. Corneal Diseases
9. Conjunctival Diseases
10. Orbital Diseases
11. Eye Neoplasms
12. Lacrimal Apparatus Diseases

### Inheritance categories
1. Autosomal dominant
2. Autosomal recessive
3. Isolated cases
4. Mitochondrial
5. Other
6. X-linked dominant
7. X-linked recessive

### Gene-based subtypes
- Pseudogene
- Genetic Locus
- lncRNA
- miRNA
- mt_tRNA
- Other
- Protein coding
- RNA gene

`Genetic Locus` remains a separate relational entity internally.

### Variant consequences
The 21 unique controlled consequence categories supplied for ODDB are seeded.
The duplicated `frameshift variant` entry is represented once.

The application **does not infer** a molecular consequence from a generic
ClinVar structural variant type. The backfill only accepts exact controlled
source values already present in ODDB source fields.

## 1. Apply the web taxonomy migration

From this web-app directory:

```bash
/opt/lampp/bin/mysql \
  -h 127.0.0.1 \
  -P 3306 \
  -u root \
  oddb_v1 \
  < sql/001_web_taxonomy.sql
```

## 2. Populate categories and external links

With the same Python environment used for the ODDB importer:

```bash
python scripts/backfill_web_taxonomy.py
```

The output reports counts for every category. Review it before public
deployment. Zero counts mean the current normalized source data did not contain
an exact value that safely maps to that controlled category; the script does not
invent classifications.

## 3. Run locally

```bash
cd public

ODDB_DB_HOST=127.0.0.1 \
ODDB_DB_PORT=3306 \
ODDB_DB_NAME=oddb_v1 \
ODDB_DB_USER=root \
ODDB_DB_PASSWORD='' \
/opt/lampp/bin/php -S 127.0.0.1:8081
```

Open:

```text
http://127.0.0.1:8081/
```

## External links

v0.3 builds deterministic links from canonical identifiers:

- Gene: HGNC, Ensembl, NCBI Gene, GeneCards
- Variant: ClinVar, dbSNP
- Drug: ChEMBL, DrugBank, PubChem
- Trial: ClinicalTrials.gov
- Disease: MONDO and OMIM when present

It also scans preserved source JSON for explicit URL/link fields.

The exact links from the original legacy Excel/ZIP should still be imported
when that original spreadsheet is available. They should be retained rather
than replaced by guesses.

## Evidence semantics

- Disease–drug direct evidence = disease-specific therapeutic/clinical evidence.
- Drug–gene edges = molecular pharmacology.
- Target-overlap-only edges = discovery context, not treatment assertions.
- Trial investigation is not automatically approval.
- Disease–variant evidence stays separate from disease–gene validity.

## Deployment

Recommended production arrangement:

```text
GitHub repository
      |
      | source control / release tags
      v
CSC or existing server
      |
      +-- PHP frontend/API
      +-- private MySQL oddb_v1
      |
      v
https://oculardiseases.fi
```

Do not expose MySQL to the public internet and do not commit credentials to
GitHub.
