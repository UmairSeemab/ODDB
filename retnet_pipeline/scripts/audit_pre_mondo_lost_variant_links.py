#!/usr/bin/env python3
"""
Compare the original pre-MONDO disease-variant mapping with the final canonical
mapping and identify links/diseases that disappeared after ontology-aware
normalization.

This is a QC script only. It does not modify any ODDB table.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--variants", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    old = pd.read_csv(args.baseline, sep="\t", dtype=str).fillna("")
    new = pd.read_csv(args.canonical, sep="\t", dtype=str).fillna("")
    dis = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")

    var_cols = [
        "Variant_ID", "ClinVar_Variation_ID",
        "Phenotype_List_Raw", "Phenotype_IDs_Raw",
        "Clinical_Significance", "Review_Status"
    ]
    var = pd.read_csv(
        args.variants,
        sep="\t",
        dtype=str,
        usecols=lambda c: c in var_cols
    ).fillna("")

    old_keys = set(zip(old["DiseaseID"], old["Variant_ID"]))
    new_keys = set(zip(new["DiseaseID"], new["Variant_ID"]))

    lost = old_keys - new_keys
    gained = new_keys - old_keys

    lost_df = old[
        old.apply(
            lambda r: (r["DiseaseID"], r["Variant_ID"]) in lost,
            axis=1
        )
    ].copy()

    lost_df = lost_df.merge(
        var,
        how="left",
        on=["Variant_ID", "ClinVar_Variation_ID"],
        suffixes=("", "_VariantMaster")
    )

    # For each lost variant, show where it maps now.
    current_targets = (
        new.groupby("Variant_ID")
        .agg(
            Current_DiseaseIDs=("DiseaseID", lambda x: " | ".join(sorted(set(x)))),
            Current_Disease_Names=("Disease_Name", lambda x: " | ".join(sorted(set(x)))),
        )
        .reset_index()
    )
    lost_df = lost_df.merge(current_targets, how="left", on="Variant_ID")
    lost_df["Current_DiseaseIDs"] = lost_df["Current_DiseaseIDs"].fillna("")
    lost_df["Current_Disease_Names"] = lost_df["Current_Disease_Names"].fillna("")

    # Add canonical disease metadata where still present.
    dis_meta = dis[
        [c for c in [
            "DiseaseID", "Disease_Name", "MONDO_ID",
            "OMIM_ID", "Orphanet_ID", "MedGen_UMLS_CUI"
        ] if c in dis.columns]
    ].drop_duplicates("DiseaseID")

    lost_df = lost_df.merge(
        dis_meta,
        how="left",
        on="DiseaseID",
        suffixes=("_Baseline", "_CanonicalMaster")
    )

    lost_df.to_csv(
        outdir / "lost_pre_mondo_links.tsv",
        sep="\t",
        index=False
    )

    old_diseases = set(old["DiseaseID"])
    new_diseases = set(new["DiseaseID"])

    diseases_losing_all = sorted(old_diseases - new_diseases)

    loss_counts = (
        lost_df.groupby("DiseaseID")
        .agg(
            Lost_Associations=("Variant_ID", "size"),
            Lost_Unique_Variants=("Variant_ID", "nunique"),
            Variants_Still_Map_Elsewhere=(
                "Current_DiseaseIDs",
                lambda x: sum(bool(clean(v)) for v in x)
            )
        )
        .reset_index()
    )

    disease_loss = dis_meta.merge(
        loss_counts,
        how="right",
        on="DiseaseID"
    )
    disease_loss["Lost_All_Variant_Links"] = disease_loss["DiseaseID"].map(
        lambda x: "Yes" if x in diseases_losing_all else "No"
    )

    disease_loss.sort_values(
        ["Lost_All_Variant_Links", "Lost_Associations"],
        ascending=[False, False]
    ).to_csv(
        outdir / "diseases_with_lost_links.tsv",
        sep="\t",
        index=False
    )

    lost_all_df = disease_loss[
        disease_loss["Lost_All_Variant_Links"] == "Yes"
    ].copy()
    lost_all_df.to_csv(
        outdir / "diseases_losing_all_variant_links.tsv",
        sep="\t",
        index=False
    )

    gained_df = new[
        new.apply(
            lambda r: (r["DiseaseID"], r["Variant_ID"]) in gained,
            axis=1
        )
    ].copy()
    gained_df.to_csv(
        outdir / "gained_canonical_links.tsv",
        sep="\t",
        index=False
    )

    summary = pd.DataFrame([
        ["Baseline_associations", len(old)],
        ["Canonical_associations", len(new)],
        ["Lost_association_keys", len(lost)],
        ["Gained_association_keys", len(gained)],
        ["Baseline_diseases", old["DiseaseID"].nunique()],
        ["Canonical_diseases", new["DiseaseID"].nunique()],
        ["Diseases_losing_all_variant_links", len(diseases_losing_all)],
    ], columns=["Metric", "Value"])

    summary.to_csv(
        outdir / "pre_mondo_vs_canonical_summary.tsv",
        sep="\t",
        index=False
    )

    print("PRE-MONDO VS CANONICAL DISEASE-VARIANT QC")
    print(summary.to_string(index=False))

    print("\nDiseases losing all variant links:")
    if len(lost_all_df):
        print(
            lost_all_df[
                [c for c in [
                    "DiseaseID", "Disease_Name", "MONDO_ID",
                    "OMIM_ID", "Orphanet_ID", "MedGen_UMLS_CUI",
                    "Lost_Associations", "Lost_Unique_Variants",
                    "Variants_Still_Map_Elsewhere"
                ] if c in lost_all_df.columns]
            ].to_string(index=False)
        )
    else:
        print("None")

    print(f"\nReports written to: {outdir}")


if __name__ == "__main__":
    main()
