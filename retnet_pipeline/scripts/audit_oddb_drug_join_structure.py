#!/usr/bin/env python3
"""
Audit whether legacy ODDB gene-drug relationships are genuine or are artifacts
of joining disease-gene and disease-drug tables.

No input files are modified.

Key idea:
For each canonical disease:
  - count all distinct canonical/legacy gene symbols represented in the legacy file
For each DiseaseID + drug:
  - count how many distinct genes carry that drug
  - calculate coverage = genes carrying drug / all genes in that disease

If a disease-level drug is replicated across nearly every gene in the disease,
the legacy file should NOT be interpreted as gene-drug evidence.

Also summarizes candidate Drug entities and phase/identifier consistency.
"""

import argparse
import re
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def norm_name(x):
    x = clean(x).lower()
    x = re.sub(r"\s+", " ", x)
    return x


def uniq_join(values):
    out, seen = [], set()
    for x in values:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return " | ".join(out)


def stable_identifier_status(row):
    vals = {
        "InChIKey": clean(row.get("Standard_inchiKey", "")),
        "PubChem_CID": clean(row.get("CID", "")),
        "DrugBank_ID": clean(row.get("DrugBank_ID", "")),
    }
    present = [k for k, v in vals.items() if v]
    return " | ".join(present) if present else "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--canonical-diseases", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.legacy, sep="\t", dtype=str).fillna("")
    diseases = pd.read_csv(
        args.canonical_diseases, sep="\t", dtype=str
    ).fillna("")

    required = [
        "DiseaseID", "Ocular.disease", "GeneSymbol",
        "Drug_name", "Phase", "Merged_RefNew",
        "Standard_inchiKey", "CID", "DrugBank_ID"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    for c in required:
        df[c] = df[c].map(clean)

    drug = df[df["Drug_name"].ne("")].copy()
    drug["Drug_Name_Normalized"] = drug["Drug_name"].map(norm_name)

    # ---------------------------------------------------------
    # Disease-level gene counts
    # ---------------------------------------------------------
    disease_gene_counts = (
        df[df["DiseaseID"].ne("") & df["GeneSymbol"].ne("")]
        .groupby("DiseaseID")
        .agg(
            Disease_Total_Genes=("GeneSymbol", "nunique"),
            Disease_Legacy_Rows=("GeneSymbol", "size"),
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # Pure Disease + Drug pairs and gene replication
    # ---------------------------------------------------------
    pair_rows = []
    for (did, drug_norm), g in drug.groupby(
        ["DiseaseID", "Drug_Name_Normalized"], dropna=False
    ):
        if not did or not drug_norm:
            continue

        total_genes_row = disease_gene_counts[
            disease_gene_counts["DiseaseID"] == did
        ]
        total_genes = (
            int(total_genes_row["Disease_Total_Genes"].iloc[0])
            if len(total_genes_row) else 0
        )

        genes = sorted(set(x for x in g["GeneSymbol"] if x))
        n_genes = len(genes)
        coverage = (n_genes / total_genes) if total_genes else 0.0

        pair_rows.append({
            "DiseaseID": did,
            "Disease_Name_Legacy": uniq_join(g["Ocular.disease"]),
            "Drug_Name_Normalized": drug_norm,
            "Observed_Drug_Names": uniq_join(g["Drug_name"]),
            "Disease_Total_Genes": total_genes,
            "Genes_Carrying_Drug": n_genes,
            "Gene_Coverage_Fraction": coverage,
            "Gene_Coverage_Percent": round(coverage * 100, 2),
            "Replicated_Across_All_Disease_Genes":
                "Yes" if total_genes > 0 and n_genes == total_genes else "No",
            "Likely_Disease_Level_Join_Artifact":
                "Yes" if total_genes >= 2 and coverage >= 0.90 else "No",
            "GeneSymbols": " | ".join(genes),
            "Source_Row_Count": len(g),
            "Phases": uniq_join(g["Phase"]),
            "InChIKeys": uniq_join(g["Standard_inchiKey"]),
            "PubChem_CIDs": uniq_join(g["CID"]),
            "DrugBank_IDs": uniq_join(g["DrugBank_ID"]),
            "References": uniq_join(g["Merged_RefNew"]),
            "Unique_Phase_Count": g.loc[g["Phase"].ne(""), "Phase"].nunique(),
            "Unique_InChIKey_Count":
                g.loc[g["Standard_inchiKey"].ne(""), "Standard_inchiKey"].nunique(),
            "Unique_CID_Count":
                g.loc[g["CID"].ne(""), "CID"].nunique(),
            "Unique_DrugBank_Count":
                g.loc[g["DrugBank_ID"].ne(""), "DrugBank_ID"].nunique(),
            "Unique_Reference_Count":
                g.loc[g["Merged_RefNew"].ne(""), "Merged_RefNew"].nunique(),
        })

    pairs = pd.DataFrame(pair_rows)
    if len(pairs):
        pairs = pairs.sort_values(
            ["Likely_Disease_Level_Join_Artifact",
             "Gene_Coverage_Percent",
             "DiseaseID",
             "Drug_Name_Normalized"],
            ascending=[False, False, True, True]
        )

    # ---------------------------------------------------------
    # Candidate drug master from names
    # ---------------------------------------------------------
    drug_rows = []
    for drug_norm, g in drug.groupby("Drug_Name_Normalized"):
        drug_rows.append({
            "Drug_Name_Normalized": drug_norm,
            "Observed_Drug_Names": uniq_join(g["Drug_name"]),
            "InChIKeys": uniq_join(g["Standard_inchiKey"]),
            "PubChem_CIDs": uniq_join(g["CID"]),
            "DrugBank_IDs": uniq_join(g["DrugBank_ID"]),
            "Identifier_Types_Available": stable_identifier_status(g.iloc[0]),
            "Disease_Count": g["DiseaseID"].replace("", pd.NA).nunique(dropna=True),
            "Diseases": uniq_join(g["Ocular.disease"]),
            "Phases": uniq_join(g["Phase"]),
            "Unique_Phase_Count":
                g.loc[g["Phase"].ne(""), "Phase"].nunique(),
            "References": uniq_join(g["Merged_RefNew"]),
            "Source_Row_Count": len(g),
            "Unique_InChIKey_Count":
                g.loc[g["Standard_inchiKey"].ne(""), "Standard_inchiKey"].nunique(),
            "Unique_CID_Count":
                g.loc[g["CID"].ne(""), "CID"].nunique(),
            "Unique_DrugBank_Count":
                g.loc[g["DrugBank_ID"].ne(""), "DrugBank_ID"].nunique(),
        })

    candidate_drugs = pd.DataFrame(drug_rows).sort_values(
        "Drug_Name_Normalized"
    )

    # Rows without ANY stable identifier, collapsed to unique drug.
    missing_identifiers = candidate_drugs[
        candidate_drugs["InChIKeys"].eq("")
        & candidate_drugs["PubChem_CIDs"].eq("")
        & candidate_drugs["DrugBank_IDs"].eq("")
    ].copy()

    phase_conflicts = candidate_drugs[
        candidate_drugs["Unique_Phase_Count"] > 1
    ].copy()

    identifier_conflicts = candidate_drugs[
        (candidate_drugs["Unique_InChIKey_Count"] > 1)
        | (candidate_drugs["Unique_CID_Count"] > 1)
        | (candidate_drugs["Unique_DrugBank_Count"] > 1)
    ].copy()

    # ---------------------------------------------------------
    # Canonical disease names
    # ---------------------------------------------------------
    if "Disease_Name" in diseases.columns:
        pairs = pairs.merge(
            diseases[["DiseaseID", "Disease_Name"]],
            how="left",
            on="DiseaseID"
        )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    n_pairs = len(pairs)
    all_gene = (
        int((pairs["Replicated_Across_All_Disease_Genes"] == "Yes").sum())
        if n_pairs else 0
    )
    likely_artifact = (
        int((pairs["Likely_Disease_Level_Join_Artifact"] == "Yes").sum())
        if n_pairs else 0
    )
    ge_50 = (
        int((pairs["Gene_Coverage_Fraction"] >= 0.50).sum())
        if n_pairs else 0
    )

    summary = pd.DataFrame([
        ["Drug_rows", len(drug)],
        ["Unique_drug_names", drug["Drug_Name_Normalized"].nunique()],
        ["Pure_unique_disease_drug_pairs", n_pairs],
        ["Disease_drug_pairs_replicated_across_all_genes", all_gene],
        ["Disease_drug_pairs_with_gene_coverage_ge_90pct", likely_artifact],
        ["Disease_drug_pairs_with_gene_coverage_ge_50pct", ge_50],
        ["Candidate_drugs_without_any_stable_identifier", len(missing_identifiers)],
        ["Candidate_drugs_with_multiple_phase_values", len(phase_conflicts)],
        ["Candidate_drugs_with_identifier_conflicts", len(identifier_conflicts)],
    ], columns=["Metric", "Value"])

    # ---------------------------------------------------------
    # Outputs
    # ---------------------------------------------------------
    summary.to_csv(
        outdir / "drug_join_structure_summary.tsv",
        sep="\t", index=False
    )
    disease_gene_counts.to_csv(
        outdir / "disease_gene_counts_for_drug_audit.tsv",
        sep="\t", index=False
    )
    pairs.to_csv(
        outdir / "disease_drug_gene_replication.tsv",
        sep="\t", index=False
    )
    candidate_drugs.to_csv(
        outdir / "candidate_drug_master_audit.tsv",
        sep="\t", index=False
    )
    missing_identifiers.to_csv(
        outdir / "candidate_drugs_missing_all_identifiers.tsv",
        sep="\t", index=False
    )
    phase_conflicts.to_csv(
        outdir / "candidate_drugs_with_phase_conflicts.tsv",
        sep="\t", index=False
    )
    identifier_conflicts.to_csv(
        outdir / "candidate_drugs_with_identifier_conflicts.tsv",
        sep="\t", index=False
    )

    print("ODDB DRUG JOIN-STRUCTURE AUDIT")
    print(summary.to_string(index=False))

    print("\nTop disease-drug pairs by gene replication:")
    if len(pairs):
        print(
            pairs[
                [
                    "DiseaseID",
                    "Observed_Drug_Names",
                    "Disease_Total_Genes",
                    "Genes_Carrying_Drug",
                    "Gene_Coverage_Percent",
                    "Likely_Disease_Level_Join_Artifact",
                ]
            ].head(25).to_string(index=False)
        )

    print("\nCandidate drugs missing all stable identifiers:")
    if len(missing_identifiers):
        print(
            missing_identifiers[
                [
                    "Observed_Drug_Names",
                    "Disease_Count",
                    "Phases",
                    "Source_Row_Count",
                ]
            ].to_string(index=False)
        )
    else:
        print("None")

    print(f"\nReports written to: {outdir}")


if __name__ == "__main__":
    main()
