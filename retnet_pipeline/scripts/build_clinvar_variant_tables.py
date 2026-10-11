#!/usr/bin/env python3
"""
Normalize an ODDB-gene-filtered ClinVar variant_summary staging TSV into:

1. Variant_v1.tsv
   - one row per ClinVar VariationID

2. Gene_Variant_Association_v1.tsv
   - one row per HGNC gene × ClinVar VariationID

The script intentionally does NOT create disease-variant associations.
ClinVar PhenotypeIDS/PhenotypeList are preserved for later disease mapping.

Uses only Python standard library for the streaming/deduplication layer.
"""

import argparse
import csv
import hashlib
import sqlite3
from pathlib import Path


def clean(x):
    return str(x or "").strip()


def norm_name(x):
    return clean(x).lower().lstrip("#").replace(" ", "").replace("_", "")


def find_col(fieldnames, candidates, required=False):
    lookup = {norm_name(c): c for c in fieldnames}
    for cand in candidates:
        key = norm_name(cand)
        if key in lookup:
            return lookup[key]
    if required:
        raise SystemExit(
            f"Required column not found. Tried {candidates}. "
            f"Available: {fieldnames}"
        )
    return None


def qident(name):
    return '"' + str(name).replace('"', '""') + '"'


def stable_gene_variant_id(hgnc_id, variation_id):
    key = f"{clean(hgnc_id)}|{clean(variation_id)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-GVA-{digest}"


def variant_id(variation_id):
    return f"ODDB-VAR-CV{clean(variation_id)}"


def create_db(conn):
    conn.execute("""
        CREATE TABLE variant (
            ClinVar_Variation_ID TEXT PRIMARY KEY,
            Variant_ID TEXT NOT NULL,
            Variant_Type TEXT,
            ClinVar_Name TEXT,
            ClinVar_Allele_ID TEXT,
            dbSNP_rsID TEXT,
            NCBI_Variant_IDs TEXT,
            Assembly TEXT,
            Chromosome TEXT,
            Chromosome_Accession TEXT,
            Start TEXT,
            Stop TEXT,
            Position_VCF TEXT,
            Reference_Allele TEXT,
            Alternate_Allele TEXT,
            Reference_Allele_VCF TEXT,
            Alternate_Allele_VCF TEXT,
            Cytogenetic_Location TEXT,
            Clinical_Significance TEXT,
            Clinical_Significance_Simple TEXT,
            Last_Evaluated TEXT,
            Review_Status TEXT,
            Number_Submitters TEXT,
            Guidelines TEXT,
            Origin TEXT,
            Origin_Simple TEXT,
            Phenotype_IDs_Raw TEXT,
            Phenotype_List_Raw TEXT,
            RCV_Accessions_Raw TEXT,
            Other_IDs_Raw TEXT,
            Somatic_Clinical_Impact TEXT,
            Oncogenicity TEXT,
            ClinVar_Source_URL TEXT,
            ClinVar_Retrieved_UTC TEXT,
            ClinVar_Raw_SHA256 TEXT,
            Source_Row_Count INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE gene_variant (
            Gene_Variant_Association_ID TEXT PRIMARY KEY,
            HGNC_ID TEXT NOT NULL,
            GeneSymbol TEXT,
            Variant_ID TEXT NOT NULL,
            ClinVar_Variation_ID TEXT NOT NULL,
            ClinVar_Gene_ID TEXT,
            Match_Method TEXT,
            Source TEXT,
            Source_URL TEXT,
            Retrieved_UTC TEXT,
            Raw_SHA256 TEXT,
            UNIQUE(HGNC_ID, ClinVar_Variation_ID)
        )
    """)

    conn.execute("""
        CREATE TABLE duplicate_variant_rows (
            ClinVar_Variation_ID TEXT,
            GeneSymbol TEXT,
            HGNC_ID TEXT,
            ClinVar_Name TEXT
        )
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", required=True)
    ap.add_argument("--variant-output", required=True)
    ap.add_argument("--gene-variant-output", required=True)
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--sqlite-temp", required=False)
    args = ap.parse_args()

    staging = Path(args.staging)
    out_variant = Path(args.variant_output)
    out_gv = Path(args.gene_variant_output)
    report_dir = Path(args.report_dir)

    out_variant.parent.mkdir(parents=True, exist_ok=True)
    out_gv.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    db_path = (
        Path(args.sqlite_temp)
        if args.sqlite_temp
        else report_dir / "_clinvar_normalization_tmp.sqlite"
    )
    if db_path.exists():
        db_path.unlink()

    # Read header and dynamically map current ClinVar fields.
    with staging.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames or []

    c = {}
    c["variation"] = find_col(fields, ["VariationID", "Variation ID"], True)
    c["allele"] = find_col(fields, ["AlleleID", "Allele ID"])
    c["type"] = find_col(fields, ["Type"])
    c["name"] = find_col(fields, ["Name"])
    c["geneid"] = find_col(fields, ["GeneID", "Gene ID"])
    c["genesymbol"] = find_col(fields, ["GeneSymbol", "Gene Symbol"])
    c["hgnc"] = find_col(fields, ["HGNC_ID", "HGNC ID"])
    c["clinsig"] = find_col(fields, ["ClinicalSignificance", "Clinical Significance"])
    c["clinsigsimple"] = find_col(fields, ["ClinSigSimple"])
    c["lasteval"] = find_col(fields, ["LastEvaluated", "Last Evaluated"])
    c["rs"] = find_col(fields, ["RS#", "RS", "dbSNP"])
    c["nsv_esv"] = find_col(fields, ["nsv/esv", "NSV/ESV"])
    c["rcv"] = find_col(fields, ["RCVaccession", "RCV accession"])
    c["phenotype_ids"] = find_col(fields, ["PhenotypeIDS", "Phenotype IDs"])
    c["phenotype_list"] = find_col(fields, ["PhenotypeList", "Phenotype List"])
    c["origin"] = find_col(fields, ["Origin"])
    c["origin_simple"] = find_col(fields, ["OriginSimple", "Origin Simple"])
    c["assembly"] = find_col(fields, ["Assembly"])
    c["chr_acc"] = find_col(fields, ["ChromosomeAccession", "Chromosome Accession"])
    c["chromosome"] = find_col(fields, ["Chromosome"])
    c["start"] = find_col(fields, ["Start"])
    c["stop"] = find_col(fields, ["Stop"])
    c["ref"] = find_col(fields, ["ReferenceAllele", "Reference Allele"])
    c["alt"] = find_col(fields, ["AlternateAllele", "Alternate Allele"])
    c["cytogenetic"] = find_col(fields, ["Cytogenetic"])
    c["review"] = find_col(fields, ["ReviewStatus", "Review Status"])
    c["submitters"] = find_col(fields, ["NumberSubmitters", "Number Submitters"])
    c["guidelines"] = find_col(fields, ["Guidelines"])
    c["otherids"] = find_col(fields, ["OtherIDs", "Other IDs"])
    c["position_vcf"] = find_col(fields, ["PositionVCF", "Position VCF"])
    c["ref_vcf"] = find_col(fields, ["ReferenceAlleleVCF", "Reference Allele VCF"])
    c["alt_vcf"] = find_col(fields, ["AlternateAlleleVCF", "Alternate Allele VCF"])
    c["somatic_impact"] = find_col(fields, ["SomaticClinicalImpact", "Somatic Clinical Impact"])
    c["oncogenicity"] = find_col(fields, ["Oncogenicity"])

    # ODDB-added provenance/mapping columns.
    c["oddb_hgnc"] = find_col(fields, ["ODDB_Matched_HGNC_ID"], True)
    c["oddb_symbol"] = find_col(fields, ["ODDB_Matched_GeneSymbol"], True)
    c["match_method"] = find_col(fields, ["ODDB_Gene_Match_Method"])
    c["source_url"] = find_col(fields, ["ClinVar_Source_URL"])
    c["retrieved"] = find_col(fields, ["ClinVar_Retrieved_UTC"])
    c["sha"] = find_col(fields, ["ClinVar_Raw_SHA256"])

    def val(row, key):
        col = c.get(key)
        return clean(row.get(col, "")) if col else ""

    conn = sqlite3.connect(db_path)
    create_db(conn)

    insert_variant = """
        INSERT OR IGNORE INTO variant (
            ClinVar_Variation_ID, Variant_ID, Variant_Type, ClinVar_Name,
            ClinVar_Allele_ID, dbSNP_rsID, NCBI_Variant_IDs, Assembly,
            Chromosome, Chromosome_Accession, Start, Stop, Position_VCF,
            Reference_Allele, Alternate_Allele, Reference_Allele_VCF,
            Alternate_Allele_VCF, Cytogenetic_Location,
            Clinical_Significance, Clinical_Significance_Simple,
            Last_Evaluated, Review_Status, Number_Submitters, Guidelines,
            Origin, Origin_Simple, Phenotype_IDs_Raw, Phenotype_List_Raw,
            RCV_Accessions_Raw, Other_IDs_Raw, Somatic_Clinical_Impact,
            Oncogenicity, ClinVar_Source_URL, ClinVar_Retrieved_UTC,
            ClinVar_Raw_SHA256, Source_Row_Count
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1
        )
    """

    insert_gv = """
        INSERT OR IGNORE INTO gene_variant (
            Gene_Variant_Association_ID, HGNC_ID, GeneSymbol, Variant_ID,
            ClinVar_Variation_ID, ClinVar_Gene_ID, Match_Method,
            Source, Source_URL, Retrieved_UTC, Raw_SHA256
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """

    total_rows = 0
    duplicates = 0
    missing_variation_id = 0
    missing_hgnc = 0

    with staging.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")

        for row in reader:
            total_rows += 1
            vid = val(row, "variation")
            hgnc = val(row, "oddb_hgnc")
            gene_symbol = val(row, "oddb_symbol") or val(row, "genesymbol")

            if not vid:
                missing_variation_id += 1
                continue

            before = conn.total_changes

            conn.execute(
                insert_variant,
                (
                    vid,
                    variant_id(vid),
                    val(row, "type"),
                    val(row, "name"),
                    val(row, "allele"),
                    val(row, "rs"),
                    val(row, "nsv_esv"),
                    val(row, "assembly"),
                    val(row, "chromosome"),
                    val(row, "chr_acc"),
                    val(row, "start"),
                    val(row, "stop"),
                    val(row, "position_vcf"),
                    val(row, "ref"),
                    val(row, "alt"),
                    val(row, "ref_vcf"),
                    val(row, "alt_vcf"),
                    val(row, "cytogenetic"),
                    val(row, "clinsig"),
                    val(row, "clinsigsimple"),
                    val(row, "lasteval"),
                    val(row, "review"),
                    val(row, "submitters"),
                    val(row, "guidelines"),
                    val(row, "origin"),
                    val(row, "origin_simple"),
                    val(row, "phenotype_ids"),
                    val(row, "phenotype_list"),
                    val(row, "rcv"),
                    val(row, "otherids"),
                    val(row, "somatic_impact"),
                    val(row, "oncogenicity"),
                    val(row, "source_url"),
                    val(row, "retrieved"),
                    val(row, "sha"),
                ),
            )

            if conn.total_changes == before:
                duplicates += 1
                conn.execute(
                    """
                    UPDATE variant
                    SET Source_Row_Count = Source_Row_Count + 1
                    WHERE ClinVar_Variation_ID = ?
                    """,
                    (vid,),
                )
                conn.execute(
                    """
                    INSERT INTO duplicate_variant_rows
                    (ClinVar_Variation_ID, GeneSymbol, HGNC_ID, ClinVar_Name)
                    VALUES (?,?,?,?)
                    """,
                    (vid, gene_symbol, hgnc, val(row, "name")),
                )

            if not hgnc:
                missing_hgnc += 1
            else:
                conn.execute(
                    insert_gv,
                    (
                        stable_gene_variant_id(hgnc, vid),
                        hgnc,
                        gene_symbol,
                        variant_id(vid),
                        vid,
                        val(row, "geneid"),
                        val(row, "match_method"),
                        "NCBI ClinVar",
                        val(row, "source_url"),
                        val(row, "retrieved"),
                        val(row, "sha"),
                    ),
                )

            if total_rows % 100000 == 0:
                conn.commit()
                print(f"Processed {total_rows:,} staging rows...")

    conn.commit()

    variant_count = conn.execute(
        "SELECT COUNT(*) FROM variant"
    ).fetchone()[0]
    gv_count = conn.execute(
        "SELECT COUNT(*) FROM gene_variant"
    ).fetchone()[0]
    unique_genes = conn.execute(
        "SELECT COUNT(DISTINCT HGNC_ID) FROM gene_variant"
    ).fetchone()[0]
    coord_missing = conn.execute(
        """
        SELECT COUNT(*) FROM variant
        WHERE Chromosome='' OR Start='' OR Reference_Allele='' OR Alternate_Allele=''
        """
    ).fetchone()[0]

    # Export canonical variant table.
    variant_cols = [
        "Variant_ID",
        "ClinVar_Variation_ID",
        "Variant_Type",
        "ClinVar_Name",
        "ClinVar_Allele_ID",
        "dbSNP_rsID",
        "NCBI_Variant_IDs",
        "Assembly",
        "Chromosome",
        "Chromosome_Accession",
        "Start",
        "Stop",
        "Position_VCF",
        "Reference_Allele",
        "Alternate_Allele",
        "Reference_Allele_VCF",
        "Alternate_Allele_VCF",
        "Cytogenetic_Location",
        "Clinical_Significance",
        "Clinical_Significance_Simple",
        "Last_Evaluated",
        "Review_Status",
        "Number_Submitters",
        "Guidelines",
        "Origin",
        "Origin_Simple",
        "Phenotype_IDs_Raw",
        "Phenotype_List_Raw",
        "RCV_Accessions_Raw",
        "Other_IDs_Raw",
        "Somatic_Clinical_Impact",
        "Oncogenicity",
        "ClinVar_Source_URL",
        "ClinVar_Retrieved_UTC",
        "ClinVar_Raw_SHA256",
        "Source_Row_Count",
    ]

    with out_variant.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(variant_cols)
        query = (
            "SELECT " + ",".join(qident(x) for x in variant_cols) +
            " FROM variant ORDER BY CAST(ClinVar_Variation_ID AS INTEGER)"
        )
        for record in conn.execute(query):
            writer.writerow(record)

    gv_cols = [
        "Gene_Variant_Association_ID",
        "HGNC_ID",
        "GeneSymbol",
        "Variant_ID",
        "ClinVar_Variation_ID",
        "ClinVar_Gene_ID",
        "Match_Method",
        "Source",
        "Source_URL",
        "Retrieved_UTC",
        "Raw_SHA256",
    ]

    with out_gv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(gv_cols)
        query = (
            "SELECT " + ",".join(qident(x) for x in gv_cols) +
            " FROM gene_variant ORDER BY HGNC_ID, CAST(ClinVar_Variation_ID AS INTEGER)"
        )
        for record in conn.execute(query):
            writer.writerow(record)

    # Reports.
    dup_path = report_dir / "duplicate_clinvar_variation_rows.tsv"
    with dup_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["ClinVar_Variation_ID", "GeneSymbol", "HGNC_ID", "ClinVar_Name"]
        )
        for record in conn.execute(
            """
            SELECT ClinVar_Variation_ID, GeneSymbol, HGNC_ID, ClinVar_Name
            FROM duplicate_variant_rows
            ORDER BY CAST(ClinVar_Variation_ID AS INTEGER)
            """
        ):
            writer.writerow(record)

    def export_distribution(column, filename):
        path = report_dir / filename
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            writer.writerow([column, "Rows"])
            query = (
                f"SELECT {qident(column)}, COUNT(*) AS n "
                f"FROM variant GROUP BY {qident(column)} ORDER BY n DESC"
            )
            for value, count in conn.execute(query):
                writer.writerow([value, count])

    export_distribution("Clinical_Significance", "clinical_significance_counts.tsv")
    export_distribution("Review_Status", "review_status_counts.tsv")
    export_distribution("Variant_Type", "variant_type_counts.tsv")

    summary = [
        ("Staging_rows_processed", total_rows),
        ("Canonical_variant_rows", variant_count),
        ("Gene_variant_association_rows", gv_count),
        ("Unique_HGNC_genes_in_gene_variant", unique_genes),
        ("Duplicate_staging_rows_by_VariationID", duplicates),
        ("Rows_missing_VariationID", missing_variation_id),
        ("Rows_missing_ODDB_HGNC_ID", missing_hgnc),
        ("Variants_missing_complete_GRCh38_ref_alt_coordinate", coord_missing),
    ]

    with (report_dir / "variant_build_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["Metric", "Value"])
        writer.writerows(summary)

    print("\nODDB VARIANT NORMALIZATION")
    for key, value in summary:
        print(f"{key}: {value:,}" if isinstance(value, int) else f"{key}: {value}")

    print(f"\nVariant master: {out_variant}")
    print(f"Gene-variant associations: {out_gv}")
    print(f"Reports: {report_dir}")
    print("\nNo disease-variant associations were created.")

    conn.close()

    # Keep temp SQLite only if user explicitly supplied a path.
    if not args.sqlite_temp and db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    main()
