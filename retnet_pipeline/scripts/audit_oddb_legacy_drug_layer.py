#!/usr/bin/env python3
"""
Audit the legacy ODDB drug/therapy fields before normalization.

This script does NOT modify any input data.

It evaluates:
- unique drug names
- drug-bearing rows and disease coverage
- DrugBank / PubChem CID / InChIKey coverage
- phase distribution
- drug-name -> identifier conflicts
- identifier -> multiple-name conflicts
- disease-drug combinations
- gene-drug combinations
- rows with drug name but no stable identifier
- rows with identifier but no drug name
- potentially mixed/multi-valued fields

Outputs a summary plus focused QC TSVs.
"""

import argparse
import re
from pathlib import Path

import pandas as pd


def clean_series(s):
    return s.fillna("").astype(str).str.strip()


def norm_name(x):
    x = str(x or "").strip().lower()
    x = re.sub(r"\s+", " ", x)
    return x


def is_present(s):
    return clean_series(s).ne("")


def split_multivalue(x):
    x = str(x or "").strip()
    if not x:
        return []
    # Conservative: only inspect obvious multi-value delimiters.
    parts = re.split(r"\s*[|;]\s*", x)
    return [p.strip() for p in parts if p.strip()]


def uniq_join(values):
    vals = []
    seen = set()
    for x in values:
        x = str(x or "").strip()
        if x and x not in seen:
            seen.add(x)
            vals.append(x)
    return " | ".join(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--canonical-diseases", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    legacy = pd.read_csv(args.legacy, sep="\t", dtype=str).fillna("")
    diseases = pd.read_csv(args.canonical_diseases, sep="\t", dtype=str).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    required = [
        "DiseaseID",
        "Ocular.disease",
        "GeneSymbol",
        "Drug_name",
        "Phase",
        "Merged_RefNew",
        "Standard_inchiKey",
        "CID",
        "DrugBank_ID",
    ]
    missing = [c for c in required if c not in legacy.columns]
    if missing:
        raise SystemExit(f"Legacy file missing required columns: {missing}")

    # Normalize whitespace only; never alter original values in source file.
    work = legacy.copy()
    for c in required:
        work[c] = clean_series(work[c])

    drug_rows = work[
        work["Drug_name"].ne("")
        | work["Standard_inchiKey"].ne("")
        | work["CID"].ne("")
        | work["DrugBank_ID"].ne("")
    ].copy()

    drug_rows["Drug_Name_Normalized_Audit"] = drug_rows["Drug_name"].map(norm_name)

    # ---------------------------------------------------------
    # Basic entity / relationship views
    # ---------------------------------------------------------
    unique_drugs = (
        drug_rows[drug_rows["Drug_name"].ne("")]
        .drop_duplicates("Drug_Name_Normalized_Audit")
        .sort_values("Drug_name")
        .copy()
    )

    disease_drug = drug_rows[
        drug_rows["DiseaseID"].ne("") & drug_rows["Drug_name"].ne("")
    ][
        [
            "DiseaseID", "Ocular.disease", "Drug_name",
            "Standard_inchiKey", "CID", "DrugBank_ID",
            "Phase", "Merged_RefNew"
        ]
    ].drop_duplicates()

    gene_drug = drug_rows[
        drug_rows["GeneSymbol"].ne("") & drug_rows["Drug_name"].ne("")
    ][
        [
            "GeneSymbol", "Drug_name",
            "Standard_inchiKey", "CID", "DrugBank_ID",
            "Phase", "Merged_RefNew"
        ]
    ].drop_duplicates()

    # ---------------------------------------------------------
    # Identifier coverage
    # ---------------------------------------------------------
    identifier_coverage = pd.DataFrame([
        ["Drug_rows", len(drug_rows)],
        ["Rows_with_Drug_name", int(drug_rows["Drug_name"].ne("").sum())],
        ["Rows_with_InChIKey", int(drug_rows["Standard_inchiKey"].ne("").sum())],
        ["Rows_with_CID", int(drug_rows["CID"].ne("").sum())],
        ["Rows_with_DrugBank_ID", int(drug_rows["DrugBank_ID"].ne("").sum())],
        ["Rows_with_any_stable_identifier", int((
            drug_rows["Standard_inchiKey"].ne("")
            | drug_rows["CID"].ne("")
            | drug_rows["DrugBank_ID"].ne("")
        ).sum())],
        ["Rows_with_name_but_no_identifier", int((
            drug_rows["Drug_name"].ne("")
            & drug_rows["Standard_inchiKey"].eq("")
            & drug_rows["CID"].eq("")
            & drug_rows["DrugBank_ID"].eq("")
        ).sum())],
        ["Rows_with_identifier_but_no_name", int((
            drug_rows["Drug_name"].eq("")
            & (
                drug_rows["Standard_inchiKey"].ne("")
                | drug_rows["CID"].ne("")
                | drug_rows["DrugBank_ID"].ne("")
            )
        ).sum())],
    ], columns=["Metric", "Value"])

    # ---------------------------------------------------------
    # Phase distribution
    # ---------------------------------------------------------
    phase_counts = (
        drug_rows["Phase"]
        .replace("", "[blank]")
        .value_counts(dropna=False)
        .rename_axis("Phase")
        .reset_index(name="Rows")
    )

    # ---------------------------------------------------------
    # Name -> identifiers
    # ---------------------------------------------------------
    grouped_name = []
    for name_norm, g in drug_rows[
        drug_rows["Drug_Name_Normalized_Audit"].ne("")
    ].groupby("Drug_Name_Normalized_Audit"):
        grouped_name.append({
            "Drug_Name_Normalized_Audit": name_norm,
            "Observed_Drug_Names": uniq_join(g["Drug_name"]),
            "InChIKeys": uniq_join(g["Standard_inchiKey"]),
            "PubChem_CIDs": uniq_join(g["CID"]),
            "DrugBank_IDs": uniq_join(g["DrugBank_ID"]),
            "Phases": uniq_join(g["Phase"]),
            "Disease_Count": g["DiseaseID"].replace("", pd.NA).nunique(dropna=True),
            "GeneSymbol_Count": g["GeneSymbol"].replace("", pd.NA).nunique(dropna=True),
            "Source_Row_Count": len(g),
            "Unique_InChIKey_Count": g.loc[
                g["Standard_inchiKey"].ne(""), "Standard_inchiKey"
            ].nunique(),
            "Unique_CID_Count": g.loc[g["CID"].ne(""), "CID"].nunique(),
            "Unique_DrugBank_Count": g.loc[
                g["DrugBank_ID"].ne(""), "DrugBank_ID"
            ].nunique(),
        })

    name_map = pd.DataFrame(grouped_name)

    if len(name_map):
        name_conflicts = name_map[
            (name_map["Unique_InChIKey_Count"] > 1)
            | (name_map["Unique_CID_Count"] > 1)
            | (name_map["Unique_DrugBank_Count"] > 1)
        ].copy()
    else:
        name_conflicts = name_map.copy()

    # ---------------------------------------------------------
    # Identifier -> names
    # ---------------------------------------------------------
    id_collision_rows = []

    for column, namespace in [
        ("Standard_inchiKey", "InChIKey"),
        ("CID", "PubChem_CID"),
        ("DrugBank_ID", "DrugBank_ID"),
    ]:
        subset = drug_rows[drug_rows[column].ne("")].copy()
        for ident, g in subset.groupby(column):
            names = sorted(
                set(
                    x for x in g["Drug_name"]
                    if str(x).strip()
                )
            )
            norm_names = sorted(
                set(
                    norm_name(x) for x in names
                    if norm_name(x)
                )
            )
            if len(norm_names) > 1:
                id_collision_rows.append({
                    "Namespace": namespace,
                    "Identifier": ident,
                    "Distinct_Normalized_Drug_Names": len(norm_names),
                    "Observed_Drug_Names": " | ".join(names),
                    "Disease_Count": g["DiseaseID"].replace(
                        "", pd.NA
                    ).nunique(dropna=True),
                    "Source_Row_Count": len(g),
                })

    id_collisions = pd.DataFrame(
        id_collision_rows,
        columns=[
            "Namespace", "Identifier",
            "Distinct_Normalized_Drug_Names",
            "Observed_Drug_Names",
            "Disease_Count", "Source_Row_Count"
        ]
    )

    # ---------------------------------------------------------
    # Rows needing review
    # ---------------------------------------------------------
    missing_id = drug_rows[
        drug_rows["Drug_name"].ne("")
        & drug_rows["Standard_inchiKey"].eq("")
        & drug_rows["CID"].eq("")
        & drug_rows["DrugBank_ID"].eq("")
    ].copy()

    identifier_no_name = drug_rows[
        drug_rows["Drug_name"].eq("")
        & (
            drug_rows["Standard_inchiKey"].ne("")
            | drug_rows["CID"].ne("")
            | drug_rows["DrugBank_ID"].ne("")
        )
    ].copy()

    # Detect obvious multi-value cells.
    multivalue_rows = []
    for idx, row in drug_rows.iterrows():
        flagged = {}
        for col in [
            "Drug_name", "Standard_inchiKey",
            "CID", "DrugBank_ID", "Phase"
        ]:
            parts = split_multivalue(row[col])
            if len(parts) > 1:
                flagged[col] = row[col]

        if flagged:
            multivalue_rows.append({
                "Source_Row_Index": idx,
                "DiseaseID": row["DiseaseID"],
                "Ocular.disease": row["Ocular.disease"],
                "GeneSymbol": row["GeneSymbol"],
                "Drug_name": row["Drug_name"],
                "Standard_inchiKey": row["Standard_inchiKey"],
                "CID": row["CID"],
                "DrugBank_ID": row["DrugBank_ID"],
                "Phase": row["Phase"],
                "Flagged_Fields": " | ".join(flagged.keys()),
            })

    multivalue = pd.DataFrame(multivalue_rows)

    # ---------------------------------------------------------
    # Canonical disease coverage
    # ---------------------------------------------------------
    canonical_ids = set(diseases["DiseaseID"])
    drug_disease_ids = set(
        drug_rows.loc[drug_rows["DiseaseID"].ne(""), "DiseaseID"]
    )

    unknown_disease_ids = sorted(drug_disease_ids - canonical_ids)
    canonical_with_drugs = canonical_ids & drug_disease_ids

    coverage = diseases[
        diseases["DiseaseID"].isin(canonical_with_drugs)
    ][
        [c for c in ["DiseaseID", "Disease_Name"] if c in diseases.columns]
    ].copy()

    per_disease = (
        disease_drug.groupby("DiseaseID")
        .agg(
            Unique_Drug_Names=(
                "Drug_name",
                lambda x: len(set(norm_name(v) for v in x if norm_name(v)))
            ),
            Disease_Drug_Rows=("Drug_name", "size"),
        )
        .reset_index()
    )
    coverage = coverage.merge(per_disease, how="left", on="DiseaseID")

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    unique_name_count = drug_rows.loc[
        drug_rows["Drug_Name_Normalized_Audit"].ne(""),
        "Drug_Name_Normalized_Audit"
    ].nunique()

    summary = pd.DataFrame([
        ["Legacy_rows_total", len(work)],
        ["Drug_related_rows", len(drug_rows)],
        ["Unique_drug_names_normalized", unique_name_count],
        ["Unique_InChIKeys", drug_rows.loc[
            drug_rows["Standard_inchiKey"].ne(""), "Standard_inchiKey"
        ].nunique()],
        ["Unique_PubChem_CIDs", drug_rows.loc[
            drug_rows["CID"].ne(""), "CID"
        ].nunique()],
        ["Unique_DrugBank_IDs", drug_rows.loc[
            drug_rows["DrugBank_ID"].ne(""), "DrugBank_ID"
        ].nunique()],
        ["Canonical_diseases_with_drugs", len(canonical_with_drugs)],
        ["Canonical_diseases_without_drugs", len(canonical_ids - canonical_with_drugs)],
        ["Unknown_or_retired_DiseaseIDs_in_drug_rows", len(unknown_disease_ids)],
        ["Unique_disease_drug_rows", len(disease_drug)],
        ["Unique_gene_drug_rows", len(gene_drug)],
        ["Drug_names_with_identifier_conflicts", len(name_conflicts)],
        ["Identifiers_linked_to_multiple_names", len(id_collisions)],
        ["Rows_name_without_stable_identifier", len(missing_id)],
        ["Rows_identifier_without_drug_name", len(identifier_no_name)],
        ["Rows_with_obvious_multivalue_fields", len(multivalue)],
    ], columns=["Metric", "Value"])

    # ---------------------------------------------------------
    # Write reports
    # ---------------------------------------------------------
    summary.to_csv(outdir / "drug_audit_summary.tsv", sep="\t", index=False)
    identifier_coverage.to_csv(
        outdir / "drug_identifier_coverage.tsv", sep="\t", index=False
    )
    phase_counts.to_csv(
        outdir / "drug_phase_counts.tsv", sep="\t", index=False
    )
    name_map.to_csv(
        outdir / "drug_name_identifier_map.tsv", sep="\t", index=False
    )
    name_conflicts.to_csv(
        outdir / "drug_name_identifier_conflicts.tsv", sep="\t", index=False
    )
    id_collisions.to_csv(
        outdir / "drug_identifier_name_collisions.tsv", sep="\t", index=False
    )
    missing_id.to_csv(
        outdir / "drug_rows_missing_stable_identifier.tsv", sep="\t", index=False
    )
    identifier_no_name.to_csv(
        outdir / "drug_rows_identifier_without_name.tsv", sep="\t", index=False
    )
    multivalue.to_csv(
        outdir / "drug_multivalue_field_review.tsv", sep="\t", index=False
    )
    disease_drug.to_csv(
        outdir / "legacy_disease_drug_pairs.tsv", sep="\t", index=False
    )
    gene_drug.to_csv(
        outdir / "legacy_gene_drug_pairs.tsv", sep="\t", index=False
    )
    coverage.to_csv(
        outdir / "canonical_disease_drug_coverage.tsv", sep="\t", index=False
    )

    pd.DataFrame(
        {"Unknown_or_retired_DiseaseID": unknown_disease_ids}
    ).to_csv(
        outdir / "unknown_or_retired_disease_ids_in_drug_rows.tsv",
        sep="\t",
        index=False
    )

    print("ODDB LEGACY DRUG / THERAPY AUDIT")
    print(summary.to_string(index=False))

    print("\nTop phase values:")
    print(phase_counts.head(20).to_string(index=False))

    print("\nIdentifier coverage:")
    print(identifier_coverage.to_string(index=False))

    print(f"\nReports written to: {outdir}")


if __name__ == "__main__":
    main()
