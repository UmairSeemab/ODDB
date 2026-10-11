#!/usr/bin/env python3
"""
Rebuild the ODDB disease master using only fields that are genuinely
disease-level in the legacy merged ODDB table.

Important:
- Does NOT copy legacy OMIM, Description, Ensembl, ClinVar, etc. because those
  belong to the gene annotation block in Gene_Disease_Drug_merged.
- Preserves DiseaseID, disease name, disease category, and Disease_UML_CUI.
- Adds gene-association counts from the validated canonical association table.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def unique_join(series, sep=" | "):
    out, seen = [], set()
    for x in series:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return sep.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--associations", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report-output", required=True)
    args = ap.parse_args()

    legacy = pd.read_csv(args.legacy, sep="\t", dtype=str).fillna("")
    assoc = pd.read_csv(args.associations, sep="\t", dtype=str).fillna("")

    required_legacy = [
        "DiseaseID",
        "Disease.category",
        "Ocular.disease",
        "Disease_UML_CUI",
    ]
    missing = [c for c in required_legacy if c not in legacy.columns]
    if missing:
        raise SystemExit(f"Legacy file missing required disease columns: {missing}")

    rows = []

    for did, g in legacy.groupby("DiseaseID", dropna=False):
        did = clean(did)
        if not did:
            continue

        names = []
        seen = set()
        for x in g["Ocular.disease"]:
            x = clean(x)
            if x and x not in seen:
                seen.add(x)
                names.append(x)

        categories = []
        seen_cat = set()
        for x in g["Disease.category"]:
            x = clean(x)
            if x and x not in seen_cat:
                seen_cat.add(x)
                categories.append(x)

        rows.append({
            "DiseaseID": did,
            "Disease_Name": names[0] if names else "",
            "Disease_Name_Conflict": "Yes" if len(names) > 1 else "No",
            "Alternative_Disease_Names_From_Legacy":
                " | ".join(names[1:]) if len(names) > 1 else "",
            "Localization_Category": " | ".join(categories),
            "MedGen_UMLS_CUI": unique_join(g["Disease_UML_CUI"]),

            # Intentionally blank until filled by authoritative disease sources.
            "Synonyms": "",
            "Disease_Description": "",
            "MONDO_ID": "",
            "OMIM_ID": "",
            "Orphanet_ID": "",

            "Source_Status": "ODDB legacy disease entity",
        })

    disease = pd.DataFrame(rows)

    counts = (
        assoc.groupby("DiseaseID")
        .agg(
            Gene_Association_Count=("Association_ID", "nunique"),
            Unique_Gene_Count=("HGNC_ID", "nunique"),
        )
        .reset_index()
    )

    disease = disease.merge(counts, how="left", on="DiseaseID")
    disease["Gene_Association_Count"] = (
        disease["Gene_Association_Count"].fillna(0).astype(int)
    )
    disease["Unique_Gene_Count"] = (
        disease["Unique_Gene_Count"].fillna(0).astype(int)
    )
    disease["Has_Gene_Association"] = disease["Gene_Association_Count"].map(
        lambda x: "Yes" if x > 0 else "No"
    )

    cols = [
        "DiseaseID",
        "Disease_Name",
        "Disease_Name_Conflict",
        "Alternative_Disease_Names_From_Legacy",
        "Localization_Category",
        "Synonyms",
        "Disease_Description",
        "MONDO_ID",
        "OMIM_ID",
        "Orphanet_ID",
        "MedGen_UMLS_CUI",
        "Has_Gene_Association",
        "Gene_Association_Count",
        "Unique_Gene_Count",
        "Source_Status",
    ]

    disease = disease[cols].sort_values("DiseaseID")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_output).parent.mkdir(parents=True, exist_ok=True)

    disease.to_csv(args.output, sep="\t", index=False)

    report = pd.DataFrame(
        [
            ["Disease_rows", len(disease)],
            ["Unique_DiseaseIDs", disease["DiseaseID"].nunique()],
            ["Disease_name_conflicts",
             int((disease["Disease_Name_Conflict"] == "Yes").sum())],
            ["Diseases_with_MedGen_UMLS_CUI",
             int(disease["MedGen_UMLS_CUI"].str.strip().ne("").sum())],
            ["Diseases_without_MedGen_UMLS_CUI",
             int(disease["MedGen_UMLS_CUI"].str.strip().eq("").sum())],
            ["Diseases_with_gene_associations",
             int((disease["Has_Gene_Association"] == "Yes").sum())],
            ["Diseases_without_gene_associations",
             int((disease["Has_Gene_Association"] == "No").sum())],
            ["Legacy_gene_level_OMIM_copied", 0],
            ["Legacy_gene_level_Description_copied", 0],
        ],
        columns=["Metric", "Value"]
    )
    report.to_csv(args.report_output, sep="\t", index=False)

    print("ODDB CLEAN DISEASE MASTER REBUILD")
    print(report.to_string(index=False))
    print(f"\nWritten: {args.output}")
    print(f"Report: {args.report_output}")
    print("\nGene-level OMIM/Description/ClinVar fields were deliberately excluded.")


if __name__ == "__main__":
    main()
