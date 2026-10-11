#!/usr/bin/env python3
import argparse
import hashlib
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def expected_id(disease_id, hgnc_id, inheritance):
    key = f"{clean(disease_id)}|{clean(hgnc_id)}|{clean(inheritance).lower()}"
    return "ODDB-DGA-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--associations", required=True)
    ap.add_argument("--additions", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    a = pd.read_csv(args.associations, sep="\t", dtype=str).fillna("")
    n = pd.read_csv(args.additions, sep="\t", dtype=str).fillna("")
    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    required = [
        "Association_ID", "DiseaseID", "Disease", "HGNC_ID", "GeneSymbol",
        "Inheritance", "Association_Origin", "Curation_Status",
        "Curator_Decision"
    ]
    missing = [c for c in required if c not in a.columns]
    if missing:
        raise SystemExit(f"Association file missing columns: {missing}")

    problems = []

    def add_problem(kind, rows):
        if len(rows):
            x = rows.copy()
            x.insert(0, "Problem_Type", kind)
            problems.append(x)

    # Blank stable identifiers
    add_problem(
        "blank_core_identifier",
        a[
            a["Association_ID"].str.strip().eq("")
            | a["DiseaseID"].str.strip().eq("")
            | a["HGNC_ID"].str.strip().eq("")
            | a["GeneSymbol"].str.strip().eq("")
        ]
    )

    # Association-ID uniqueness
    add_problem(
        "duplicate_association_id",
        a[a.duplicated(["Association_ID"], keep=False)]
    )

    # Biological-key uniqueness
    key_cols = ["DiseaseID", "HGNC_ID", "Inheritance"]
    add_problem(
        "duplicate_disease_gene_inheritance_key",
        a[a.duplicated(key_cols, keep=False)]
    )

    # Stable ID correctness
    expected = [
        expected_id(d, h, i)
        for d, h, i in zip(a["DiseaseID"], a["HGNC_ID"], a["Inheritance"])
    ]
    bad_id = a[a["Association_ID"].ne(pd.Series(expected, index=a.index))]
    add_problem("association_id_hash_mismatch", bad_id)

    # One HGNC ID should normally map to one current symbol in this table.
    symbol_counts = (
        a[a["HGNC_ID"].str.strip().ne("")]
        .groupby("HGNC_ID")["GeneSymbol"]
        .nunique()
    )
    conflicted_hgnc = set(symbol_counts[symbol_counts > 1].index)
    add_problem(
        "hgnc_id_multiple_gene_symbols",
        a[a["HGNC_ID"].isin(conflicted_hgnc)]
    )

    # One DiseaseID should normally have one display disease name.
    disease_counts = (
        a[a["DiseaseID"].str.strip().ne("")]
        .groupby("DiseaseID")["Disease"]
        .nunique()
    )
    conflicted_diseases = set(disease_counts[disease_counts > 1].index)
    add_problem(
        "disease_id_multiple_names",
        a[a["DiseaseID"].isin(conflicted_diseases)]
    )

    # Verify RetNet addition file and canonical table agree.
    canonical_new = a[
        a["Association_Origin"].eq("verified_retnet_discovery")
    ].copy()

    compare_cols = ["DiseaseID", "HGNC_ID", "Inheritance"]
    set_canonical = set(map(tuple, canonical_new[compare_cols].astype(str).values.tolist()))
    set_additions = set(map(tuple, n[compare_cols].astype(str).values.tolist()))

    missing_from_canonical = set_additions - set_canonical
    extra_in_canonical = set_canonical - set_additions

    # Summary
    summary = {
        "Association_rows": len(a),
        "Unique_Association_IDs": a["Association_ID"].nunique(),
        "Unique_DiseaseIDs": a["DiseaseID"].nunique(),
        "Unique_HGNC_IDs": a["HGNC_ID"].nunique(),
        "Verified_RetNet_rows_in_canonical": len(canonical_new),
        "RetNet_additions_file_rows": len(n),
        "Missing_RetNet_keys_from_canonical": len(missing_from_canonical),
        "Extra_RetNet_keys_in_canonical": len(extra_in_canonical),
        "Validation_problem_rows": sum(len(x) for x in problems),
    }

    summary_df = pd.DataFrame(
        [{"Metric": k, "Value": v} for k, v in summary.items()]
    )
    summary_df.to_csv(outdir / "association_validation_summary.tsv", sep="\t", index=False)

    origin = (
        a["Association_Origin"]
        .value_counts(dropna=False)
        .rename_axis("Association_Origin")
        .reset_index(name="Rows")
    )
    origin.to_csv(outdir / "association_origin_counts.tsv", sep="\t", index=False)

    evidence = (
        a["Evidence_Status"]
        .value_counts(dropna=False)
        .rename_axis("Evidence_Status")
        .reset_index(name="Rows")
        if "Evidence_Status" in a.columns
        else pd.DataFrame()
    )
    if len(evidence):
        evidence.to_csv(outdir / "evidence_status_counts.tsv", sep="\t", index=False)

    # New genes contributed by accepted additions.
    legacy_genes = set(
        a.loc[a["Association_Origin"].eq("existing_oddb"), "HGNC_ID"]
        .astype(str).str.strip()
    )
    new_gene_rows = canonical_new[
        ~canonical_new["HGNC_ID"].astype(str).str.strip().isin(legacy_genes)
    ].copy()
    new_gene_rows.to_csv(
        outdir / "new_genes_from_verified_retnet.tsv",
        sep="\t",
        index=False
    )

    # New associations for genes already in legacy ODDB.
    existing_gene_new_assoc = canonical_new[
        canonical_new["HGNC_ID"].astype(str).str.strip().isin(legacy_genes)
    ].copy()
    existing_gene_new_assoc.to_csv(
        outdir / "new_associations_existing_genes_from_verified_retnet.tsv",
        sep="\t",
        index=False
    )

    if problems:
        problem_df = pd.concat(problems, ignore_index=True)
    else:
        problem_df = pd.DataFrame(columns=["Problem_Type"] + list(a.columns))
    problem_df.to_csv(outdir / "association_validation_problems.tsv", sep="\t", index=False)

    print("ODDB DISEASE-GENE ASSOCIATION VALIDATION")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print("\nAssociation origins:")
    print(origin.to_string(index=False))

    print("\nNew HGNC genes contributed by verified RetNet additions:")
    if len(new_gene_rows):
        print(
            new_gene_rows[
                ["GeneSymbol", "HGNC_ID", "Disease", "Inheritance"]
            ].drop_duplicates().to_string(index=False)
        )
    else:
        print("None")

    print("\nNew associations for genes already in ODDB:")
    print(len(existing_gene_new_assoc))

    if not problems and not missing_from_canonical and not extra_in_canonical:
        print("\nVALIDATION PASSED: no structural problems detected.")
    else:
        print("\nVALIDATION NEEDS REVIEW: inspect association_validation_problems.tsv")

    print(f"\nReports written to: {outdir}")


if __name__ == "__main__":
    main()
