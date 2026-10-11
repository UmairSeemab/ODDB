#!/usr/bin/env python3
"""
Build an ODDB v1 refined DRUG-IDENTITY WORKING COPY.

IMPORTANT
---------
- This script DOES NOT modify the frozen release.
- It applies only the already-resolved identity refinements.
- Levothyroxine and X-82/Vorolanib remain unresolved/manual-review cases.
- Pegaptanib clinical links are retained, but source-ID conflicts are flagged.

Outputs
-------
1. Drug_v1_refined_2026-09-30.tsv
2. Drug_Form_Relationship_v1_refined_2026-09-30.tsv
3. Drug_Clinical_Report_Association_v1_refined_2026-09-30.tsv
4. Drug_ClinicalTrial_Association_v1_refined_2026-09-30.tsv
5. Drug_Identity_Refinement_Log_v1_2026-09-30.tsv
6. validation summary/problems

Safe changes applied
--------------------
- 51 missing ChEMBL identifiers added to existing Drug_v1 rows.
- RETINOL / CHEMBL986 added as a new drug entity.
- 6 clinical-report links remapped from TRETINOIN to RETINOL.
- corresponding NCT Drug_ClinicalTrial links remapped.
- 98 existing explicit Open Targets parent/form relationships preserved.
- TIMOLOL MALEATE -> TIMOLOL explicit salt/form relationship added if absent.
- 5 pegaptanib source-ID conflicts flagged, Drug_ID unchanged.
- 1 levothyroxine case flagged manual_review_pending.
- 1 X-82/Vorolanib case flagged manual_review_pending.
"""

import argparse
import hashlib
import re
from pathlib import Path

import pandas as pd


def clean(x):
    return str(x or "").strip()


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{h}"


def infer_id_prefix(series, fallback):
    for value in series.astype(str):
        m = re.match(r"^(.*)-([0-9A-Fa-f]{12})$", value.strip())
        if m:
            return m.group(1)
    return fallback


def append_note(old, new):
    old = clean(old)
    new = clean(new)
    if not old:
        return new
    if not new:
        return old
    if new in old:
        return old
    return old + " | " + new


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--drugs", required=True)
    ap.add_argument("--enrichment-proposal", required=True)
    ap.add_argument("--drug-addition-proposal", required=True)
    ap.add_argument("--explicit-parent-relationships", required=True)
    ap.add_argument("--form-proposal", required=True)
    ap.add_argument("--link-correction-proposal", required=True)

    ap.add_argument("--drug-report-links", required=True)
    ap.add_argument("--clinical-trials", required=True)
    ap.add_argument("--drug-trial-links", required=True)

    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--report-dir", required=True)

    args = ap.parse_args()

    outdir = Path(args.output_dir)
    report_dir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    enrich = pd.read_csv(
        args.enrichment_proposal, sep="\t", dtype=str
    ).fillna("")
    additions = pd.read_csv(
        args.drug_addition_proposal, sep="\t", dtype=str
    ).fillna("")
    parent_rel = pd.read_csv(
        args.explicit_parent_relationships, sep="\t", dtype=str
    ).fillna("")
    form_prop = pd.read_csv(
        args.form_proposal, sep="\t", dtype=str
    ).fillna("")
    corrections = pd.read_csv(
        args.link_correction_proposal, sep="\t", dtype=str
    ).fillna("")
    dcr = pd.read_csv(
        args.drug_report_links, sep="\t", dtype=str
    ).fillna("")
    trials = pd.read_csv(
        args.clinical_trials, sep="\t", dtype=str
    ).fillna("")
    dct = pd.read_csv(
        args.drug_trial_links, sep="\t", dtype=str
    ).fillna("")

    problems = []
    log_rows = []

    # ------------------------------------------------------------
    # A. Refine Drug_v1
    # ------------------------------------------------------------
    refined_drugs = drugs.copy()

    if "Drug_Identity_Refinement_Status" not in refined_drugs.columns:
        refined_drugs["Drug_Identity_Refinement_Status"] = ""
    if "Drug_Identity_Refinement_Notes" not in refined_drugs.columns:
        refined_drugs["Drug_Identity_Refinement_Notes"] = ""

    # 51 ChEMBL enrichments
    applied_enrichments = 0

    for _, p in enrich.iterrows():
        did = clean(p["Drug_ID"])
        proposed = clean(p["Proposed_ChEMBL_ID"]).upper()

        idx = refined_drugs.index[
            refined_drugs["Drug_ID"].eq(did)
        ]

        if len(idx) != 1:
            problems.append({
                "Table": "Drug_v1_refined",
                "Problem": "enrichment_drug_id_not_unique",
                "Detail": did,
            })
            continue

        i = idx[0]
        current = clean(refined_drugs.at[i, "ChEMBL_ID"]).upper()

        if current and current != proposed:
            problems.append({
                "Table": "Drug_v1_refined",
                "Problem": "attempted_overwrite_existing_chembl",
                "Detail": f"{did}: {current} -> {proposed}",
            })
            continue

        refined_drugs.at[i, "ChEMBL_ID"] = proposed
        refined_drugs.at[
            i, "Drug_Identity_Refinement_Status"
        ] = "chembl_identifier_enriched"
        refined_drugs.at[
            i, "Drug_Identity_Refinement_Notes"
        ] = append_note(
            refined_drugs.at[
                i, "Drug_Identity_Refinement_Notes"
            ],
            "Added from verified Open Targets clinical-report "
            "source ChEMBL identity.",
        )

        applied_enrichments += 1

        log_rows.append({
            "Action": "add_chembl_identifier",
            "Drug_ID": did,
            "Old_Value": current,
            "New_Value": proposed,
            "Clinical_Report_ID": "",
            "Reason": "resolved missing canonical ChEMBL identity",
        })

    # Add RETINOL
    retinol_id = ""

    if len(additions) != 1:
        problems.append({
            "Table": "Drug_v1_refined",
            "Problem": "expected_exactly_one_new_drug_proposal",
            "Detail": f"rows={len(additions)}",
        })
    else:
        p = additions.iloc[0]

        candidate_id = clean(p["Proposed_Drug_ID"])
        if candidate_id.startswith("ODDB-DRUG-CAND-"):
            retinol_id = candidate_id.replace(
                "ODDB-DRUG-CAND-", "ODDB-DRUG-", 1
            )
        else:
            retinol_id = stable_id(
                "ODDB-DRUG",
                clean(p.get("ChEMBL_ID")) or "CHEMBL986",
                clean(p.get("Preferred_Name")) or "RETINOL",
            )

        existing_by_id = refined_drugs[
            refined_drugs["Drug_ID"].eq(retinol_id)
        ]
        existing_by_chembl = refined_drugs[
            refined_drugs["ChEMBL_ID"].str.upper().eq(
                clean(p["ChEMBL_ID"]).upper()
            )
        ]

        if len(existing_by_id) or len(existing_by_chembl):
            problems.append({
                "Table": "Drug_v1_refined",
                "Problem": "retinol_candidate_already_present",
                "Detail": (
                    f"Drug_ID={retinol_id}; "
                    f"ChEMBL={clean(p['ChEMBL_ID'])}"
                ),
            })
        else:
            row = {c: "" for c in refined_drugs.columns}

            row["Drug_ID"] = retinol_id
            row["Preferred_Name"] = clean(p["Preferred_Name"])
            row["Normalized_Name"] = clean(p["Normalized_Name"])
            row["ChEMBL_ID"] = clean(p["ChEMBL_ID"])
            row["Standard_InChIKey"] = clean(
                p.get("Standard_InChIKey")
            )
            row["Drug_Entity_Type"] = clean(
                p.get("Drug_Entity_Type")
            )
            row["Identity_Basis"] = "chembl"
            row["Identifier_Curation_Status"] = (
                "opentargets_chembl_verified_refinement"
            )
            row["Source"] = clean(p.get("Source")) or (
                "Open Targets drug_molecule 26.09"
            )
            row["OpenTargets_Drug_IDs"] = clean(
                p.get("ChEMBL_ID")
            )
            row["OpenTargets_Name"] = clean(
                p.get("Preferred_Name")
            )
            row["OpenTargets_Drug_Type"] = clean(
                p.get("Drug_Entity_Type")
            )
            row["OpenTargets_Parent_ID"] = clean(
                p.get("OpenTargets_Parent_ID")
            )
            row["OpenTargets_Maximum_Clinical_Stage"] = clean(
                p.get("OpenTargets_Maximum_Clinical_Stage")
            )
            row["OpenTargets_Source_Release"] = "26.09"
            row["OpenTargets_Match_Method"] = (
                "new_entity_from_verified_source_chembl"
            )
            row["Drug_Identity_Refinement_Status"] = (
                "new_verified_drug_entity"
            )
            row["Drug_Identity_Refinement_Notes"] = (
                "Added to correct clinical reports previously "
                "misassigned from Vitamin A/retinol to TRETINOIN."
            )

            refined_drugs = pd.concat(
                [refined_drugs, pd.DataFrame([row])],
                ignore_index=True,
            )

            log_rows.append({
                "Action": "add_new_drug_entity",
                "Drug_ID": retinol_id,
                "Old_Value": "",
                "New_Value": "RETINOL / CHEMBL986",
                "Clinical_Report_ID": "",
                "Reason": (
                    "Vitamin A/retinol source reports are molecularly "
                    "distinct from TRETINOIN"
                ),
            })

    # ------------------------------------------------------------
    # B. Build Drug_Form_Relationship_v1
    # ------------------------------------------------------------
    form_rows = []

    for _, r in parent_rel.iterrows():
        child_id = clean(r["Child_Drug_ID"])
        parent_id = clean(r["Parent_Drug_ID"])

        form_rows.append({
            "Drug_Form_Relationship_ID": stable_id(
                "ODDB-DFR",
                child_id,
                parent_id,
                "form_of",
            ),
            "Child_Drug_ID": child_id,
            "Child_Drug_Name": clean(r["Child_Drug_Name"]),
            "Child_ChEMBL_ID": clean(r["Child_ChEMBL_ID"]),
            "Parent_Drug_ID": parent_id,
            "Parent_Drug_Name": clean(r["Parent_Drug_Name"]),
            "Parent_ChEMBL_ID": clean(r["Parent_ChEMBL_ID"]),
            "Relationship_Type": "form_of",
            "Source": clean(r.get("Source")) or "Open Targets",
            "Source_Release": clean(
                r.get("Source_Release")
            ) or "26.09",
            "Evidence_Basis": clean(r.get("Evidence_Basis")),
            "Curation_Status": (
                "source_explicit_parent_relationship"
            ),
        })

    for _, r in form_prop.iterrows():
        child_id = clean(r["Child_Drug_ID"])
        parent_id = clean(r["Parent_Drug_ID"])

        form_rows.append({
            "Drug_Form_Relationship_ID": stable_id(
                "ODDB-DFR",
                child_id,
                parent_id,
                clean(r.get("Relationship_Type")) or "salt_form_of",
            ),
            "Child_Drug_ID": child_id,
            "Child_Drug_Name": clean(r["Child_Drug_Name"]),
            "Child_ChEMBL_ID": clean(r["Child_ChEMBL_ID"]),
            "Parent_Drug_ID": parent_id,
            "Parent_Drug_Name": clean(r["Parent_Drug_Name"]),
            "Parent_ChEMBL_ID": clean(r["Parent_ChEMBL_ID"]),
            "Relationship_Type": clean(
                r.get("Relationship_Type")
            ) or "salt_form_of",
            "Source": clean(r.get("Source")) or "Open Targets",
            "Source_Release": clean(
                r.get("Source_Release")
            ) or "26.09",
            "Evidence_Basis": clean(r.get("Evidence_Basis")),
            "Curation_Status": (
                "source_explicit_parent_relationship"
            ),
        })

    forms = pd.DataFrame(form_rows)

    if len(forms):
        forms = forms.drop_duplicates(
            ["Child_Drug_ID", "Parent_Drug_ID"],
            keep="last",
        ).reset_index(drop=True)

    # ------------------------------------------------------------
    # C. Refine Drug_Clinical_Report_Association
    # ------------------------------------------------------------
    refined_dcr = dcr.copy()

    for col in [
        "Identity_Resolution_Status",
        "Identity_Resolution_Notes",
        "Original_Drug_ID",
        "Original_Drug_Name",
    ]:
        if col not in refined_dcr.columns:
            refined_dcr[col] = ""

    dcr_pk_col = "Drug_Clinical_Report_Association_ID"
    dcr_prefix = infer_id_prefix(
        refined_dcr[dcr_pk_col],
        "ODDB-DCRA",
    )

    remapped_report_ids = []
    pegaptanib_flagged = 0
    levothyroxine_pending = 0
    x82_pending = 0

    for _, p in corrections.iterrows():
        report_id = clean(p["Clinical_Report_ID"])
        current_drug_id = clean(p["Current_Drug_ID"])
        action = clean(p["Proposed_Action"])

        idx = refined_dcr.index[
            refined_dcr["Clinical_Report_ID"].eq(report_id)
            & refined_dcr["Drug_ID"].eq(current_drug_id)
        ]

        if len(idx) != 1:
            problems.append({
                "Table": "Drug_Clinical_Report_Association_refined",
                "Problem": "correction_target_not_unique",
                "Detail": (
                    f"{report_id} / {current_drug_id} -> rows={len(idx)}"
                ),
            })
            continue

        i = idx[0]

        if action == "remap_from_tretinoin_to_retinol_candidate":
            if not retinol_id:
                problems.append({
                    "Table": "Drug_Clinical_Report_Association_refined",
                    "Problem": "retinol_id_unavailable_for_remap",
                    "Detail": report_id,
                })
                continue

            old_name = clean(refined_dcr.at[i, "Drug_Name"])

            refined_dcr.at[i, "Original_Drug_ID"] = current_drug_id
            refined_dcr.at[i, "Original_Drug_Name"] = old_name
            refined_dcr.at[i, "Drug_ID"] = retinol_id
            refined_dcr.at[i, "Drug_Name"] = "RETINOL"

            if "Match_Method" in refined_dcr.columns:
                refined_dcr.at[i, "Match_Method"] = (
                    "manual_identity_refinement_source_chembl_verified"
                )

            refined_dcr.at[
                i, "Identity_Resolution_Status"
            ] = "resolved_remap_to_retinol"
            refined_dcr.at[
                i, "Identity_Resolution_Notes"
            ] = clean(p["Rationale"])

            refined_dcr.at[i, dcr_pk_col] = stable_id(
                dcr_prefix,
                retinol_id,
                report_id,
            )

            remapped_report_ids.append(report_id)

            log_rows.append({
                "Action": "remap_clinical_report_drug",
                "Drug_ID": retinol_id,
                "Old_Value": current_drug_id,
                "New_Value": retinol_id,
                "Clinical_Report_ID": report_id,
                "Reason": clean(p["Rationale"]),
            })

        elif action == "retain_pegaptanib_link_flag_source_id_conflict":
            refined_dcr.at[
                i, "Identity_Resolution_Status"
            ] = "retained_source_identifier_conflict"
            refined_dcr.at[
                i, "Identity_Resolution_Notes"
            ] = clean(p["Rationale"])
            pegaptanib_flagged += 1

        elif action == "retain_for_manual_stereochemistry_review":
            refined_dcr.at[
                i, "Identity_Resolution_Status"
            ] = "manual_review_pending_stereochemistry"
            refined_dcr.at[
                i, "Identity_Resolution_Notes"
            ] = clean(p["Rationale"])
            levothyroxine_pending += 1

        elif action == "retain_x82_link_probable_vorolanib_alias_candidate":
            refined_dcr.at[
                i, "Identity_Resolution_Status"
            ] = "manual_review_pending_alias_identity"
            refined_dcr.at[
                i, "Identity_Resolution_Notes"
            ] = clean(p["Rationale"])
            x82_pending += 1

    # ------------------------------------------------------------
    # D. Propagate resolved RETINOL remaps to Drug_ClinicalTrial
    # ------------------------------------------------------------
    refined_dct = dct.copy()

    for col in [
        "Identity_Resolution_Status",
        "Identity_Resolution_Notes",
        "Original_Drug_ID",
        "Original_Drug_Name",
    ]:
        if col not in refined_dct.columns:
            refined_dct[col] = ""

    dct_pk_col = "Drug_ClinicalTrial_Association_ID"
    dct_prefix = infer_id_prefix(
        refined_dct[dct_pk_col],
        "ODDB-DCTA",
    )

    report_to_trials = (
        trials.groupby("Clinical_Report_ID")["ClinicalTrial_ID"]
        .apply(list)
        .to_dict()
    )

    retinol_trial_remaps = 0

    for report_id in remapped_report_ids:
        trial_ids = report_to_trials.get(report_id, [])

        for trial_id in trial_ids:
            idx = refined_dct.index[
                refined_dct["ClinicalTrial_ID"].eq(trial_id)
                & refined_dct["Drug_ID"].eq("ODDB-DRUG-6B3235E14695")
            ]

            for i in idx:
                old_name = clean(refined_dct.at[i, "Drug_Name"])

                refined_dct.at[
                    i, "Original_Drug_ID"
                ] = "ODDB-DRUG-6B3235E14695"
                refined_dct.at[
                    i, "Original_Drug_Name"
                ] = old_name
                refined_dct.at[i, "Drug_ID"] = retinol_id
                refined_dct.at[i, "Drug_Name"] = "RETINOL"
                refined_dct.at[
                    i, "Identity_Resolution_Status"
                ] = "resolved_remap_to_retinol"
                refined_dct.at[
                    i, "Identity_Resolution_Notes"
                ] = (
                    "Propagated from corrected parent clinical-report "
                    "drug identity."
                )

                refined_dct.at[i, dct_pk_col] = stable_id(
                    dct_prefix,
                    retinol_id,
                    trial_id,
                )

                retinol_trial_remaps += 1

    # ------------------------------------------------------------
    # E. Validation
    # ------------------------------------------------------------
    valid_drug_ids = set(refined_drugs["Drug_ID"])

    if refined_drugs["Drug_ID"].duplicated().any():
        problems.append({
            "Table": "Drug_v1_refined",
            "Problem": "duplicate_Drug_ID",
            "Detail": str(
                refined_drugs["Drug_ID"].duplicated().sum()
            ),
        })

    nonblank_chembl = refined_drugs[
        refined_drugs["ChEMBL_ID"].str.strip().ne("")
    ]

    chembl_dup = nonblank_chembl["ChEMBL_ID"].duplicated().sum()
    if chembl_dup:
        problems.append({
            "Table": "Drug_v1_refined",
            "Problem": "duplicate_nonblank_ChEMBL_ID",
            "Detail": str(chembl_dup),
        })

    bad_dcr_fk = (~refined_dcr["Drug_ID"].isin(valid_drug_ids)).sum()
    if bad_dcr_fk:
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "invalid_Drug_ID_FK",
            "Detail": str(bad_dcr_fk),
        })

    bad_dct_fk = (~refined_dct["Drug_ID"].isin(valid_drug_ids)).sum()
    if bad_dct_fk:
        problems.append({
            "Table": "Drug_ClinicalTrial_Association_refined",
            "Problem": "invalid_Drug_ID_FK",
            "Detail": str(bad_dct_fk),
        })

    if refined_dcr[dcr_pk_col].duplicated().any():
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "duplicate_primary_key",
            "Detail": str(
                refined_dcr[dcr_pk_col].duplicated().sum()
            ),
        })

    if refined_dct[dct_pk_col].duplicated().any():
        problems.append({
            "Table": "Drug_ClinicalTrial_Association_refined",
            "Problem": "duplicate_primary_key",
            "Detail": str(
                refined_dct[dct_pk_col].duplicated().sum()
            ),
        })

    if len(remapped_report_ids) != 6:
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "unexpected_retinol_report_remap_count",
            "Detail": str(len(remapped_report_ids)),
        })

    if pegaptanib_flagged != 5:
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "unexpected_pegaptanib_flag_count",
            "Detail": str(pegaptanib_flagged),
        })

    if levothyroxine_pending != 1:
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "unexpected_levothyroxine_pending_count",
            "Detail": str(levothyroxine_pending),
        })

    if x82_pending != 1:
        problems.append({
            "Table": "Drug_Clinical_Report_Association_refined",
            "Problem": "unexpected_x82_pending_count",
            "Detail": str(x82_pending),
        })

    # ------------------------------------------------------------
    # F. Write
    # ------------------------------------------------------------
    drug_out = outdir / "Drug_v1_refined_2026-09-30.tsv"
    form_out = outdir / "Drug_Form_Relationship_v1_refined_2026-09-30.tsv"
    dcr_out = (
        outdir /
        "Drug_Clinical_Report_Association_v1_refined_2026-09-30.tsv"
    )
    dct_out = (
        outdir /
        "Drug_ClinicalTrial_Association_v1_refined_2026-09-30.tsv"
    )
    log_out = (
        outdir /
        "Drug_Identity_Refinement_Log_v1_2026-09-30.tsv"
    )

    refined_drugs.to_csv(drug_out, sep="\t", index=False)
    forms.to_csv(form_out, sep="\t", index=False)
    refined_dcr.to_csv(dcr_out, sep="\t", index=False)
    refined_dct.to_csv(dct_out, sep="\t", index=False)

    pd.DataFrame(log_rows).to_csv(
        log_out, sep="\t", index=False
    )

    summary = pd.DataFrame([
        ["Input_drug_rows", len(drugs)],
        ["Applied_ChEMBL_enrichments", applied_enrichments],
        ["New_RETINOL_drug_entities", 1 if retinol_id else 0],
        ["Refined_drug_rows", len(refined_drugs)],
        ["Drug_form_relationship_rows", len(forms)],
        ["Clinical_report_drug_links", len(refined_dcr)],
        ["Clinical_report_links_remapped_to_RETINOL",
         len(remapped_report_ids)],
        ["Pegaptanib_links_flagged_source_ID_conflict",
         pegaptanib_flagged],
        ["Levothyroxine_links_manual_review_pending",
         levothyroxine_pending],
        ["X82_links_manual_review_pending",
         x82_pending],
        ["Clinical_trial_drug_links", len(refined_dct)],
        ["Clinical_trial_links_remapped_to_RETINOL",
         retinol_trial_remaps],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    summary.to_csv(
        report_dir / "refined_drug_identity_build_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame(
        problems,
        columns=["Table", "Problem", "Detail"],
    ).to_csv(
        report_dir / "refined_drug_identity_build_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB v1 REFINED DRUG-IDENTITY WORKING COPY")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        print(pd.DataFrame(problems).to_string(index=False))
        raise SystemExit(1)

    print("\nVALIDATION PASSED.")
    print("\nOutputs:")
    print(drug_out)
    print(form_out)
    print(dcr_out)
    print(dct_out)
    print(log_out)
    print("\nFrozen releases were not modified.")


if __name__ == "__main__":
    main()
