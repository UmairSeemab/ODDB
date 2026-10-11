#!/usr/bin/env python3
"""
Final ODDB v1 genetics/variant core validator + release manifest builder.

Validates:
- Disease primary keys
- Gene primary keys
- Variant primary keys
- Disease-Gene association IDs and foreign keys
- Gene-Variant association IDs and foreign keys
- Disease-Variant association IDs and foreign keys
- Disease alias targets
- Disease-locus targets
- Duplicate relationship keys
- Canonical disease identifier collisions
- Presence of reclassified legacy rows
- SHA256 checksums and row counts for release manifest

No input files are modified.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(x):
    return str(x or "").strip()


def split_pipe(x):
    return [v.strip() for v in clean(x).split("|") if v.strip()]


def norm_omim(x):
    m = re.search(r"(\d{5,7})", clean(x))
    return m.group(1) if m else ""


def norm_orpha(x):
    m = re.search(r"(\d+)", clean(x))
    return m.group(1) if m else ""


def norm_mondo(x):
    m = re.search(r"(\d{4,})", clean(x))
    return f"MONDO:{m.group(1).zfill(7)}" if m else ""


def norm_cui(x):
    m = re.search(r"\b(CN?\d+|C\d+)\b", clean(x).upper())
    return m.group(1) if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--genes", required=True)
    ap.add_argument("--dga", required=True)
    ap.add_argument("--variants", required=True)
    ap.add_argument("--gva", required=True)
    ap.add_argument("--dva", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--loci", required=True)
    ap.add_argument("--reclassified-dga", required=True)
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--manifest-output", required=True)
    args = ap.parse_args()

    paths = {
        "Disease": Path(args.diseases),
        "Gene": Path(args.genes),
        "Disease_Gene_Association": Path(args.dga),
        "Variant": Path(args.variants),
        "Gene_Variant_Association": Path(args.gva),
        "Disease_Variant_Association": Path(args.dva),
        "Disease_Alias": Path(args.aliases),
        "Disease_Locus_Association": Path(args.loci),
        "Disease_Gene_Association_Reclassified": Path(args.reclassified_dga),
    }

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.manifest_output).parent.mkdir(parents=True, exist_ok=True)

    for name, p in paths.items():
        if not p.exists():
            raise SystemExit(f"Missing required file: {name}: {p}")

    disease = pd.read_csv(paths["Disease"], sep="\t", dtype=str).fillna("")
    gene = pd.read_csv(paths["Gene"], sep="\t", dtype=str).fillna("")
    dga = pd.read_csv(paths["Disease_Gene_Association"], sep="\t", dtype=str).fillna("")
    variant = pd.read_csv(paths["Variant"], sep="\t", dtype=str).fillna("")
    gva = pd.read_csv(paths["Gene_Variant_Association"], sep="\t", dtype=str).fillna("")
    dva = pd.read_csv(paths["Disease_Variant_Association"], sep="\t", dtype=str).fillna("")
    aliases = pd.read_csv(paths["Disease_Alias"], sep="\t", dtype=str).fillna("")
    loci = pd.read_csv(paths["Disease_Locus_Association"], sep="\t", dtype=str).fillna("")
    recl = pd.read_csv(paths["Disease_Gene_Association_Reclassified"], sep="\t", dtype=str).fillna("")

    # Required columns.
    required = {
        "Disease": ["DiseaseID"],
        "Gene": ["HGNC_ID"],
        "Disease_Gene_Association": [
            "Association_ID", "DiseaseID", "HGNC_ID", "Inheritance"
        ],
        "Variant": ["Variant_ID", "ClinVar_Variation_ID"],
        "Gene_Variant_Association": [
            "Gene_Variant_Association_ID", "HGNC_ID", "Variant_ID"
        ],
        "Disease_Variant_Association": [
            "Disease_Variant_Association_ID", "DiseaseID", "Variant_ID"
        ],
        "Disease_Alias": ["Alias_DiseaseID", "Canonical_DiseaseID"],
        "Disease_Locus_Association": [
            "Disease_Locus_Association_ID", "DiseaseID"
        ],
    }

    frames = {
        "Disease": disease,
        "Gene": gene,
        "Disease_Gene_Association": dga,
        "Variant": variant,
        "Gene_Variant_Association": gva,
        "Disease_Variant_Association": dva,
        "Disease_Alias": aliases,
        "Disease_Locus_Association": loci,
    }

    schema_problems = []
    for table, cols in required.items():
        missing = [c for c in cols if c not in frames[table].columns]
        if missing:
            schema_problems.append({
                "Problem_Type": "missing_required_columns",
                "Table": table,
                "Details": ", ".join(missing),
            })

    if schema_problems:
        pd.DataFrame(schema_problems).to_csv(
            outdir / "schema_problems.tsv", sep="\t", index=False
        )
        raise SystemExit(
            "Schema problems detected. See "
            f"{outdir / 'schema_problems.tsv'}"
        )

    disease_ids = set(disease["DiseaseID"])
    gene_ids = set(gene["HGNC_ID"])
    variant_ids = set(variant["Variant_ID"])

    problems = []

    def add_problem(ptype, table, count, details=""):
        problems.append({
            "Problem_Type": ptype,
            "Table": table,
            "Count": int(count),
            "Details": details,
        })

    # Primary ID duplicates / blanks.
    checks = [
        ("Disease", disease, "DiseaseID"),
        ("Gene", gene, "HGNC_ID"),
        ("Variant", variant, "Variant_ID"),
        ("DGA", dga, "Association_ID"),
        ("GVA", gva, "Gene_Variant_Association_ID"),
        ("DVA", dva, "Disease_Variant_Association_ID"),
        ("Locus", loci, "Disease_Locus_Association_ID"),
    ]
    for table, df, col in checks:
        blank = df[col].astype(str).str.strip().eq("").sum()
        dup = df[col].duplicated(keep=False).sum()
        if blank:
            add_problem("blank_primary_id", table, blank, col)
        if dup:
            add_problem("duplicate_primary_id", table, dup, col)

    # Relationship-key duplicates.
    dga_dup = dga.duplicated(
        ["DiseaseID", "HGNC_ID", "Inheritance"], keep=False
    ).sum()
    gva_dup = gva.duplicated(
        ["HGNC_ID", "Variant_ID"], keep=False
    ).sum()
    dva_dup = dva.duplicated(
        ["DiseaseID", "Variant_ID"], keep=False
    ).sum()

    if dga_dup:
        add_problem("duplicate_relationship_key", "DGA", dga_dup)
    if gva_dup:
        add_problem("duplicate_relationship_key", "GVA", gva_dup)
    if dva_dup:
        add_problem("duplicate_relationship_key", "DVA", dva_dup)

    # Foreign keys.
    fk_checks = [
        ("DGA", "DiseaseID", dga, disease_ids),
        ("DGA", "HGNC_ID", dga, gene_ids),
        ("GVA", "HGNC_ID", gva, gene_ids),
        ("GVA", "Variant_ID", gva, variant_ids),
        ("DVA", "DiseaseID", dva, disease_ids),
        ("DVA", "Variant_ID", dva, variant_ids),
        ("Disease_Alias", "Canonical_DiseaseID", aliases, disease_ids),
        ("Disease_Locus", "DiseaseID", loci, disease_ids),
    ]

    for table, col, df, valid in fk_checks:
        bad = df.loc[
            df[col].astype(str).str.strip().ne("")
            & ~df[col].isin(valid)
        ]
        if len(bad):
            add_problem(
                "foreign_key_failure", table, len(bad),
                f"{col} not found in canonical parent table"
            )

    # Canonical disease external identifier collisions.
    indexes = {
        "MONDO": defaultdict(set),
        "OMIM": defaultdict(set),
        "ORPHA": defaultdict(set),
        "CUI": defaultdict(set),
    }

    for _, r in disease.iterrows():
        did = clean(r.get("DiseaseID"))

        for x in split_pipe(r.get("MONDO_ID", "")):
            v = norm_mondo(x)
            if v:
                indexes["MONDO"][v].add(did)

        for x in split_pipe(r.get("OMIM_ID", "")):
            v = norm_omim(x)
            if v:
                indexes["OMIM"][v].add(did)

        for x in split_pipe(r.get("Orphanet_ID", "")):
            v = norm_orpha(x)
            if v:
                indexes["ORPHA"][v].add(did)

        for x in split_pipe(r.get("MedGen_UMLS_CUI", "")):
            v = norm_cui(x)
            if v:
                indexes["CUI"][v].add(did)

    collision_rows = []
    for ns, idx in indexes.items():
        for ident, dids in idx.items():
            if len(dids) > 1:
                collision_rows.append({
                    "Namespace": ns,
                    "Identifier": ident,
                    "Disease_Count": len(dids),
                    "DiseaseIDs": " | ".join(sorted(dids)),
                })

    collision_df = pd.DataFrame(
        collision_rows,
        columns=["Namespace", "Identifier", "Disease_Count", "DiseaseIDs"]
    )
    collision_df.to_csv(
        outdir / "disease_identifier_collisions.tsv",
        sep="\t",
        index=False
    )

    if len(collision_df):
        add_problem(
            "disease_identifier_collision",
            "Disease",
            len(collision_df)
        )

    # Check ODDB-146 is absent from simple DGA and preserved in reclassified.
    oddb146_dga = int((dga["DiseaseID"] == "ODDB-146").sum())
    oddb146_recl = int(
        (recl["DiseaseID"] == "ODDB-146").sum()
        if "DiseaseID" in recl.columns else 0
    )
    if oddb146_dga:
        add_problem(
            "reclassified_relationship_still_canonical",
            "DGA",
            oddb146_dga,
            "ODDB-146 should not retain DMD-only canonical DGA"
        )
    if oddb146_recl == 0:
        add_problem(
            "missing_reclassified_legacy_relationship",
            "DGA_reclassified",
            1,
            "Expected preserved ODDB-146 legacy relationship"
        )

    # Check known corrected entities.
    known_checks = []
    for did, expected_name in [
        ("ODDB-101", "ÅLAND ISLANDS EYE DISEASE"),
        ("ODDB-143", "FAMILIAL CAVITARY OPTIC DISK ANOMALY"),
        ("ODDB-225", "STARGARDT DISEASE"),
    ]:
        hit = disease[disease["DiseaseID"] == did]
        actual = hit["Disease_Name"].iloc[0] if len(hit) else ""
        known_checks.append({
            "DiseaseID": did,
            "Expected_Name": expected_name,
            "Actual_Name": actual,
            "Pass": actual == expected_name,
        })
        if actual != expected_name:
            add_problem(
                "known_curated_disease_check_failed",
                "Disease",
                1,
                f"{did}: expected {expected_name}, got {actual}"
            )

    pd.DataFrame(known_checks).to_csv(
        outdir / "known_curated_disease_checks.tsv",
        sep="\t",
        index=False
    )

    # Summary counts.
    summary_rows = [
        ["Disease_rows", len(disease)],
        ["Gene_rows", len(gene)],
        ["Disease_Gene_Association_rows", len(dga)],
        ["Variant_rows", len(variant)],
        ["Gene_Variant_Association_rows", len(gva)],
        ["Disease_Variant_Association_rows", len(dva)],
        ["Disease_Alias_rows", len(aliases)],
        ["Disease_Locus_Association_rows", len(loci)],
        ["Reclassified_DGA_rows", len(recl)],
        ["Unique_DVA_diseases", dva["DiseaseID"].nunique()],
        ["Unique_DVA_variants", dva["Variant_ID"].nunique()],
        ["Disease_identifier_collision_rows", len(collision_df)],
        ["Validation_problem_types", len(problems)],
        ["Validation_problem_rows_total",
         sum(int(p["Count"]) for p in problems)],
    ]

    summary = pd.DataFrame(summary_rows, columns=["Metric", "Value"])
    summary.to_csv(
        outdir / "oddb_v1_core_validation_summary.tsv",
        sep="\t",
        index=False
    )

    problems_df = pd.DataFrame(
        problems,
        columns=["Problem_Type", "Table", "Count", "Details"]
    )
    problems_df.to_csv(
        outdir / "oddb_v1_core_validation_problems.tsv",
        sep="\t",
        index=False
    )

    # Release manifest.
    manifest = {
        "release_name": "ODDB v1 genetics-variant canonical core",
        "release_date": "2026-09-29",
        "validation_status": "PASS" if not problems else "REVIEW_REQUIRED",
        "tables": {},
        "counts": {
            "diseases": len(disease),
            "genes": len(gene),
            "disease_gene_associations": len(dga),
            "variants": len(variant),
            "gene_variant_associations": len(gva),
            "disease_variant_associations": len(dva),
            "diseases_with_clinvar_links": int(dva["DiseaseID"].nunique()),
            "variants_with_oddb_disease_links": int(dva["Variant_ID"].nunique()),
            "disease_aliases": len(aliases),
            "disease_locus_associations": len(loci),
            "reclassified_disease_gene_rows": len(recl),
        },
    }

    for name, path in paths.items():
        df = {
            "Disease": disease,
            "Gene": gene,
            "Disease_Gene_Association": dga,
            "Variant": variant,
            "Gene_Variant_Association": gva,
            "Disease_Variant_Association": dva,
            "Disease_Alias": aliases,
            "Disease_Locus_Association": loci,
            "Disease_Gene_Association_Reclassified": recl,
        }[name]

        manifest["tables"][name] = {
            "path": str(path),
            "rows": int(len(df)),
            "sha256": sha256_file(path),
        }

    Path(args.manifest_output).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("ODDB v1 GENETICS / VARIANT CORE FREEZE VALIDATION")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION: REVIEW REQUIRED")
        print(problems_df.to_string(index=False))
    else:
        print("\nVALIDATION PASSED: canonical genetics/variant core is internally consistent.")

    print(f"\nSummary: {outdir / 'oddb_v1_core_validation_summary.tsv'}")
    print(f"Problems: {outdir / 'oddb_v1_core_validation_problems.tsv'}")
    print(f"Manifest: {args.manifest_output}")


if __name__ == "__main__":
    main()
