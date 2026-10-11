#!/usr/bin/env python3
"""
Audit ODDB v1 drug parent/form relationships and clinical-report drug-ID mismatches.

This is AUDIT ONLY.
It does not modify any canonical or frozen files.

Outputs
-------
1. Explicit Open Targets parent relationships resolvable inside Drug_v1.
2. Parent IDs that do not resolve to another canonical ODDB drug.
3. Clinical-report links where Source_Drug_ID differs from the canonical
   drug's ChEMBL/OpenTargets identifiers and mapping relied on name matching.
4. Summary report.
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

    # ------------------------------------------------------------
    # Build ChEMBL -> canonical ODDB drug index
    # ------------------------------------------------------------
    chembl_cols = [
        c for c in [
            "ChEMBL_ID",
            "ChEMBL_ID_Alternative",
            "OpenTargets_Drug_IDs",
        ]
        if c in drugs.columns
    ]

    chembl_to_drugs = {}

    for _, r in drugs.iterrows():
        did = clean(r["Drug_ID"])

        ids = set()
        for col in chembl_cols:
            ids.update(
                x for x in split_multi(r[col])
                if x.startswith("CHEMBL")
            )

        for chembl in ids:
            chembl_to_drugs.setdefault(chembl, set()).add(did)

    drug_lookup = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in drugs.iterrows()
    }

    # ------------------------------------------------------------
    # Explicit Open Targets parent relationships
    # ------------------------------------------------------------
    parent_rows = []
    unresolved_parent_rows = []
    ambiguous_parent_rows = []

    if "OpenTargets_Parent_ID" in drugs.columns:
        for _, r in drugs.iterrows():
            child_id = clean(r["Drug_ID"])
            parent_chembl = clean(
                r["OpenTargets_Parent_ID"]
            ).upper()

            if not parent_chembl:
                continue

            candidates = chembl_to_drugs.get(
                parent_chembl, set()
            )

            if len(candidates) == 1:
                parent_id = next(iter(candidates))
                pr = drug_lookup[parent_id]

                parent_rows.append({
                    "Child_Drug_ID": child_id,
                    "Child_Drug_Name":
                        clean(r.get("Preferred_Name")),
                    "Child_ChEMBL_ID":
                        clean(r.get("ChEMBL_ID")),
                    "Parent_Drug_ID": parent_id,
                    "Parent_Drug_Name":
                        clean(pr.get("Preferred_Name")),
                    "Parent_ChEMBL_ID": parent_chembl,
                    "Relationship_Type":
                        "OpenTargets_parent_form_relationship",
                    "Source": "Open Targets",
                    "Source_Release":
                        clean(r.get("OpenTargets_Source_Release"))
                        or "26.09",
                    "Evidence_Basis":
                        "explicit_OpenTargets_Parent_ID",
                })

            elif len(candidates) == 0:
                unresolved_parent_rows.append({
                    "Child_Drug_ID": child_id,
                    "Child_Drug_Name":
                        clean(r.get("Preferred_Name")),
                    "Child_ChEMBL_ID":
                        clean(r.get("ChEMBL_ID")),
                    "OpenTargets_Parent_ID":
                        parent_chembl,
                    "Reason":
                        "parent_ChEMBL_not_present_in_ODDB_Drug_v1",
                })

            else:
                ambiguous_parent_rows.append({
                    "Child_Drug_ID": child_id,
                    "Child_Drug_Name":
                        clean(r.get("Preferred_Name")),
                    "Child_ChEMBL_ID":
                        clean(r.get("ChEMBL_ID")),
                    "OpenTargets_Parent_ID":
                        parent_chembl,
                    "Candidate_Parent_Drug_IDs":
                        " | ".join(sorted(candidates)),
                    "Reason":
                        "parent_ChEMBL_maps_to_multiple_ODDB_drugs",
                })

    parent_df = pd.DataFrame(parent_rows)
    unresolved_parent = pd.DataFrame(
        unresolved_parent_rows
    )
    ambiguous_parent = pd.DataFrame(
        ambiguous_parent_rows
    )

    # ------------------------------------------------------------
    # Clinical-report source-ID mismatch audit
    # ------------------------------------------------------------
    mismatch_rows = []

    for _, r in links.iterrows():
        drug_id = clean(r["Drug_ID"])
        source_id = clean(
            r.get("Source_Drug_ID")
        ).upper()

        if not source_id.startswith("CHEMBL"):
            continue

        canonical = drug_lookup.get(drug_id)
        if canonical is None:
            continue

        canonical_ids = set()

        for col in chembl_cols:
            canonical_ids.update(
                x for x in split_multi(
                    canonical.get(col, "")
                )
                if x.startswith("CHEMBL")
            )

        if source_id in canonical_ids:
            continue

        method = clean(r.get("Match_Method"))

        mismatch_rows.append({
            "Drug_ID": drug_id,
            "Drug_Name":
                clean(canonical.get("Preferred_Name")),
            "Canonical_ChEMBL_ID":
                clean(canonical.get("ChEMBL_ID")),
            "Canonical_OpenTargets_Parent_ID":
                clean(
                    canonical.get("OpenTargets_Parent_ID")
                ),
            "Source_Drug_ID": source_id,
            "Source_Drug_Name":
                clean(r.get("Source_Drug_Name")),
            "Match_Method": method,
            "Clinical_Report_ID":
                clean(r.get("Clinical_Report_ID")),
            "OpenTargets_Clinical_Report_ID":
                clean(
                    r.get(
                        "OpenTargets_Clinical_Report_ID"
                    )
                ),
            "Mismatch_Class":
                (
                    "name_only_despite_source_chembl_mismatch"
                    if "exact_chembl_identifier" not in method
                    else
                    "unexpected_identifier_conflict"
                ),
        })

    mismatch = pd.DataFrame(mismatch_rows)

    # ------------------------------------------------------------
    # Source ChEMBL IDs involved in mismatches
    # ------------------------------------------------------------
    if len(mismatch):
        mismatch_summary = (
            mismatch.groupby(
                [
                    "Drug_ID",
                    "Drug_Name",
                    "Canonical_ChEMBL_ID",
                    "Source_Drug_ID",
                    "Mismatch_Class",
                ],
                dropna=False,
            )
            .size()
            .reset_index(name="Clinical_Report_Link_Count")
            .sort_values(
                [
                    "Clinical_Report_Link_Count",
                    "Drug_Name",
                ],
                ascending=[False, True],
            )
        )
    else:
        mismatch_summary = pd.DataFrame()

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    summary = pd.DataFrame([
        ["Drug_rows", len(drugs)],
        ["Explicit_OpenTargets_parent_relationships",
         len(parent_df)],
        ["Unique_child_drugs_with_resolved_parent",
         parent_df["Child_Drug_ID"].nunique()
         if len(parent_df) else 0],
        ["Unique_parent_drugs",
         parent_df["Parent_Drug_ID"].nunique()
         if len(parent_df) else 0],
        ["Unresolved_OpenTargets_parent_ID_rows",
         len(unresolved_parent)],
        ["Ambiguous_OpenTargets_parent_ID_rows",
         len(ambiguous_parent)],
        ["Drug_Clinical_Report_links", len(links)],
        ["Clinical_report_links_with_source_ChEMBL_mismatch",
         len(mismatch)],
        ["Unique_canonical_drugs_with_source_ID_mismatch",
         mismatch["Drug_ID"].nunique()
         if len(mismatch) else 0],
        ["Unique_source_ChEMBL_IDs_in_mismatch",
         mismatch["Source_Drug_ID"].nunique()
         if len(mismatch) else 0],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------
    parent_df.to_csv(
        outdir / "explicit_drug_parent_relationships.tsv",
        sep="\t", index=False
    )

    unresolved_parent.to_csv(
        outdir / "unresolved_drug_parent_ids.tsv",
        sep="\t", index=False
    )

    ambiguous_parent.to_csv(
        outdir / "ambiguous_drug_parent_ids.tsv",
        sep="\t", index=False
    )

    mismatch.to_csv(
        outdir / "clinical_report_drug_identifier_mismatches.tsv",
        sep="\t", index=False
    )

    mismatch_summary.to_csv(
        outdir /
        "clinical_report_drug_identifier_mismatch_summary.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "drug_identity_parent_audit_summary.tsv",
        sep="\t", index=False
    )

    print("ODDB DRUG IDENTITY / PARENT RELATIONSHIP AUDIT")
    print(summary.to_string(index=False))

    print("\nPEGAPTANIB / BEVASIRANIB / IPTACOPAN parent relationships:")
    if len(parent_df):
        target = parent_df[
            parent_df["Child_Drug_Name"]
            .str.upper()
            .str.contains(
                "PEGAPTANIB|BEVASIRANIB|IPTACOPAN",
                regex=True,
            )
            |
            parent_df["Parent_Drug_Name"]
            .str.upper()
            .str.contains(
                "PEGAPTANIB|BEVASIRANIB|IPTACOPAN",
                regex=True,
            )
        ]
        if len(target):
            print(target.to_string(index=False))
        else:
            print("No explicit parent relationship for these names.")
    else:
        print("No explicit parent relationships resolved.")

    print("\nIdentifier mismatch summary:")
    if len(mismatch_summary):
        print(mismatch_summary.head(50).to_string(index=False))
    else:
        print("None")

    print("\nReports:", outdir)
    print(
        "\nAUDIT ONLY: no canonical/frozen ODDB files were modified."
    )


if __name__ == "__main__":
    main()
