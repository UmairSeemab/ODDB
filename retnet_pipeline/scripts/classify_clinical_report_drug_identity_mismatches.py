#!/usr/bin/env python3
"""
Classify ODDB clinical-report drug identity mismatches.

AUDIT ONLY: does not modify canonical or frozen files.

For each clinical-report link where Source_Drug_ID is a ChEMBL ID that does
not belong to the currently linked canonical Drug_ID, classify the mismatch as:

1. source_chembl_maps_to_other_oddb_drug
   The source ChEMBL ID already belongs to a different Drug_v1 entity.
   -> likely remap candidate.

2. source_is_explicit_parent_of_current_drug
   Current drug has OpenTargets_Parent_ID == source ChEMBL ID.
   -> explicit parent/form context.

3. source_is_explicit_child_of_current_drug
   Another Drug_v1 entity with Source_Drug_ID has parent == current drug's
   ChEMBL ID.
   -> explicit child/form context.

4. source_chembl_absent_from_drug_master
   Source ChEMBL ID is not represented in Drug_v1.
   -> normalization candidate for future release.

5. other_identifier_mismatch
   Unexpected case requiring manual review.
"""

import argparse
import re
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def split_multi(x):
    return [
        v.strip().upper()
        for v in re.split(r"\s*[|;,]\s*", clean(x))
        if v.strip()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--drug-report-links", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    links = pd.read_csv(
        args.drug_report_links, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    chembl_cols = [
        c for c in [
            "ChEMBL_ID",
            "ChEMBL_ID_Alternative",
            "OpenTargets_Drug_IDs",
        ]
        if c in drugs.columns
    ]

    # Drug_ID -> record
    drug_lookup = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in drugs.iterrows()
    }

    # ChEMBL -> Drug_ID(s)
    chembl_to_drugs = {}

    # Parent ChEMBL -> child Drug_ID(s)
    parent_to_children = {}

    for _, r in drugs.iterrows():
        drug_id = clean(r["Drug_ID"])

        ids = set()
        for col in chembl_cols:
            ids.update(
                x for x in split_multi(r[col])
                if x.startswith("CHEMBL")
            )

        for chembl in ids:
            chembl_to_drugs.setdefault(
                chembl, set()
            ).add(drug_id)

        parent_id = clean(
            r.get("OpenTargets_Parent_ID")
        ).upper()

        if parent_id.startswith("CHEMBL"):
            parent_to_children.setdefault(
                parent_id, set()
            ).add(drug_id)

    rows = []

    for _, r in links.iterrows():
        current_drug_id = clean(r["Drug_ID"])
        source_chembl = clean(
            r.get("Source_Drug_ID")
        ).upper()

        if not source_chembl.startswith("CHEMBL"):
            continue

        current = drug_lookup.get(current_drug_id)
        if current is None:
            continue

        current_ids = set()
        for col in chembl_cols:
            current_ids.update(
                x for x in split_multi(
                    current.get(col, "")
                )
                if x.startswith("CHEMBL")
            )

        # Not a mismatch.
        if source_chembl in current_ids:
            continue

        current_primary = clean(
            current.get("ChEMBL_ID")
        ).upper()

        current_parent = clean(
            current.get("OpenTargets_Parent_ID")
        ).upper()

        source_candidates = chembl_to_drugs.get(
            source_chembl, set()
        )

        classification = ""
        related_drug_ids = set()
        relationship_note = ""

        # Current entity explicitly says source is its parent.
        if current_parent == source_chembl:
            classification = (
                "source_is_explicit_parent_of_current_drug"
            )
            related_drug_ids = set(source_candidates)
            relationship_note = (
                "Current Drug_v1 OpenTargets_Parent_ID equals "
                "Source_Drug_ID."
            )

        # Source ChEMBL corresponds to a Drug_v1 entity whose parent is
        # current drug's ChEMBL ID.
        elif source_candidates and current_primary:
            matching_children = {
                did for did in source_candidates
                if clean(
                    drug_lookup[did].get(
                        "OpenTargets_Parent_ID"
                    )
                ).upper() == current_primary
            }

            if matching_children:
                classification = (
                    "source_is_explicit_child_of_current_drug"
                )
                related_drug_ids = matching_children
                relationship_note = (
                    "Source ChEMBL belongs to a Drug_v1 entity whose "
                    "OpenTargets_Parent_ID equals current drug ChEMBL."
                )

            else:
                classification = (
                    "source_chembl_maps_to_other_oddb_drug"
                )
                related_drug_ids = set(source_candidates)
                relationship_note = (
                    "Source ChEMBL already belongs to another Drug_v1 "
                    "entity but no explicit direct parent relation to "
                    "the current drug was found."
                )

        elif source_candidates:
            classification = (
                "source_chembl_maps_to_other_oddb_drug"
            )
            related_drug_ids = set(source_candidates)
            relationship_note = (
                "Source ChEMBL already belongs to another Drug_v1 entity."
            )

        elif source_chembl not in chembl_to_drugs:
            classification = (
                "source_chembl_absent_from_drug_master"
            )
            relationship_note = (
                "Source ChEMBL is not represented in current Drug_v1."
            )

        else:
            classification = "other_identifier_mismatch"
            relationship_note = "Unexpected mismatch requiring review."

        related_names = [
            clean(
                drug_lookup[x].get("Preferred_Name")
            )
            for x in sorted(related_drug_ids)
            if x in drug_lookup
        ]

        rows.append({
            "Drug_ID": current_drug_id,
            "Drug_Name": clean(
                current.get("Preferred_Name")
            ),
            "Canonical_ChEMBL_ID":
                current_primary,
            "Canonical_OpenTargets_Parent_ID":
                current_parent,
            "Source_Drug_ID": source_chembl,
            "Source_Drug_Name":
                clean(r.get("Source_Drug_Name")),
            "Match_Method":
                clean(r.get("Match_Method")),
            "Clinical_Report_ID":
                clean(r.get("Clinical_Report_ID")),
            "OpenTargets_Clinical_Report_ID":
                clean(
                    r.get(
                        "OpenTargets_Clinical_Report_ID"
                    )
                ),
            "Classification": classification,
            "Related_ODDB_Drug_IDs":
                " | ".join(sorted(related_drug_ids)),
            "Related_ODDB_Drug_Names":
                " | ".join(sorted(set(related_names))),
            "Relationship_Note":
                relationship_note,
        })

    detail = pd.DataFrame(rows)

    if len(detail):
        summary_by_pair = (
            detail.groupby(
                [
                    "Drug_ID",
                    "Drug_Name",
                    "Canonical_ChEMBL_ID",
                    "Source_Drug_ID",
                    "Source_Drug_Name",
                    "Classification",
                    "Related_ODDB_Drug_IDs",
                    "Related_ODDB_Drug_Names",
                ],
                dropna=False,
            )
            .size()
            .reset_index(
                name="Clinical_Report_Link_Count"
            )
            .sort_values(
                [
                    "Clinical_Report_Link_Count",
                    "Drug_Name",
                ],
                ascending=[False, True],
            )
        )

        class_counts = (
            detail["Classification"]
            .value_counts()
            .rename_axis("Classification")
            .reset_index(
                name="Clinical_Report_Link_Count"
            )
        )

        unique_pair_class_counts = (
            summary_by_pair["Classification"]
            .value_counts()
            .rename_axis("Classification")
            .reset_index(
                name="Unique_Drug_SourceChEMBL_Pairs"
            )
        )
    else:
        summary_by_pair = pd.DataFrame()
        class_counts = pd.DataFrame()
        unique_pair_class_counts = pd.DataFrame()

    summary = pd.DataFrame([
        [
            "Mismatch_clinical_report_links",
            len(detail)
        ],
        [
            "Unique_current_ODDB_drugs_in_mismatch",
            detail["Drug_ID"].nunique()
            if len(detail) else 0
        ],
        [
            "Unique_source_ChEMBL_IDs_in_mismatch",
            detail["Source_Drug_ID"].nunique()
            if len(detail) else 0
        ],
        [
            "Unique_drug_sourceChEMBL_mismatch_pairs",
            len(summary_by_pair)
        ],
        [
            "Links_source_maps_to_other_ODDB_drug",
            int(
                detail["Classification"]
                .eq(
                    "source_chembl_maps_to_other_oddb_drug"
                )
                .sum()
            )
            if len(detail) else 0
        ],
        [
            "Links_source_is_explicit_parent",
            int(
                detail["Classification"]
                .eq(
                    "source_is_explicit_parent_of_current_drug"
                )
                .sum()
            )
            if len(detail) else 0
        ],
        [
            "Links_source_is_explicit_child",
            int(
                detail["Classification"]
                .eq(
                    "source_is_explicit_child_of_current_drug"
                )
                .sum()
            )
            if len(detail) else 0
        ],
        [
            "Links_source_ChEMBL_absent_from_Drug_v1",
            int(
                detail["Classification"]
                .eq(
                    "source_chembl_absent_from_drug_master"
                )
                .sum()
            )
            if len(detail) else 0
        ],
        [
            "Links_other_identifier_mismatch",
            int(
                detail["Classification"]
                .eq(
                    "other_identifier_mismatch"
                )
                .sum()
            )
            if len(detail) else 0
        ],
    ], columns=["Metric", "Value"])

    detail.to_csv(
        outdir /
        "clinical_report_drug_identity_mismatch_classified.tsv",
        sep="\t",
        index=False,
    )

    summary_by_pair.to_csv(
        outdir /
        "clinical_report_drug_identity_mismatch_by_pair.tsv",
        sep="\t",
        index=False,
    )

    class_counts.to_csv(
        outdir /
        "clinical_report_drug_identity_mismatch_class_counts.tsv",
        sep="\t",
        index=False,
    )

    unique_pair_class_counts.to_csv(
        outdir /
        "clinical_report_drug_identity_mismatch_unique_pair_counts.tsv",
        sep="\t",
        index=False,
    )

    summary.to_csv(
        outdir /
        "clinical_report_drug_identity_classification_summary.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB CLINICAL-REPORT DRUG IDENTITY CLASSIFICATION")
    print(summary.to_string(index=False))

    print("\nClassification by links:")
    if len(class_counts):
        print(class_counts.to_string(index=False))
    else:
        print("None")

    print("\nTop mismatch pairs:")
    if len(summary_by_pair):
        print(
            summary_by_pair.head(60)
            .to_string(index=False)
        )
    else:
        print("None")

    print("\nReports:", outdir)
    print(
        "\nAUDIT ONLY: frozen and canonical files were not modified."
    )


if __name__ == "__main__":
    main()
