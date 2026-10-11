#!/usr/bin/env python3
"""
ODDB clinical-report ChEMBL mismatch severity audit.

AUDIT ONLY. No canonical/frozen files are modified.

Classifies source-ChEMBL mismatches into:
- missing_canonical_chembl_exact_name_candidate
- missing_canonical_chembl_alias_candidate
- different_chembl_same_name_conflict
- different_chembl_alias_conflict

The purpose is to separate identifier-enrichment gaps from true
multi-entity/form/identity conflicts.
"""

import argparse
import re
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def norm_name(x):
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())


def split_multi(x):
    return [
        v.strip()
        for v in re.split(r"\s*[|;,]\s*", clean(x))
        if v.strip()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--classified-mismatches", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    mm = pd.read_csv(
        args.classified_mismatches, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    drug_lookup = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in drugs.iterrows()
    }

    rows = []

    for _, r in mm.iterrows():
        did = clean(r["Drug_ID"])
        d = drug_lookup.get(did, {})

        canonical_chembl = clean(d.get("ChEMBL_ID"))
        source_chembl = clean(r.get("Source_Drug_ID"))

        preferred = clean(d.get("Preferred_Name"))
        normalized = clean(d.get("Normalized_Name"))
        source_name = clean(r.get("Source_Drug_Name"))

        source_norm = norm_name(source_name)

        candidate_names = {
            norm_name(preferred),
            norm_name(normalized),
        }

        for col in [
            "Alternative_Names_From_Legacy",
            "OpenTargets_Synonyms",
            "OpenTargets_Trade_Names",
        ]:
            if col in d:
                candidate_names.update(
                    norm_name(x)
                    for x in split_multi(d.get(col, ""))
                    if norm_name(x)
                )

        candidate_names.discard("")

        exact_or_known_name = source_norm in candidate_names

        if not canonical_chembl:
            if exact_or_known_name:
                severity = (
                    "missing_canonical_chembl_exact_name_candidate"
                )
                recommendation = (
                    "high_priority_identifier_enrichment_review"
                )
            else:
                severity = (
                    "missing_canonical_chembl_alias_candidate"
                )
                recommendation = (
                    "manual_alias_identity_review_before_enrichment"
                )
        else:
            if exact_or_known_name:
                severity = "different_chembl_same_name_conflict"
                recommendation = (
                    "review_ChEMBL_parent_form_or_duplicate_entity"
                )
            else:
                severity = "different_chembl_alias_conflict"
                recommendation = (
                    "manual_identity_review_do_not_propagate"
                )

        rows.append({
            "Drug_ID": did,
            "Drug_Name": preferred,
            "Canonical_ChEMBL_ID": canonical_chembl,
            "Source_Drug_ID": source_chembl,
            "Source_Drug_Name": source_name,
            "Clinical_Report_ID":
                clean(r.get("Clinical_Report_ID")),
            "OpenTargets_Clinical_Report_ID":
                clean(r.get("OpenTargets_Clinical_Report_ID")),
            "Match_Method": clean(r.get("Match_Method")),
            "Identity_Severity_Class": severity,
            "Recommended_Action": recommendation,
        })

    detail = pd.DataFrame(rows)

    pair_summary = (
        detail.groupby(
            [
                "Drug_ID",
                "Drug_Name",
                "Canonical_ChEMBL_ID",
                "Source_Drug_ID",
                "Source_Drug_Name",
                "Identity_Severity_Class",
                "Recommended_Action",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="Clinical_Report_Link_Count")
        .sort_values(
            ["Clinical_Report_Link_Count", "Drug_Name"],
            ascending=[False, True],
        )
    )

    link_counts = (
        detail["Identity_Severity_Class"]
        .value_counts()
        .rename_axis("Identity_Severity_Class")
        .reset_index(name="Clinical_Report_Link_Count")
    )

    pair_counts = (
        pair_summary["Identity_Severity_Class"]
        .value_counts()
        .rename_axis("Identity_Severity_Class")
        .reset_index(name="Unique_Drug_SourceChEMBL_Pairs")
    )

    no_canonical = detail[
        detail["Canonical_ChEMBL_ID"].eq("")
    ].copy()

    different = detail[
        detail["Canonical_ChEMBL_ID"].ne("")
    ].copy()

    summary = pd.DataFrame([
        ["Mismatch_links_total", len(detail)],
        ["Unique_mismatch_pairs", len(pair_summary)],
        ["Links_with_missing_canonical_ChEMBL", len(no_canonical)],
        ["Unique_pairs_with_missing_canonical_ChEMBL",
         len(
             no_canonical[
                 ["Drug_ID", "Source_Drug_ID"]
             ].drop_duplicates()
         )],
        ["Links_with_different_canonical_ChEMBL", len(different)],
        ["Unique_pairs_with_different_canonical_ChEMBL",
         len(
             different[
                 ["Drug_ID", "Source_Drug_ID"]
             ].drop_duplicates()
         )],
        ["Unique_drugs_with_different_canonical_ChEMBL",
         different["Drug_ID"].nunique()],
    ], columns=["Metric", "Value"])

    detail.to_csv(
        outdir / "drug_chembl_mismatch_severity_detail.tsv",
        sep="\t", index=False
    )

    pair_summary.to_csv(
        outdir / "drug_chembl_mismatch_severity_by_pair.tsv",
        sep="\t", index=False
    )

    no_canonical.to_csv(
        outdir / "missing_canonical_chembl_candidates.tsv",
        sep="\t", index=False
    )

    different.to_csv(
        outdir / "different_canonical_chembl_conflicts.tsv",
        sep="\t", index=False
    )

    link_counts.to_csv(
        outdir / "drug_chembl_mismatch_severity_link_counts.tsv",
        sep="\t", index=False
    )

    pair_counts.to_csv(
        outdir / "drug_chembl_mismatch_severity_pair_counts.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "drug_chembl_mismatch_severity_summary.tsv",
        sep="\t", index=False
    )

    print("ODDB DRUG ChEMBL MISMATCH SEVERITY AUDIT")
    print(summary.to_string(index=False))

    print("\nBy clinical-report links:")
    print(link_counts.to_string(index=False))

    print("\nBy unique drug/source-ChEMBL pairs:")
    print(pair_counts.to_string(index=False))

    print("\nDifferent canonical ChEMBL conflicts:")
    if len(different):
        print(
            pair_summary[
                pair_summary[
                    "Canonical_ChEMBL_ID"
                ].ne("")
            ].to_string(index=False)
        )
    else:
        print("None")

    print("\nReports:", outdir)
    print(
        "\nAUDIT ONLY: no canonical or frozen files were modified."
    )


if __name__ == "__main__":
    main()
