#!/usr/bin/env python3
"""
Build an AUDIT-ONLY ODDB v1 drug identity refinement proposal.

This script does NOT modify:
- Drug_v1
- clinical-report associations
- frozen releases

It converts the completed drug-identity audits into explicit proposal tables
for a future dated ODDB v1 release.

Rules encoded
-------------
1. Missing canonical ChEMBL + exact Open Targets identity match:
   -> propose ChEMBL enrichment only.

2. Timolol maleate:
   -> propose CHEMBL1200870 enrichment and explicit form/parent relation
      to TIMOLOL / CHEMBL499.

3. TRETINOIN + source CHEMBL986 (RETINOL/Vitamin A):
   -> propose REMAP away from TRETINOIN.
   -> propose new RETINOL drug entity candidate if not already in Drug_v1.

4. PEGAPTANIB SODIUM + source CHEMBL3301576 (PEGPLERANIB SODIUM):
   -> retain canonical pegaptanib clinical link.
   -> flag source identifier inconsistency.
   -> never add CHEMBL3301576 as pegaptanib alternate identifier.

5. LEVOTHYROXINE + source CHEMBL42115 (THYROXINE):
   -> retain for manual review only.
   -> classify as stereochemistry-unspecified related entity.
   -> do not automatically add CHEMBL42115 as canonical/alternate identifier.

6. X-82 + source CHEMBL4297587 (VOROLANIB):
   -> probable same-drug alias/external-identity candidate.
   -> retain current link, but require curator approval before adding alternate ID.

All generated files are proposals only.
"""

import argparse
import hashlib
import re
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds


def clean(x):
    return str(x or "").strip()


def norm(x):
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--resolution", required=True)
    ap.add_argument("--mismatch-detail", required=True)
    ap.add_argument("--drug-report-links", required=True)
    ap.add_argument("--clinical-reports", required=True)
    ap.add_argument("--drug-molecule-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    res = pd.read_csv(args.resolution, sep="\t", dtype=str).fillna("")
    mm = pd.read_csv(args.mismatch_detail, sep="\t", dtype=str).fillna("")
    links = pd.read_csv(
        args.drug_report_links, sep="\t", dtype=str
    ).fillna("")
    reports = pd.read_csv(
        args.clinical_reports, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    drug_by_id = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in drugs.iterrows()
    }

    # ------------------------------------------------------------
    # 1. Straightforward ChEMBL enrichment candidates
    # ------------------------------------------------------------
    enrich = res[
        res["Identity_Resolution_Class"].eq(
            "missing_canonical_chembl_exact_identity_candidate"
        )
    ].copy()

    enrich_rows = []

    for _, r in enrich.iterrows():
        enrich_rows.append({
            "Proposal_ID": stable_id(
                "ODDB-DIP",
                "chembl_enrichment",
                r["Drug_ID"],
                r["Source_Drug_ID"],
            ),
            "Drug_ID": clean(r["Drug_ID"]),
            "Drug_Name": clean(r["Drug_Name"]),
            "Current_ChEMBL_ID": clean(r["Canonical_ChEMBL_ID"]),
            "Proposed_ChEMBL_ID": clean(r["Source_Drug_ID"]),
            "Proposed_Action": "add_canonical_chembl_identifier",
            "Evidence_Source": "Open Targets drug_molecule 26.09",
            "Evidence_Basis":
                "source_ChEMBL_resolves_to_exact_identity_candidate",
            "Curation_Status": "proposal_requires_curator_approval",
        })

    enrichment = pd.DataFrame(enrich_rows)

    # ------------------------------------------------------------
    # 2. Timolol maleate special parent/form case
    # ------------------------------------------------------------
    timolol_form_rows = []

    timolol_maleate = res[
        (res["Drug_Name"].str.upper() == "TIMOLOL MALEATE")
        & (res["Source_Drug_ID"].str.upper() == "CHEMBL1200870")
    ]

    # Find timolol Drug_ID by preferred name.
    timolol_candidates = drugs[
        drugs["Preferred_Name"].str.upper().eq("TIMOLOL")
    ]

    if len(timolol_maleate) and len(timolol_candidates) == 1:
        tm = timolol_maleate.iloc[0]
        parent = timolol_candidates.iloc[0]

        timolol_form_rows.append({
            "Drug_Form_Relationship_ID": stable_id(
                "ODDB-DFR",
                tm["Drug_ID"],
                parent["Drug_ID"],
                "salt_form_of",
            ),
            "Child_Drug_ID": clean(tm["Drug_ID"]),
            "Child_Drug_Name": clean(tm["Drug_Name"]),
            "Child_ChEMBL_ID": "CHEMBL1200870",
            "Parent_Drug_ID": clean(parent["Drug_ID"]),
            "Parent_Drug_Name": clean(parent["Preferred_Name"]),
            "Parent_ChEMBL_ID": "CHEMBL499",
            "Relationship_Type": "salt_form_of",
            "Source": "Open Targets drug_molecule",
            "Source_Release": "26.09",
            "Evidence_Basis":
                "CHEMBL1200870 parentId == CHEMBL499",
            "Curation_Status": "proposal_requires_curator_approval",
        })

    timolol_form = pd.DataFrame(timolol_form_rows)

    # ------------------------------------------------------------
    # 3. Fetch RETINOL record for new-drug proposal
    # ------------------------------------------------------------
    dm = ds.dataset(
        args.drug_molecule_dir,
        format="parquet",
        partitioning="hive",
    )

    cols = [
        c for c in [
            "id",
            "name",
            "parentId",
            "inchiKey",
            "drugType",
            "maximumClinicalStage",
        ]
        if c in dm.schema.names
    ]

    retinol_table = dm.to_table(
        columns=cols,
        filter=ds.field("id") == "CHEMBL986",
    )
    retinol_df = retinol_table.to_pandas().fillna("")

    existing_retinol = drugs[
        drugs["Preferred_Name"].str.upper().isin(
            ["RETINOL", "VITAMIN A"]
        )
        | drugs["ChEMBL_ID"].str.upper().eq("CHEMBL986")
    ]

    new_drug_rows = []

    if len(existing_retinol) == 0 and len(retinol_df) == 1:
        rr = retinol_df.iloc[0]
        proposed_drug_id = stable_id(
            "ODDB-DRUG-CAND",
            "CHEMBL986",
            "RETINOL",
        )

        new_drug_rows.append({
            "Proposed_Drug_ID": proposed_drug_id,
            "Preferred_Name": clean(rr.get("name")) or "RETINOL",
            "Normalized_Name": "retinol",
            "ChEMBL_ID": "CHEMBL986",
            "Standard_InChIKey": clean(rr.get("inchiKey")),
            "Drug_Entity_Type": clean(rr.get("drugType")),
            "OpenTargets_Parent_ID": clean(rr.get("parentId")),
            "OpenTargets_Maximum_Clinical_Stage":
                clean(rr.get("maximumClinicalStage")),
            "Source": "Open Targets drug_molecule",
            "Source_Release": "26.09",
            "Reason":
                "required_to_correct_Vitamin_A_retinol_clinical_report_links",
            "Curation_Status": "new_drug_candidate_requires_curator_approval",
        })

    new_drugs = pd.DataFrame(new_drug_rows)

    # ------------------------------------------------------------
    # 4. Clinical-report conflict actions
    # ------------------------------------------------------------
    conflict_keys = {
        ("ODDB-DRUG-6B3235E14695", "CHEMBL986"):
            (
                "remap_from_tretinoin_to_retinol_candidate",
                "source molecule is RETINOL/Vitamin A; "
                "different InChIKey/connectivity from TRETINOIN"
            ),
        ("ODDB-DRUG-346B4298790E", "CHEMBL3301576"):
            (
                "retain_pegaptanib_link_flag_source_id_conflict",
                "report names/titles identify Macugen/pegaptanib, "
                "while source ChEMBL resolves to PEGPLERANIB SODIUM"
            ),
        ("ODDB-DRUG-EEC5D7196D9C", "CHEMBL42115"):
            (
                "retain_for_manual_stereochemistry_review",
                "source THYROXINE has same connectivity block as "
                "LEVOTHYROXINE but unspecified stereochemistry"
            ),
        ("ODDB-DRUG-439D1BBFB8BC", "CHEMBL4297587"):
            (
                "retain_x82_link_probable_vorolanib_alias_candidate",
                "X-82 and VOROLANIB are reciprocal source synonyms; "
                "alternate ChEMBL identity requires curator approval"
            ),
    }

    # Start from mismatch detail because it has one row per report link.
    conflict = mm[
        mm.apply(
            lambda r: (
                clean(r["Drug_ID"]),
                clean(r["Source_Drug_ID"]).upper()
            ) in conflict_keys,
            axis=1,
        )
    ].copy()

    # Attach report metadata.
    report_cols = [
        c for c in [
            "Clinical_Report_ID",
            "OpenTargets_Clinical_Report_ID",
            "NCT_IDs",
            "Title",
            "Trial_Official_Title",
            "Source",
            "Origin",
            "Clinical_Stage",
            "Trial_Phase",
            "Trial_Overall_Status",
        ]
        if c in reports.columns
    ]

    conflict = conflict.merge(
        reports[report_cols].drop_duplicates("Clinical_Report_ID"),
        on="Clinical_Report_ID",
        how="left",
        suffixes=("", "_report"),
    )

    proposal_rows = []

    retinol_candidate_id = (
        clean(new_drugs.iloc[0]["Proposed_Drug_ID"])
        if len(new_drugs)
        else (
            clean(existing_retinol.iloc[0]["Drug_ID"])
            if len(existing_retinol)
            else ""
        )
    )

    for _, r in conflict.iterrows():
        key = (
            clean(r["Drug_ID"]),
            clean(r["Source_Drug_ID"]).upper(),
        )
        action, rationale = conflict_keys[key]

        proposed_drug_id = clean(r["Drug_ID"])
        proposed_drug_name = clean(r["Drug_Name"])

        if key == ("ODDB-DRUG-6B3235E14695", "CHEMBL986"):
            proposed_drug_id = retinol_candidate_id
            proposed_drug_name = "RETINOL"

        proposal_rows.append({
            "Proposal_ID": stable_id(
                "ODDB-DCRP",
                r["Clinical_Report_ID"],
                key[0],
                key[1],
            ),
            "Clinical_Report_ID": clean(r["Clinical_Report_ID"]),
            "OpenTargets_Clinical_Report_ID":
                clean(r.get("OpenTargets_Clinical_Report_ID")),
            "NCT_IDs": clean(r.get("NCT_IDs")),
            "Current_Drug_ID": key[0],
            "Current_Drug_Name": clean(r["Drug_Name"]),
            "Canonical_ChEMBL_ID":
                clean(r["Canonical_ChEMBL_ID"]),
            "Source_Drug_ID": key[1],
            "Source_Drug_Name":
                clean(r.get("Source_Drug_Name")),
            "Proposed_Drug_ID": proposed_drug_id,
            "Proposed_Drug_Name": proposed_drug_name,
            "Proposed_Action": action,
            "Rationale": rationale,
            "Report_Title": clean(r.get("Title")),
            "Trial_Official_Title":
                clean(r.get("Trial_Official_Title")),
            "Evidence_Source": clean(r.get("Source")),
            "Curation_Status": "proposal_requires_curator_approval",
        })

    link_proposals = pd.DataFrame(proposal_rows)

    # ------------------------------------------------------------
    # 5. Mapper policy proposal
    # ------------------------------------------------------------
    mapper_policy = pd.DataFrame([
        [
            "P1",
            "source_identifier_first",
            "If Source_Drug_ID is present, resolve that identifier before "
            "performing name matching."
        ],
        [
            "P2",
            "do_not_override_identifier_conflict_with_name",
            "If the source identifier resolves to a different molecular "
            "entity than the name-based candidate, do not auto-map. "
            "Create an identity-conflict review record."
        ],
        [
            "P3",
            "name_match_only_when_source_identifier_missing_or_unresolvable",
            "Use exact unique name matching only when no usable source "
            "identifier exists, or after explicit curator approval."
        ],
        [
            "P4",
            "preserve_parent_form_entities",
            "Do not collapse salts/forms into the parent Drug_ID. Store an "
            "explicit Drug_Form_Relationship."
        ],
        [
            "P5",
            "preserve_raw_source_identifiers",
            "Every clinical-report drug link should retain the raw source "
            "drug ID and source drug name even after canonical mapping."
        ],
        [
            "P6",
            "source_conflict_flag",
            "When a report title/intervention clearly supports the canonical "
            "drug but the source ChEMBL resolves to another drug, retain the "
            "canonical mapping only with an explicit source-ID conflict flag."
        ],
    ], columns=["Rule_ID", "Rule_Name", "Rule"])

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    summary = pd.DataFrame([
        ["Straightforward_ChEMBL_enrichment_candidates", len(enrichment)],
        ["Proposed_new_drug_entities", len(new_drugs)],
        ["Proposed_timolol_parent_form_relationships", len(timolol_form)],
        ["Conflict_clinical_report_link_proposals", len(link_proposals)],
        [
            "Tretinoin_to_retinol_remap_proposals",
            int(
                link_proposals["Proposed_Action"]
                .eq("remap_from_tretinoin_to_retinol_candidate")
                .sum()
            ) if len(link_proposals) else 0
        ],
        [
            "Pegaptanib_source_ID_conflict_flags",
            int(
                link_proposals["Proposed_Action"]
                .eq("retain_pegaptanib_link_flag_source_id_conflict")
                .sum()
            ) if len(link_proposals) else 0
        ],
        [
            "Levothyroxine_manual_review_links",
            int(
                link_proposals["Proposed_Action"]
                .eq("retain_for_manual_stereochemistry_review")
                .sum()
            ) if len(link_proposals) else 0
        ],
        [
            "X82_vorolanib_alias_candidate_links",
            int(
                link_proposals["Proposed_Action"]
                .eq("retain_x82_link_probable_vorolanib_alias_candidate")
                .sum()
            ) if len(link_proposals) else 0
        ],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------
    # Write
    # ------------------------------------------------------------
    enrichment.to_csv(
        outdir / "Drug_ChEMBL_Enrichment_Proposal_v1_2026-09-30.tsv",
        sep="\t", index=False
    )

    new_drugs.to_csv(
        outdir / "Drug_Addition_Proposal_v1_2026-09-30.tsv",
        sep="\t", index=False
    )

    timolol_form.to_csv(
        outdir / "Drug_Form_Relationship_Proposal_v1_2026-09-30.tsv",
        sep="\t", index=False
    )

    link_proposals.to_csv(
        outdir /
        "Clinical_Report_Drug_Link_Correction_Proposal_v1_2026-09-30.tsv",
        sep="\t", index=False
    )

    mapper_policy.to_csv(
        outdir / "Drug_Identity_Mapping_Policy_v1_2026-09-30.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "drug_identity_refinement_proposal_summary.tsv",
        sep="\t", index=False
    )

    print("ODDB v1 DRUG IDENTITY REFINEMENT PROPOSAL")
    print(summary.to_string(index=False))

    print("\nNo canonical or frozen files were modified.")
    print("Proposal directory:", outdir)


if __name__ == "__main__":
    main()
