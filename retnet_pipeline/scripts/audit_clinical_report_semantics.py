#!/usr/bin/env python3
"""
Audit semantics of ODDB-relevant Open Targets clinical reports.

No canonical files are modified.

Outputs:
- value counts for report type/origin/source/provider/stage/status
- single-disease/single-drug reports
- candidate pair-specific indication reports
- single-pair non-indication reports
- multi-entity reports
- NCT-linked single-pair reports
- summary metrics

This audit is intentionally conservative: it does NOT promote anything into
Disease_Drug_Evidence_v1.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def write_counts(df, col, outpath):
    if col not in df.columns:
        pd.DataFrame(columns=[col, "Count"]).to_csv(
            outpath, sep="\t", index=False
        )
        return

    out = (
        df[col]
        .fillna("")
        .astype(str)
        .replace("", "<blank>")
        .value_counts(dropna=False)
        .rename_axis(col)
        .reset_index(name="Count")
    )
    out.to_csv(outpath, sep="\t", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clinical-reports", required=True)
    ap.add_argument("--disease-report-links", required=True)
    ap.add_argument("--drug-report-links", required=True)
    ap.add_argument("--clinical-trials", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    cr = pd.read_csv(
        args.clinical_reports, sep="\t", dtype=str
    ).fillna("")
    dr = pd.read_csv(
        args.disease_report_links, sep="\t", dtype=str
    ).fillna("")
    gr = pd.read_csv(
        args.drug_report_links, sep="\t", dtype=str
    ).fillna("")
    ct = pd.read_csv(
        args.clinical_trials, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # Sanity checks
    # ------------------------------------------------------------
    problems = []

    if cr["Clinical_Report_ID"].duplicated().any():
        problems.append("duplicate Clinical_Report_ID")

    valid_cr = set(cr["Clinical_Report_ID"])

    if (~dr["Clinical_Report_ID"].isin(valid_cr)).any():
        problems.append("invalid Disease->Clinical_Report FK")

    if (~gr["Clinical_Report_ID"].isin(valid_cr)).any():
        problems.append("invalid Drug->Clinical_Report FK")

    # ------------------------------------------------------------
    # Core semantic counts
    # ------------------------------------------------------------
    for col, fn in [
        ("Report_Type", "counts_report_type.tsv"),
        ("Origin", "counts_origin.tsv"),
        ("Source", "counts_source.tsv"),
        ("Provider", "counts_provider.tsv"),
        ("Clinical_Stage", "counts_clinical_stage.tsv"),
        ("Phase_From_Source", "counts_phase_from_source.tsv"),
        ("Trial_Phase", "counts_trial_phase.tsv"),
        ("Trial_Overall_Status", "counts_trial_overall_status.tsv"),
        ("Trial_Study_Type", "counts_trial_study_type.tsv"),
        ("Trial_Primary_Purpose", "counts_trial_primary_purpose.tsv"),
        ("Entity_Context", "counts_entity_context.tsv"),
    ]:
        write_counts(cr, col, outdir / fn)

    # Combined semantic profile
    profile_cols = [
        c for c in [
            "Report_Type",
            "Origin",
            "Source",
            "Provider",
            "Clinical_Stage",
            "Entity_Context",
        ]
        if c in cr.columns
    ]

    if profile_cols:
        profile = (
            cr.groupby(profile_cols, dropna=False)
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
        )
    else:
        profile = pd.DataFrame()

    profile.to_csv(
        outdir / "clinical_report_semantic_profiles.tsv",
        sep="\t", index=False
    )

    # ------------------------------------------------------------
    # Candidate subsets
    # ------------------------------------------------------------
    single = cr[
        cr["Entity_Context"].eq("single_disease_single_drug")
    ].copy()

    multi = cr[
        cr["Entity_Context"].eq("multi_entity_report_context")
    ].copy()

    # Conservative indication candidate:
    # - exactly one mapped ODDB disease
    # - exactly one mapped ODDB drug
    # - source report explicitly says INDICATION
    indication = single[
        single["Report_Type"]
        .str.upper()
        .eq("INDICATION")
    ].copy()

    non_indication = single[
        ~single["Report_Type"]
        .str.upper()
        .eq("INDICATION")
    ].copy()

    nct_single = single[
        single["NCT_IDs"].str.strip().ne("")
    ].copy()

    indication_nct = indication[
        indication["NCT_IDs"].str.strip().ne("")
    ].copy()

    indication_non_nct = indication[
        indication["NCT_IDs"].str.strip().eq("")
    ].copy()

    single.to_csv(
        outdir / "single_disease_single_drug_reports.tsv",
        sep="\t", index=False
    )

    multi.to_csv(
        outdir / "multi_entity_reports.tsv",
        sep="\t", index=False
    )

    indication.to_csv(
        outdir / "candidate_pair_specific_indication_reports.tsv",
        sep="\t", index=False
    )

    non_indication.to_csv(
        outdir / "single_pair_non_indication_reports.tsv",
        sep="\t", index=False
    )

    nct_single.to_csv(
        outdir / "single_pair_nct_reports.tsv",
        sep="\t", index=False
    )

    indication_nct.to_csv(
        outdir / "candidate_indication_nct_reports.tsv",
        sep="\t", index=False
    )

    indication_non_nct.to_csv(
        outdir / "candidate_indication_non_nct_reports.tsv",
        sep="\t", index=False
    )

    # ------------------------------------------------------------
    # Link cardinalities
    # ------------------------------------------------------------
    disease_counts = (
        dr.groupby("Clinical_Report_ID")["DiseaseID"]
        .nunique()
        .rename("Disease_Link_Count")
    )

    drug_counts = (
        gr.groupby("Clinical_Report_ID")["Drug_ID"]
        .nunique()
        .rename("Drug_Link_Count")
    )

    cardinality = (
        cr[["Clinical_Report_ID"]]
        .merge(
            disease_counts,
            left_on="Clinical_Report_ID",
            right_index=True,
            how="left",
        )
        .merge(
            drug_counts,
            left_on="Clinical_Report_ID",
            right_index=True,
            how="left",
        )
        .fillna(0)
    )

    cardinality["Disease_Link_Count"] = (
        cardinality["Disease_Link_Count"].astype(int)
    )
    cardinality["Drug_Link_Count"] = (
        cardinality["Drug_Link_Count"].astype(int)
    )

    cardinality.to_csv(
        outdir / "clinical_report_link_cardinality.tsv",
        sep="\t", index=False
    )

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    nct_ids = set(
        x
        for vals in cr["NCT_IDs"].astype(str)
        for x in [v.strip() for v in vals.split("|")]
        if x
    )

    summary = pd.DataFrame([
        ["Relevant_clinical_reports", len(cr)],
        ["Single_disease_single_drug_reports", len(single)],
        ["Multi_entity_reports", len(multi)],
        ["Single_pair_INDICATION_reports", len(indication)],
        ["Single_pair_non_INDICATION_reports", len(non_indication)],
        ["Single_pair_NCT_reports", len(nct_single)],
        ["Single_pair_INDICATION_NCT_reports", len(indication_nct)],
        ["Single_pair_INDICATION_non_NCT_reports", len(indication_non_nct)],
        ["Unique_NCT_IDs_in_relevant_reports", len(nct_ids)],
        ["ClinicalTrial_rows", len(ct)],
        ["Unique_Report_Types",
         cr["Report_Type"].replace("", pd.NA).nunique()],
        ["Unique_Origins",
         cr["Origin"].replace("", pd.NA).nunique()],
        ["Unique_Sources",
         cr["Source"].replace("", pd.NA).nunique()],
        ["Unique_Providers",
         cr["Provider"].replace("", pd.NA).nunique()],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    summary.to_csv(
        outdir / "clinical_report_semantics_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        outdir / "clinical_report_semantics_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB CLINICAL REPORT SEMANTICS AUDIT")
    print(summary.to_string(index=False))

    print("\nTop report types:")
    print(
        cr["Report_Type"]
        .replace("", "<blank>")
        .value_counts()
        .head(20)
        .rename_axis("Report_Type")
        .reset_index(name="Count")
        .to_string(index=False)
    )

    print("\nTop sources:")
    print(
        cr["Source"]
        .replace("", "<blank>")
        .value_counts()
        .head(20)
        .rename_axis("Source")
        .reset_index(name="Count")
        .to_string(index=False)
    )

    print("\nTop origins:")
    print(
        cr["Origin"]
        .replace("", "<blank>")
        .value_counts()
        .head(20)
        .rename_axis("Origin")
        .reset_index(name="Count")
        .to_string(index=False)
    )

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nReports:", outdir)
    print(
        "\nNo records were promoted into Disease_Drug_Evidence_v1."
    )


if __name__ == "__main__":
    main()
