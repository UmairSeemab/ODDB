#!/usr/bin/env python3
"""
Audit pair-specific ODDB clinical reports against the current canonical
Disease_Drug_Association_v1.

Purpose
-------
Use only clinical reports with:
- exactly one mapped ODDB disease
- exactly one mapped ODDB drug
- Report_Type == INDICATION

For those reports:
- derive the unique DiseaseID + Drug_ID pair
- compare against current canonical disease-drug pairs
- classify evidence by origin/source
- distinguish clinical-trial investigation from label/regulatory/curated
  indication evidence

NO canonical files are modified.
"""

import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd


def clean(x):
    return str(x or "").strip()


def uniq_join(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return " | ".join(out)


def classify_evidence(origin, source):
    origin_u = clean(origin).upper()
    source_u = clean(source).upper()

    if origin_u == "CLINICAL_TRIAL" or source_u == "CLINICALTRIALS.GOV":
        return "clinical_trial_investigation"

    if origin_u == "DRUG_LABEL" or source_u == "DAILYMED":
        return "drug_label_indication"

    if origin_u == "REGULATORY_AGENCY":
        return "regulatory_indication"

    if origin_u == "CURATED_RESOURCE":
        return "curated_indication"

    return "other_indication_context"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clinical-reports", required=True)
    ap.add_argument("--disease-report-links", required=True)
    ap.add_argument("--drug-report-links", required=True)
    ap.add_argument("--canonical-dda", required=True)
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
    dda = pd.read_csv(
        args.canonical_dda, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    problems = []

    # ------------------------------------------------------------
    # Select pair-specific indication reports
    # ------------------------------------------------------------
    pair_reports = cr[
        cr["Entity_Context"].eq("single_disease_single_drug")
        & cr["Report_Type"].str.upper().eq("INDICATION")
    ].copy()

    # One disease / one drug link expected for these report IDs.
    dr_sub = dr[
        dr["Clinical_Report_ID"].isin(pair_reports["Clinical_Report_ID"])
    ].copy()

    gr_sub = gr[
        gr["Clinical_Report_ID"].isin(pair_reports["Clinical_Report_ID"])
    ].copy()

    d_counts = (
        dr_sub.groupby("Clinical_Report_ID")["DiseaseID"]
        .nunique()
    )
    g_counts = (
        gr_sub.groupby("Clinical_Report_ID")["Drug_ID"]
        .nunique()
    )

    bad_disease_cardinality = set(
        d_counts[d_counts != 1].index
    )
    bad_drug_cardinality = set(
        g_counts[g_counts != 1].index
    )

    if bad_disease_cardinality:
        problems.append(
            "Some single-pair reports do not have exactly one disease link"
        )

    if bad_drug_cardinality:
        problems.append(
            "Some single-pair reports do not have exactly one drug link"
        )

    disease_lookup = (
        dr_sub.drop_duplicates("Clinical_Report_ID")
        .set_index("Clinical_Report_ID")[
            ["DiseaseID", "Disease_Name"]
        ]
        .to_dict("index")
    )

    drug_lookup = (
        gr_sub.drop_duplicates("Clinical_Report_ID")
        .set_index("Clinical_Report_ID")[
            ["Drug_ID", "Drug_Name"]
        ]
        .to_dict("index")
    )

    # ------------------------------------------------------------
    # Report-level pair table
    # ------------------------------------------------------------
    report_pair_rows = []

    for _, r in pair_reports.iterrows():
        rid = clean(r["Clinical_Report_ID"])

        d = disease_lookup.get(rid)
        g = drug_lookup.get(rid)

        if not d or not g:
            continue

        subtype = classify_evidence(
            r.get("Origin"),
            r.get("Source"),
        )

        report_pair_rows.append({
            "Clinical_Report_ID": rid,
            "OpenTargets_Clinical_Report_ID":
                clean(r.get("OpenTargets_Clinical_Report_ID")),
            "DiseaseID": clean(d["DiseaseID"]),
            "Disease_Name": clean(d["Disease_Name"]),
            "Drug_ID": clean(g["Drug_ID"]),
            "Drug_Name": clean(g["Drug_Name"]),
            "Evidence_Subtype": subtype,
            "Origin": clean(r.get("Origin")),
            "Source": clean(r.get("Source")),
            "Provider": clean(r.get("Provider")),
            "Clinical_Stage": clean(r.get("Clinical_Stage")),
            "Phase_From_Source": clean(r.get("Phase_From_Source")),
            "Trial_Phase": clean(r.get("Trial_Phase")),
            "Trial_Overall_Status": clean(r.get("Trial_Overall_Status")),
            "NCT_IDs": clean(r.get("NCT_IDs")),
            "Title": clean(r.get("Title")),
            "URL": clean(r.get("URL")),
        })

    report_pairs = pd.DataFrame(report_pair_rows)

    canonical_pairs = set(
        zip(dda["DiseaseID"], dda["Drug_ID"])
    )

    report_pairs["Already_Canonical_Pair"] = [
        "Yes" if (d, g) in canonical_pairs else "No"
        for d, g in zip(
            report_pairs["DiseaseID"],
            report_pairs["Drug_ID"],
        )
    ]

    # ------------------------------------------------------------
    # Aggregate to unique pair
    # ------------------------------------------------------------
    pair_summary_rows = []

    for (did, drug_id), g in report_pairs.groupby(
        ["DiseaseID", "Drug_ID"],
        sort=True,
    ):
        subtypes = uniq_join(g["Evidence_Subtype"])
        origins = uniq_join(g["Origin"])
        sources = uniq_join(g["Source"])

        subtype_set = set(g["Evidence_Subtype"])

        has_trial = "clinical_trial_investigation" in subtype_set
        has_label = "drug_label_indication" in subtype_set
        has_reg = "regulatory_indication" in subtype_set
        has_curated = "curated_indication" in subtype_set

        if has_label or has_reg:
            evidence_strength_class = "label_or_regulatory_indication"
        elif has_trial and (has_curated):
            evidence_strength_class = "trial_plus_curated_indication"
        elif has_trial:
            evidence_strength_class = "clinical_trial_investigation_only"
        elif has_curated:
            evidence_strength_class = "curated_indication_only"
        else:
            evidence_strength_class = "other_indication_context"

        pair_summary_rows.append({
            "DiseaseID": did,
            "Disease_Name": clean(g.iloc[0]["Disease_Name"]),
            "Drug_ID": drug_id,
            "Drug_Name": clean(g.iloc[0]["Drug_Name"]),
            "Clinical_Report_Count": len(g),
            "Evidence_Subtypes": subtypes,
            "Origins": origins,
            "Sources": sources,
            "NCT_IDs": uniq_join(g["NCT_IDs"]),
            "Clinical_Stages": uniq_join(g["Clinical_Stage"]),
            "Trial_Phases": uniq_join(g["Trial_Phase"]),
            "Trial_Statuses": uniq_join(g["Trial_Overall_Status"]),
            "Has_ClinicalTrial_Evidence": "Yes" if has_trial else "No",
            "Has_DrugLabel_Evidence": "Yes" if has_label else "No",
            "Has_Regulatory_Evidence": "Yes" if has_reg else "No",
            "Has_Curated_Indication_Evidence": "Yes" if has_curated else "No",
            "Evidence_Strength_Class": evidence_strength_class,
            "Already_Canonical_Pair":
                "Yes" if (did, drug_id) in canonical_pairs else "No",
        })

    pair_summary = pd.DataFrame(pair_summary_rows)

    existing = pair_summary[
        pair_summary["Already_Canonical_Pair"].eq("Yes")
    ].copy()

    new = pair_summary[
        pair_summary["Already_Canonical_Pair"].eq("No")
    ].copy()

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    subtype_counts = (
        report_pairs["Evidence_Subtype"]
        .value_counts()
        .rename_axis("Evidence_Subtype")
        .reset_index(name="Report_Count")
    )

    pair_class_counts = (
        pair_summary["Evidence_Strength_Class"]
        .value_counts()
        .rename_axis("Evidence_Strength_Class")
        .reset_index(name="Pair_Count")
    )

    summary = pd.DataFrame([
        ["Pair_specific_INDICATION_reports", len(report_pairs)],
        ["Unique_pair_specific_disease_drug_pairs", len(pair_summary)],
        ["Pairs_already_in_canonical_DDA", len(existing)],
        ["New_pairs_not_in_canonical_DDA", len(new)],
        ["Existing_canonical_DDA_pairs_total", len(canonical_pairs)],
        ["Pairs_with_clinical_trial_evidence",
         int(pair_summary["Has_ClinicalTrial_Evidence"].eq("Yes").sum())],
        ["Pairs_with_drug_label_evidence",
         int(pair_summary["Has_DrugLabel_Evidence"].eq("Yes").sum())],
        ["Pairs_with_regulatory_evidence",
         int(pair_summary["Has_Regulatory_Evidence"].eq("Yes").sum())],
        ["Pairs_with_curated_indication_evidence",
         int(
             pair_summary[
                 "Has_Curated_Indication_Evidence"
             ].eq("Yes").sum()
         )],
        ["New_pairs_with_label_or_regulatory_evidence",
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
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------
    # Write
    # ------------------------------------------------------------
    report_pairs.to_csv(
        outdir / "pair_specific_clinical_report_evidence.tsv",
        sep="\t", index=False
    )

    pair_summary.to_csv(
        outdir / "pair_specific_clinical_report_pair_summary.tsv",
        sep="\t", index=False
    )

    existing.to_csv(
        outdir / "pair_specific_reports_existing_canonical_pairs.tsv",
        sep="\t", index=False
    )

    new.to_csv(
        outdir / "pair_specific_reports_new_pairs.tsv",
        sep="\t", index=False
    )

    subtype_counts.to_csv(
        outdir / "pair_specific_report_evidence_subtypes.tsv",
        sep="\t", index=False
    )

    pair_class_counts.to_csv(
        outdir / "pair_specific_pair_strength_classes.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "pair_specific_clinical_report_audit_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        outdir / "pair_specific_clinical_report_audit_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB PAIR-SPECIFIC CLINICAL REPORT AUDIT")
    print(summary.to_string(index=False))

    print("\nEvidence subtypes:")
    print(subtype_counts.to_string(index=False))

    print("\nPair evidence classes:")
    print(pair_class_counts.to_string(index=False))

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
