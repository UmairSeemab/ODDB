# ODDB v1 — MySQL schema, importer and validator

This package deploys the two immutable ODDB v1 frozen releases into a normalized
MySQL/MariaDB database:

- `releases/ODDB_v1_genetics_core_2026-09-29/`
- `releases/ODDB_v1_drug_clinical_refined_2026-09-30/`

The refined drug/clinical release is the current drug/clinical baseline. The
earlier `ODDB_v1_drug_clinical_2026-09-30` snapshot remains immutable but should
not be loaded as the current application dataset.

## Files

- `oddb_v1_schema.sql` — final relational schema and application views.
- `import_oddb_v1_mysql.py` — frozen TSV -> MySQL importer.
- `validate_oddb_v1_mysql.py` — post-import structural and semantic validator.
- `requirements_mysql.txt` — Python dependency.
- `.env.example` — optional connection-variable template.

## Design rules encoded in the schema

1. Disease–drug therapeutic evidence and drug–target pharmacology are separate.
2. Disease–gene–drug target overlap is a discovery relation, not treatment evidence.
3. Clinical-trial investigation is not treated as approval.
4. Multi-disease/multi-drug reports remain relational; no cross-product assertion is created.
5. Drug salts/forms remain distinct entities and are linked by `drug_form_relationship`.
6. Source provenance is preserved for every imported row.
7. Every normalized row also stores the entire frozen TSV row in `source_record_json`.
8. The RETINOL/TRETINOIN correction and unresolved identity-review flags remain explicit.

## Current expected refined counts

| Table | Rows |
|---|---:|
| disease | 162 |
| gene | 1,249 |
| disease_gene_association | 1,631 |
| disease_gene_association_reclassified | 1 |
| locus | 2 |
| disease_locus_association | 2 |
| variant | 707,315 |
| gene_variant_association | 707,315 |
| disease_variant_association | 106,838 |
| drug | 805 |
| drug_form_relationship | 99 |
| drug_target_association | 1,009 |
| disease_drug_association | 344 |
| disease_drug_evidence | 1,142 |
| clinical_report | 1,291 |
| disease_clinical_report_association | 1,370 |
| drug_clinical_report_association | 1,575 |
| clinical_trial | 1,164 |
| disease_clinical_trial_association | 1,235 |
| drug_clinical_trial_association | 1,448 |
| disease_drug_aggregate_context | 157 |
| disease_drug_aggregate_context_demoted | 22 |
| disease_drug_target_overlap | 1,322 |
| disease_drug_target_overlap_summary | 1,203 |
| disease_drug_direct_without_target_overlap | 317 |

The genetics release additionally loads the frozen variant layer:
`variant`, `gene_variant_association`, `disease_variant_association`,
`disease_alias`, `disease_locus_association`, and the derived `locus` table.

## 1. Install the Python dependency

From the ODDB project root:

```bash
source .venv/bin/activate
pip install -r mysql/requirements_mysql.txt
```

If you put these files under another folder, adjust the path.

## 2. Create the MySQL database/schema

For XAMPP/MySQL:

```bash
mysql -u root -p < mysql/oddb_v1_schema.sql
```

If your local root user has no password:

```bash
mysql -u root < mysql/oddb_v1_schema.sql
```

The SQL creates the database `oddb_v1` if it does not exist.

## 3. Set credentials without putting the password in shell history

Recommended:

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD='YOUR_PASSWORD'
export MYSQL_DATABASE=oddb_v1
```

For a local XAMPP root account with no password:

```bash
export MYSQL_PASSWORD=''
```

## 4. Import the two frozen releases

```bash
python mysql/import_oddb_v1_mysql.py \
  --genetics-release releases/ODDB_v1_genetics_core_2026-09-29 \
  --drug-release releases/ODDB_v1_drug_clinical_refined_2026-09-30 \
  --truncate \
  --strict-current-counts
```

`--truncate` gives a deterministic clean reload. It never modifies the frozen
TSV releases; it only truncates and reloads the MySQL tables.

The importer records:
- release names and manifest hashes in `oddb_release`;
- file hashes and source/inserted row counts in `oddb_import_log`.

## 5. Validate the MySQL database

```bash
python mysql/validate_oddb_v1_mysql.py \
  --write-db-results
```

A successful run ends with:

```text
VALIDATION PASSED: zero problems.
The MySQL database matches the frozen refined ODDB v1 release.
```

The optional `--write-db-results` stores every check in
`oddb_validation_result`.

## Application-facing views

### `vw_direct_therapeutic_evidence`

Use this for disease-specific therapeutic evidence. It joins the canonical
disease–drug pair to its source-specific evidence.

### `vw_target_overlap_discovery`

Use this for disease–gene–drug mechanistic overlap. `display_class` explicitly
distinguishes:
- `target_overlap_plus_direct_evidence`
- `target_overlap_only_discovery`

The second must not be displayed as a treatment assertion.

### `vw_drug_forms`

Child/form -> parent drug relationships, including salts/forms.

### `vw_clinical_trial_disease_drug`

Trial-level disease and drug context using the relational association tables.

## Important identity state retained in the database

The refined release contains:
- 51 verified ChEMBL enrichments;
- one separate RETINOL entity (`CHEMBL986`);
- six clinical-report and five clinical-trial remaps from TRETINOIN to RETINOL;
- five pegaptanib source-ID conflicts retained as explicit flags;
- one levothyroxine stereochemistry case pending review;
- one X-82/vorolanib identity case pending review.

The database intentionally does not silently resolve the two pending-review cases.

## Rebuilding safely

For a future dated ODDB v1 release:

1. create and validate the new frozen TSV release first;
2. keep earlier release directories immutable;
3. rerun the importer with `--truncate`;
4. update expected counts only after the new release validator passes;
5. rerun the MySQL validator;
6. deploy the application only after MySQL validation reports zero problems.
