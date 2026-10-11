# ODDB RetNet harmonization pipeline

Snapshot date: 2026-09-28

This folder stages current RetNet summary information for ODDB curation. It does **not** automatically promote RetNet-derived associations into the public ODDB dataset. RetNet is used as a discovery/completeness source; each candidate must be independently verified against primary literature and/or authoritative resources before public promotion.

## Current snapshot

- RetNet identified genes: 351
- Remaining unidentified mapped loci: 29
- Total genes + unresolved loci: 380
- Complex-disease groups retained separately (AMD and ROP)

Source: https://retnet.org/summaries
Retrieved: 2026-09-28

## Folders

- `data/raw/`: source snapshot with provenance
- `data/processed/`: normalized RetNet associations, unresolved loci, and ODDB candidate associations
- `data/mapping/`: suggested RetNet-to-ODDB disease mappings for curator review
- `reports/`: overlap and QC reports
- `scripts/`: reproducible fetch/harmonize pipeline

## Curation rule

Only rows whose `Independent_Verification_Status` is changed to `Verified` and whose `Curator_Decision` is `Include` should be promoted to an ODDB public release. Discovery-source provenance should remain in the internal curation record.

## Run future updates

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python scripts/fetch_retnet.py
python scripts/harmonize_retnet.py --oddb ../ODDB-main/data/Gene_Disease_Drug_merged.tsv
python scripts/normalize_hgnc.py
```

The fetcher uses a headless browser because RetNet is a JavaScript application. If RetNet changes its page structure, the fetcher will stop rather than silently output an incomplete dataset.

## HGNC normalization

RetNet summary symbols are treated as staging symbols, not automatically as approved genes. Run `normalize_hgnc.py` before curation. This is important because RetNet can retain phenotype/locus symbols alongside gene symbols.

## Public promotion

Run `promote_verified.py` only after independent verification. The public output uses HGNC-approved symbols and excludes discovery-source fields; the internal candidate table retains full provenance for auditability.
