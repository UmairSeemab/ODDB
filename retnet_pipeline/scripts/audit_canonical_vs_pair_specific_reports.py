#!/usr/bin/env python3
"""
Audit current canonical ODDB disease-drug pairs against pair-specific
Open Targets clinical reports.

No canonical files are modified.

Questions answered:
1. Of the 291 current canonical pairs, which have:
   - legacy evidence
   - pair-specific clinical-report evidence
   - both
   - only aggregated Open Targets clinical_target evidence
2. Which 75 pair-specific clinical-report pairs are genuinely new?
3. What evidence-strength classes do the new pairs have?
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def yes(v):
    return clean(v).lower() == "yes"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical-dda", required=True)
    ap.add_argument("--canonical-evidence", required=True)
    ap.add_argument("--pair-summary", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    dda = pd.read_csv(
        args.canonical_dda, sep="\t", dtype=str
    ).fillna("")

    ev = pd.read_csv(
        args.canonical_evidence, sep="\t", dtype=str
    ).fillna("")

    pair = pd.read_csv(
        args.pair_summary, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    problems = []

    # ------------------------------------------------------------------
    # Current canonical pair set
    # ------------------------------------------------------------------
    canonical_pairs = set(
        zip(dda["DiseaseID"], dda["Drug_ID"])
    )

    pair_specific_pairs = set(
        zip(pair["DiseaseID"], pair["Drug_ID"])
    )

    # Evidence source lookup from canonical evidence table
    source_lookup = {}

    for (did, drug_id), g in ev.groupby(
        ["DiseaseID", "Drug_ID"],
        sort=False,
    ):
        sources = set(
            clean(x)
            for x in g["Evidence_Source"]
            if clean(x)
        )

        source_lookup[(did, drug_id)] = {
            "Has_Legacy_Evidence":
                "Yes" if "ODDB_legacy" in sources else "No",
            "Has_OpenTargets_Aggregate_Evidence":
                "Yes" if "Open_Targets" in sources else "No",
            "Canonical_Evidence_Sources":
                " | ".join(sorted(sources)),
            "Canonical_Evidence_Record_Count": len(g),
        }

    # Pair-specific report lookup
    pair_lookup = {
        (clean(r["DiseaseID"]), clean(r["Drug_ID"])): r.to_dict()
        for _, r in pair.iterrows()
    }

    # ------------------------------------------------------------------
    # Current canonical pairs
    # ------------------------------------------------------------------
    current_rows = []

    for _, r in dda.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        key = (did, drug_id)

        src = source_lookup.get(
            key,
            {
                "Has_Legacy_Evidence": "No",
                "Has_OpenTargets_Aggregate_Evidence": "No",
                "Canonical_Evidence_Sources": "",
                "Canonical_Evidence_Record_Count": 0,
            },
        )

        p = pair_lookup.get(key)

        has_pair_specific = p is not None

        if yes(src["Has_Legacy_Evidence"]) and has_pair_specific:
            support_class = "legacy_plus_pair_specific_report"

        elif yes(src["Has_Legacy_Evidence"]):
            support_class = "legacy_without_pair_specific_report"

        elif has_pair_specific:
            support_class = "pair_specific_report_without_legacy"

        elif yes(src["Has_OpenTargets_Aggregate_Evidence"]):
            support_class = "aggregate_opentargets_only_no_pair_specific_report"

        else:
            support_class = "other_or_missing_support"

        current_rows.append({
            "Disease_Drug_Association_ID":
                clean(r.get("Disease_Drug_Association_ID")),
            "DiseaseID": did,
            "Disease_Name": clean(r.get("Disease_Name")),
            "Drug_ID": drug_id,
            "Drug_Name": clean(r.get("Drug_Name")),
            "Has_Legacy_Evidence":
                src["Has_Legacy_Evidence"],
            "Has_OpenTargets_Aggregate_Evidence":
                src["Has_OpenTargets_Aggregate_Evidence"],
            "Has_Pair_Specific_Clinical_Report":
                "Yes" if has_pair_specific else "No",
            "Pair_Specific_Evidence_Strength_Class":
                clean(p.get("Evidence_Strength_Class"))
                if p else "",
            "Pair_Specific_Clinical_Report_Count":
                clean(p.get("Clinical_Report_Count"))
                if p else "",
            "Pair_Specific_Sources":
                clean(p.get("Sources"))
                if p else "",
            "Current_Support_Class": support_class,
            "Canonical_Evidence_Sources":
                src["Canonical_Evidence_Sources"],
            "Canonical_Evidence_Record_Count":
                src["Canonical_Evidence_Record_Count"],
        })

    current = pd.DataFrame(current_rows)

    # ------------------------------------------------------------------
    # New pair-specific report pairs not in current canonical DDA
    # ------------------------------------------------------------------
    new = pair[
        ~pair.apply(
            lambda r:
                (clean(r["DiseaseID"]), clean(r["Drug_ID"]))
                in canonical_pairs,
            axis=1,
        )
    ].copy()

    existing = pair[
        pair.apply(
            lambda r:
                (clean(r["DiseaseID"]), clean(r["Drug_ID"]))
                in canonical_pairs,
            axis=1,
        )
    ].copy()

    # ------------------------------------------------------------------
    # Current canonical pairs lacking pair-specific source-level reports
    # ------------------------------------------------------------------
    current_without_pair_specific = current[
        current["Has_Pair_Specific_Clinical_Report"].eq("No")
    ].copy()

    aggregate_only = current[
        current["Current_Support_Class"].eq(
            "aggregate_opentargets_only_no_pair_specific_report"
        )
    ].copy()

    legacy_without_pair_specific = current[
        current["Current_Support_Class"].eq(
            "legacy_without_pair_specific_report"
        )
    ].copy()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    if len(current) != len(dda):
        problems.append("current pair audit row count differs from DDA")

    if len(existing) + len(new) != len(pair):
        problems.append("pair-specific partition does not sum to input")

    if current.duplicated(["DiseaseID", "Drug_ID"]).any():
        problems.append("duplicate canonical DiseaseID + Drug_ID pair")

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------
    current_class_counts = (
        current["Current_Support_Class"]
        .value_counts()
        .rename_axis("Current_Support_Class")
        .reset_index(name="Pair_Count")
    )

    new_strength_counts = (
        new["Evidence_Strength_Class"]
        .value_counts()
        .rename_axis("Evidence_Strength_Class")
        .reset_index(name="New_Pair_Count")
    )

    summary = pd.DataFrame([
        ["Current_canonical_pairs", len(canonical_pairs)],
        ["Pair_specific_report_pairs", len(pair_specific_pairs)],
        ["Pair_specific_pairs_already_canonical", len(existing)],
        ["Pair_specific_new_pairs", len(new)],
        ["Current_pairs_without_pair_specific_report",
         len(current_without_pair_specific)],
        ["Current_aggregate_OpenTargets_only_without_pair_specific_report",
         len(aggregate_only)],
        ["Current_legacy_pairs_without_pair_specific_report",
         len(legacy_without_pair_specific)],
        ["Current_pairs_with_legacy_and_pair_specific_report",
         int(
             current["Current_Support_Class"]
             .eq("legacy_plus_pair_specific_report")
             .sum()
         )],
        ["Current_pairs_with_pair_specific_report_without_legacy",
         int(
             current["Current_Support_Class"]
             .eq("pair_specific_report_without_legacy")
             .sum()
         )],
        ["New_pairs_label_or_regulatory",
         int(
             new["Evidence_Strength_Class"]
             .eq("label_or_regulatory_indication")
             .sum()
         )],
        ["New_pairs_trial_only",
         int(
             new["Evidence_Strength_Class"]
             .eq("clinical_trial_investigation_only")
             .sum()
         )],
        ["New_pairs_trial_plus_curated",
         int(
             new["Evidence_Strength_Class"]
             .eq("trial_plus_curated_indication")
             .sum()
         )],
        ["New_pairs_curated_only",
         int(
             new["Evidence_Strength_Class"]
             .eq("curated_indication_only")
             .sum()
         )],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    current.to_csv(
        outdir / "current_canonical_pair_support_audit.tsv",
        sep="\t",
        index=False,
    )

    current_without_pair_specific.to_csv(
        outdir / "current_pairs_without_pair_specific_report.tsv",
        sep="\t",
        index=False,
    )

    aggregate_only.to_csv(
        outdir /
        "current_aggregate_opentargets_only_without_pair_specific_report.tsv",
        sep="\t",
        index=False,
    )

    legacy_without_pair_specific.to_csv(
        outdir / "current_legacy_without_pair_specific_report.tsv",
        sep="\t",
        index=False,
    )

    existing.to_csv(
        outdir / "pair_specific_existing_pairs.tsv",
        sep="\t",
        index=False,
    )

    new.to_csv(
        outdir / "pair_specific_new_pairs.tsv",
        sep="\t",
        index=False,
    )

    current_class_counts.to_csv(
        outdir / "current_support_class_counts.tsv",
        sep="\t",
        index=False,
    )

    new_strength_counts.to_csv(
        outdir / "new_pair_strength_class_counts.tsv",
        sep="\t",
        index=False,
    )

    summary.to_csv(
        outdir / "canonical_vs_pair_specific_summary.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        outdir / "canonical_vs_pair_specific_problems.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB CANONICAL VS PAIR-SPECIFIC CLINICAL REPORT AUDIT")
    print(summary.to_string(index=False))

    print("\nCurrent canonical support classes:")
    print(current_class_counts.to_string(index=False))

    print("\nNew pair-specific evidence classes:")
    print(new_strength_counts.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nReports:", outdir)
    print(
        "\nNo canonical disease-drug associations or evidence records "
        "were modified."
    )


if __name__ == "__main__":
    main()
