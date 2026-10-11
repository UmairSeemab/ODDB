#!/usr/bin/env python3
"""
Validate and freeze the refined ODDB v1 drug/clinical layer.

This validator is specifically for the refined 2026-09-30 working copy.

It validates:
- Drug_v1_refined (805 rows expected)
- Drug_Form_Relationship_v1_refined
- refined Drug_Clinical_Report_Association
- refined Drug_ClinicalTrial_Association
- refined Disease_Drug_Association / Evidence
- unchanged Drug_Target_Association
- refined aggregate context
- refined disease-drug target overlap
- expected RETINOL/TRETINOIN corrections
- expected pegaptanib/levothyroxine/X-82 review flags
- PK/FK consistency
- report -> trial propagation consistency
- DDA/DDE and overlap semantics
- SHA256 manifest

No source files are modified.
Freeze occurs only if validation passes.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd


def read_tsv(path):
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def add_problem(problems, table, problem, count=1, detail=""):
    count = int(count)
    if count > 0:
        problems.append({
            "Table": table,
            "Problem": problem,
            "Count": count,
            "Detail": str(detail),
        })


def require_cols(df, table, cols, problems):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        add_problem(
            problems,
            table,
            "missing_required_columns",
            len(missing),
            " | ".join(missing),
        )


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--base-processed-dir",
        default="data/processed",
    )
    ap.add_argument(
        "--refined-dir",
        default="data/processed/refined_2026-09-30",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/oddb_v1_drug_clinical_refined_freeze_2026-09-30",
    )
    ap.add_argument(
        "--release-dir",
        default="releases/ODDB_v1_drug_clinical_refined_2026-09-30",
    )

    args = ap.parse_args()

    base = Path(args.base_processed_dir)
    refined = Path(args.refined_dir)
    report_dir = Path(args.report_dir)
    release_dir = Path(args.release_dir)

    files = {
        "Disease":
            base / "Disease_v1_final_2026-09-29.tsv",

        "Gene":
            base / "Gene_v1_2026-09-29.tsv",

        "DGA":
            base / "Disease_Gene_Association_v1_final_2026-09-29.tsv",

        "Drug":
            refined / "Drug_v1_refined_2026-09-30.tsv",

        "Drug_Form_Relationship":
            refined / "Drug_Form_Relationship_v1_refined_2026-09-30.tsv",

        "DTA":
            base / "Drug_Target_Association_v1_2026-09-29.tsv",

        "DDA":
            refined / "Disease_Drug_Association_v1_refined_2026-09-30.tsv",

        "DDE":
            refined / "Disease_Drug_Evidence_v1_refined_2026-09-30.tsv",

        "Clinical_Report":
            base / "Clinical_Report_v1_2026-09-30.tsv",

        "Disease_Clinical_Report":
            base / "Disease_Clinical_Report_Association_v1_2026-09-30.tsv",

        "Drug_Clinical_Report":
            refined / "Drug_Clinical_Report_Association_v1_refined_2026-09-30.tsv",

        "ClinicalTrial":
            base / "ClinicalTrial_v1_2026-09-30.tsv",

        "Disease_ClinicalTrial":
            base / "Disease_ClinicalTrial_Association_v1_2026-09-30.tsv",

        "Drug_ClinicalTrial":
            refined / "Drug_ClinicalTrial_Association_v1_refined_2026-09-30.tsv",

        "Aggregate_Context":
            refined / "Disease_Drug_Aggregate_Clinical_Context_v1_refined_2026-09-30.tsv",

        "Demoted_Aggregate_Context":
            refined / "Disease_Drug_Aggregate_Context_Demoted_v1_refined_2026-09-30.tsv",

        "Target_Overlap":
            refined / "Disease_Drug_Target_Overlap_v1_refined_2026-09-30.tsv",

        "Target_Overlap_Summary":
            refined / "Disease_Drug_Target_Overlap_Summary_v1_refined_2026-09-30.tsv",

        "Direct_Without_Target_Overlap":
            refined / "Disease_Drug_Direct_Evidence_Without_Target_Overlap_v1_refined_2026-09-30.tsv",

        "Refinement_Log":
            refined / "Drug_Identity_Refinement_Log_v1_2026-09-30.tsv",
    }

    missing = [
        f"{name}: {path}"
        for name, path in files.items()
        if not path.exists()
    ]

    if missing:
        raise SystemExit(
            "Required files missing:\n" + "\n".join(missing)
        )

    data = {
        name: read_tsv(path)
        for name, path in files.items()
    }

    disease = data["Disease"]
    gene = data["Gene"]
    dga = data["DGA"]
    drug = data["Drug"]
    forms = data["Drug_Form_Relationship"]
    dta = data["DTA"]
    dda = data["DDA"]
    dde = data["DDE"]
    cr = data["Clinical_Report"]
    dcr = data["Disease_Clinical_Report"]
    drugcr = data["Drug_Clinical_Report"]
    ct = data["ClinicalTrial"]
    dct = data["Disease_ClinicalTrial"]
    drugct = data["Drug_ClinicalTrial"]
    agg = data["Aggregate_Context"]
    demoted = data["Demoted_Aggregate_Context"]
    overlap = data["Target_Overlap"]
    overlap_summary = data["Target_Overlap_Summary"]
    no_overlap = data["Direct_Without_Target_Overlap"]
    ref_log = data["Refinement_Log"]

    problems = []

    # ------------------------------------------------------------
    # Required columns
    # ------------------------------------------------------------
    required = {
        "Disease": ["DiseaseID"],
        "Gene": ["HGNC_ID"],
        "DGA": ["Association_ID", "DiseaseID", "HGNC_ID"],
        "Drug": ["Drug_ID", "Preferred_Name", "ChEMBL_ID"],
        "Drug_Form_Relationship": [
            "Drug_Form_Relationship_ID",
            "Child_Drug_ID",
            "Parent_Drug_ID",
        ],
        "DTA": [
            "Drug_Target_Association_ID",
            "Drug_ID",
            "HGNC_ID",
        ],
        "DDA": [
            "Disease_Drug_Association_ID",
            "DiseaseID",
            "Drug_ID",
        ],
        "DDE": [
            "Disease_Drug_Evidence_ID",
            "Disease_Drug_Association_ID",
            "DiseaseID",
            "Drug_ID",
        ],
        "Clinical_Report": [
            "Clinical_Report_ID",
            "OpenTargets_Clinical_Report_ID",
        ],
        "Disease_Clinical_Report": [
            "Disease_Clinical_Report_Association_ID",
            "DiseaseID",
            "Clinical_Report_ID",
        ],
        "Drug_Clinical_Report": [
            "Drug_Clinical_Report_Association_ID",
            "Drug_ID",
            "Drug_Name",
            "Clinical_Report_ID",
            "Identity_Resolution_Status",
        ],
        "ClinicalTrial": [
            "ClinicalTrial_ID",
            "NCT_ID",
            "Clinical_Report_ID",
        ],
        "Disease_ClinicalTrial": [
            "Disease_ClinicalTrial_Association_ID",
            "DiseaseID",
            "ClinicalTrial_ID",
        ],
        "Drug_ClinicalTrial": [
            "Drug_ClinicalTrial_Association_ID",
            "Drug_ID",
            "Drug_Name",
            "ClinicalTrial_ID",
            "Identity_Resolution_Status",
        ],
        "Aggregate_Context": [
            "DiseaseID",
            "Drug_ID",
            "Aggregate_Context_Class",
        ],
        "Demoted_Aggregate_Context": [
            "DiseaseID",
            "Drug_ID",
            "Aggregate_Context_Class",
        ],
        "Target_Overlap": [
            "Disease_Drug_Target_Overlap_ID",
            "DiseaseID",
            "Drug_ID",
            "HGNC_ID",
            "Direct_Disease_Drug_Evidence",
        ],
        "Target_Overlap_Summary": [
            "Disease_Drug_Target_Summary_ID",
            "DiseaseID",
            "Drug_ID",
            "Direct_Disease_Drug_Evidence",
        ],
        "Direct_Without_Target_Overlap": [
            "DiseaseID",
            "Drug_ID",
        ],
    }

    for name, cols in required.items():
        require_cols(data[name], name, cols, problems)

    if problems:
        report_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(problems).to_csv(
            report_dir / "validation_problems.tsv",
            sep="\t",
            index=False,
        )
        raise SystemExit(
            "Validation stopped due to missing required columns."
        )

    # ------------------------------------------------------------
    # Primary keys
    # ------------------------------------------------------------
    pk_map = {
        "Disease": ("DiseaseID", disease),
        "Gene": ("HGNC_ID", gene),
        "DGA": ("Association_ID", dga),
        "Drug": ("Drug_ID", drug),
        "Drug_Form_Relationship":
            ("Drug_Form_Relationship_ID", forms),
        "DTA": ("Drug_Target_Association_ID", dta),
        "DDA": ("Disease_Drug_Association_ID", dda),
        "DDE": ("Disease_Drug_Evidence_ID", dde),
        "Clinical_Report": ("Clinical_Report_ID", cr),
        "Disease_Clinical_Report":
            ("Disease_Clinical_Report_Association_ID", dcr),
        "Drug_Clinical_Report":
            ("Drug_Clinical_Report_Association_ID", drugcr),
        "ClinicalTrial": ("ClinicalTrial_ID", ct),
        "Disease_ClinicalTrial":
            ("Disease_ClinicalTrial_Association_ID", dct),
        "Drug_ClinicalTrial":
            ("Drug_ClinicalTrial_Association_ID", drugct),
        "Target_Overlap":
            ("Disease_Drug_Target_Overlap_ID", overlap),
        "Target_Overlap_Summary":
            ("Disease_Drug_Target_Summary_ID", overlap_summary),
    }

    for name, (pk, df) in pk_map.items():
        add_problem(
            problems,
            name,
            "duplicate_primary_key",
            df[pk].duplicated().sum(),
            pk,
        )
        add_problem(
            problems,
            name,
            "blank_primary_key",
            df[pk].str.strip().eq("").sum(),
            pk,
        )

    # Natural keys
    add_problem(
        problems,
        "DDA",
        "duplicate_DiseaseID_Drug_ID",
        dda.duplicated(["DiseaseID", "Drug_ID"]).sum(),
    )

    add_problem(
        problems,
        "Drug_Form_Relationship",
        "duplicate_child_parent_pair",
        forms.duplicated(
            ["Child_Drug_ID", "Parent_Drug_ID"]
        ).sum(),
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "duplicate_DiseaseID_Drug_ID",
        overlap_summary.duplicated(
            ["DiseaseID", "Drug_ID"]
        ).sum(),
    )

    # ------------------------------------------------------------
    # Foreign keys
    # ------------------------------------------------------------
    disease_ids = set(disease["DiseaseID"])
    gene_ids = set(gene["HGNC_ID"])
    drug_ids = set(drug["Drug_ID"])
    dda_ids = set(dda["Disease_Drug_Association_ID"])
    cr_ids = set(cr["Clinical_Report_ID"])
    trial_ids = set(ct["ClinicalTrial_ID"])

    fk_checks = [
        ("DGA", dga, "DiseaseID", disease_ids),
        ("DGA", dga, "HGNC_ID", gene_ids),

        ("DTA", dta, "Drug_ID", drug_ids),
        ("DTA", dta, "HGNC_ID", gene_ids),

        ("DDA", dda, "DiseaseID", disease_ids),
        ("DDA", dda, "Drug_ID", drug_ids),

        ("DDE", dde, "DiseaseID", disease_ids),
        ("DDE", dde, "Drug_ID", drug_ids),
        ("DDE", dde, "Disease_Drug_Association_ID", dda_ids),

        ("Drug_Form_Relationship", forms, "Child_Drug_ID", drug_ids),
        ("Drug_Form_Relationship", forms, "Parent_Drug_ID", drug_ids),

        ("Disease_Clinical_Report", dcr, "DiseaseID", disease_ids),
        ("Disease_Clinical_Report", dcr, "Clinical_Report_ID", cr_ids),

        ("Drug_Clinical_Report", drugcr, "Drug_ID", drug_ids),
        ("Drug_Clinical_Report", drugcr, "Clinical_Report_ID", cr_ids),

        ("ClinicalTrial", ct, "Clinical_Report_ID", cr_ids),

        ("Disease_ClinicalTrial", dct, "DiseaseID", disease_ids),
        ("Disease_ClinicalTrial", dct, "ClinicalTrial_ID", trial_ids),

        ("Drug_ClinicalTrial", drugct, "Drug_ID", drug_ids),
        ("Drug_ClinicalTrial", drugct, "ClinicalTrial_ID", trial_ids),

        ("Aggregate_Context", agg, "DiseaseID", disease_ids),
        ("Aggregate_Context", agg, "Drug_ID", drug_ids),

        ("Demoted_Aggregate_Context", demoted, "DiseaseID", disease_ids),
        ("Demoted_Aggregate_Context", demoted, "Drug_ID", drug_ids),

        ("Target_Overlap", overlap, "DiseaseID", disease_ids),
        ("Target_Overlap", overlap, "Drug_ID", drug_ids),
        ("Target_Overlap", overlap, "HGNC_ID", gene_ids),

        ("Target_Overlap_Summary", overlap_summary, "DiseaseID", disease_ids),
        ("Target_Overlap_Summary", overlap_summary, "Drug_ID", drug_ids),

        ("Direct_Without_Target_Overlap", no_overlap, "DiseaseID", disease_ids),
        ("Direct_Without_Target_Overlap", no_overlap, "Drug_ID", drug_ids),
    ]

    for table, df, col, valid in fk_checks:
        add_problem(
            problems,
            table,
            f"invalid_foreign_key_{col}",
            (~df[col].isin(valid)).sum(),
        )

    # ------------------------------------------------------------
    # No self form relationships
    # ------------------------------------------------------------
    add_problem(
        problems,
        "Drug_Form_Relationship",
        "self_parent_relationship",
        (forms["Child_Drug_ID"] == forms["Parent_Drug_ID"]).sum(),
    )

    # ------------------------------------------------------------
    # DDA/DDE consistency
    # ------------------------------------------------------------
    pair_to_assoc = {
        (r["DiseaseID"], r["Drug_ID"]):
            r["Disease_Drug_Association_ID"]
        for _, r in dda.iterrows()
    }

    pair_mismatch = 0
    assoc_mismatch = 0

    for _, r in dde.iterrows():
        key = (r["DiseaseID"], r["Drug_ID"])
        expected = pair_to_assoc.get(key)

        if expected is None:
            pair_mismatch += 1
        elif expected != r["Disease_Drug_Association_ID"]:
            assoc_mismatch += 1

    add_problem(
        problems,
        "DDE",
        "evidence_pair_missing_from_DDA",
        pair_mismatch,
    )

    add_problem(
        problems,
        "DDE",
        "association_id_pair_mismatch",
        assoc_mismatch,
    )

    evidence_assoc_ids = set(dde["Disease_Drug_Association_ID"])

    add_problem(
        problems,
        "DDA",
        "canonical_pair_without_evidence",
        sum(x not in evidence_assoc_ids for x in dda_ids),
    )

    # ------------------------------------------------------------
    # Clinical trial consistency
    # ------------------------------------------------------------
    add_problem(
        problems,
        "ClinicalTrial",
        "invalid_NCT_ID_format",
        (~ct["NCT_ID"].str.fullmatch(r"NCT\d{8}", na=False)).sum(),
    )

    add_problem(
        problems,
        "ClinicalTrial",
        "ClinicalTrial_ID_not_equal_NCT_ID",
        (ct["ClinicalTrial_ID"] != ct["NCT_ID"]).sum(),
    )

    trial_to_report = dict(
        zip(ct["ClinicalTrial_ID"], ct["Clinical_Report_ID"])
    )

    report_drug_pairs = set(
        zip(drugcr["Clinical_Report_ID"], drugcr["Drug_ID"])
    )

    bad_trial_parent_drug = 0

    for _, r in drugct.iterrows():
        report_id = trial_to_report.get(r["ClinicalTrial_ID"], "")
        if (report_id, r["Drug_ID"]) not in report_drug_pairs:
            bad_trial_parent_drug += 1

    add_problem(
        problems,
        "Drug_ClinicalTrial",
        "trial_drug_not_linked_to_parent_report",
        bad_trial_parent_drug,
    )

    # ------------------------------------------------------------
    # Expected refinement semantics
    # ------------------------------------------------------------
    retinol = drug[
        drug["Preferred_Name"].str.upper().eq("RETINOL")
    ]

    if len(retinol) != 1:
        add_problem(
            problems,
            "Drug",
            "expected_exactly_one_RETINOL_entity",
            abs(len(retinol) - 1) or 1,
            f"rows={len(retinol)}",
        )
        retinol_id = ""
    else:
        retinol_id = retinol.iloc[0]["Drug_ID"]

        if retinol.iloc[0]["ChEMBL_ID"].upper() != "CHEMBL986":
            add_problem(
                problems,
                "Drug",
                "RETINOL_wrong_ChEMBL_ID",
                1,
                retinol.iloc[0]["ChEMBL_ID"],
            )

    tretinoin_id = "ODDB-DRUG-6B3235E14695"

    # No refined pair-specific DDA should retain these two incorrect pairs.
    for did in ["ODDB-131", "ODDB-195"]:
        if ((dda["DiseaseID"] == did) &
            (dda["Drug_ID"] == tretinoin_id)).any():
            add_problem(
                problems,
                "DDA",
                "incorrect_TRETINOIN_pair_still_present",
                1,
                did,
            )

        if retinol_id and not (
            (dda["DiseaseID"] == did) &
            (dda["Drug_ID"] == retinol_id)
        ).any():
            add_problem(
                problems,
                "DDA",
                "expected_RETINOL_pair_missing",
                1,
                did,
            )

    # Clinical-report status counts.
    status_counts = (
        drugcr["Identity_Resolution_Status"]
        .value_counts()
        .to_dict()
    )

    expected_status_counts = {
        "resolved_remap_to_retinol": 6,
        "retained_source_identifier_conflict": 5,
        "manual_review_pending_stereochemistry": 1,
        "manual_review_pending_alias_identity": 1,
    }

    for status, expected in expected_status_counts.items():
        actual = int(status_counts.get(status, 0))
        if actual != expected:
            add_problem(
                problems,
                "Drug_Clinical_Report",
                f"unexpected_status_count_{status}",
                abs(actual - expected) or 1,
                f"expected={expected}; actual={actual}",
            )

    # Retinol trial remaps should be 5.
    retinol_trial_count = int(
        drugct["Identity_Resolution_Status"]
        .eq("resolved_remap_to_retinol")
        .sum()
    )

    if retinol_trial_count != 5:
        add_problem(
            problems,
            "Drug_ClinicalTrial",
            "unexpected_RETINOL_trial_remap_count",
            abs(retinol_trial_count - 5) or 1,
            f"expected=5; actual={retinol_trial_count}",
        )

    # ChEMBL enrichment count: 51 existing rows + RETINOL.
    refined_status_counts = (
        drug["Drug_Identity_Refinement_Status"]
        .value_counts()
        .to_dict()
        if "Drug_Identity_Refinement_Status" in drug.columns
        else {}
    )

    chembl_enriched = int(
        refined_status_counts.get("chembl_identifier_enriched", 0)
    )
    new_verified = int(
        refined_status_counts.get("new_verified_drug_entity", 0)
    )

    if chembl_enriched != 51:
        add_problem(
            problems,
            "Drug",
            "unexpected_ChEMBL_enrichment_count",
            abs(chembl_enriched - 51) or 1,
            f"expected=51; actual={chembl_enriched}",
        )

    if new_verified != 1:
        add_problem(
            problems,
            "Drug",
            "unexpected_new_verified_drug_count",
            abs(new_verified - 1) or 1,
            f"expected=1; actual={new_verified}",
        )

    # ------------------------------------------------------------
    # Aggregate context semantics
    # ------------------------------------------------------------
    expected_demoted_class = (
        "aggregate_context_only_not_direct_pair_evidence"
    )

    add_problem(
        problems,
        "Demoted_Aggregate_Context",
        "unexpected_context_class",
        (~demoted["Aggregate_Context_Class"]
          .eq(expected_demoted_class)).sum(),
    )

    dda_pairs = set(zip(dda["DiseaseID"], dda["Drug_ID"]))
    demoted_pairs = set(zip(demoted["DiseaseID"], demoted["Drug_ID"]))

    add_problem(
        problems,
        "Demoted_Aggregate_Context",
        "demoted_pair_present_in_DDA",
        sum(x in dda_pairs for x in demoted_pairs),
    )

    # ------------------------------------------------------------
    # Overlap semantics
    # ------------------------------------------------------------
    overlap_pairs = set(
        zip(overlap_summary["DiseaseID"], overlap_summary["Drug_ID"])
    )

    direct_yes = overlap_summary[
        overlap_summary["Direct_Disease_Drug_Evidence"].eq("Yes")
    ]
    direct_no = overlap_summary[
        overlap_summary["Direct_Disease_Drug_Evidence"].eq("No")
    ]

    direct_yes_pairs = set(
        zip(direct_yes["DiseaseID"], direct_yes["Drug_ID"])
    )
    direct_no_pairs = set(
        zip(direct_no["DiseaseID"], direct_no["Drug_ID"])
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "direct_yes_pair_missing_from_DDA",
        sum(x not in dda_pairs for x in direct_yes_pairs),
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "direct_no_pair_present_in_DDA",
        sum(x in dda_pairs for x in direct_no_pairs),
    )

    no_overlap_pairs = set(
        zip(no_overlap["DiseaseID"], no_overlap["Drug_ID"])
    )

    expected_no_overlap = dda_pairs - overlap_pairs

    add_problem(
        problems,
        "Direct_Without_Target_Overlap",
        "pair_set_differs_from_DDA_minus_overlap",
        len(no_overlap_pairs.symmetric_difference(expected_no_overlap)),
    )

    summary_flag = {
        (r["DiseaseID"], r["Drug_ID"]):
            r["Direct_Disease_Drug_Evidence"]
        for _, r in overlap_summary.iterrows()
    }

    path_flag_mismatch = 0

    for _, r in overlap.iterrows():
        key = (r["DiseaseID"], r["Drug_ID"])
        if summary_flag.get(key) != r["Direct_Disease_Drug_Evidence"]:
            path_flag_mismatch += 1

    add_problem(
        problems,
        "Target_Overlap",
        "path_direct_flag_disagrees_with_summary",
        path_flag_mismatch,
    )

    # ------------------------------------------------------------
    # Expected final row counts
    # ------------------------------------------------------------
    expected_counts = {
        "Disease": 162,
        "Gene": 1249,
        "DGA": 1631,
        "Drug": 805,
        "Drug_Form_Relationship": 99,
        "DTA": 1009,
        "DDA": 344,
        "DDE": 1142,
        "Clinical_Report": 1291,
        "Disease_Clinical_Report": 1370,
        "Drug_Clinical_Report": 1575,
        "ClinicalTrial": 1164,
        "Disease_ClinicalTrial": 1235,
        "Drug_ClinicalTrial": 1448,
        "Aggregate_Context": 157,
        "Demoted_Aggregate_Context": 22,
        "Target_Overlap": 1322,
        "Target_Overlap_Summary": 1203,
        "Direct_Without_Target_Overlap": 317,
    }

    for name, expected in expected_counts.items():
        actual = len(data[name])
        if actual != expected:
            add_problem(
                problems,
                name,
                "unexpected_row_count",
                abs(actual - expected) or 1,
                f"expected={expected}; actual={actual}",
            )

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    metrics = [
        ("Disease_rows", len(disease)),
        ("Gene_rows", len(gene)),
        ("DGA_rows", len(dga)),
        ("Drug_rows", len(drug)),
        ("Drug_Form_Relationship_rows", len(forms)),
        ("Drug_Target_Association_rows", len(dta)),
        ("Disease_Drug_Association_rows", len(dda)),
        ("Disease_Drug_Evidence_rows", len(dde)),
        ("DDA_unique_diseases", dda["DiseaseID"].nunique()),
        ("DDA_unique_drugs", dda["Drug_ID"].nunique()),
        ("Clinical_Report_rows", len(cr)),
        ("Disease_Clinical_Report_links", len(dcr)),
        ("Drug_Clinical_Report_links", len(drugcr)),
        ("ClinicalTrial_rows", len(ct)),
        ("Disease_ClinicalTrial_links", len(dct)),
        ("Drug_ClinicalTrial_links", len(drugct)),
        ("Aggregate_context_rows", len(agg)),
        ("Demoted_aggregate_context_rows", len(demoted)),
        ("Target_overlap_path_rows", len(overlap)),
        ("Target_overlap_unique_pairs", len(overlap_summary)),
        ("Target_overlap_plus_direct_pairs", len(direct_yes_pairs)),
        ("Target_overlap_only_pairs", len(direct_no_pairs)),
        ("Direct_pairs_without_target_overlap", len(no_overlap_pairs)),
        ("ChEMBL_enriched_existing_drugs", chembl_enriched),
        ("New_RETINOL_entities", new_verified),
        ("RETINOL_report_remaps",
         int(drugcr["Identity_Resolution_Status"]
             .eq("resolved_remap_to_retinol").sum())),
        ("RETINOL_trial_remaps", retinol_trial_count),
        ("Pegaptanib_source_conflict_flags",
         int(drugcr["Identity_Resolution_Status"]
             .eq("retained_source_identifier_conflict").sum())),
        ("Levothyroxine_pending_review",
         int(drugcr["Identity_Resolution_Status"]
             .eq("manual_review_pending_stereochemistry").sum())),
        ("X82_pending_review",
         int(drugcr["Identity_Resolution_Status"]
             .eq("manual_review_pending_alias_identity").sum())),
        ("Validation_problem_types", len(problems)),
        ("Validation_problem_rows_total",
         sum(int(x["Count"]) for x in problems)),
    ]

    summary = pd.DataFrame(metrics, columns=["Metric", "Value"])

    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = (
        report_dir /
        "oddb_v1_drug_clinical_refined_validation_summary.tsv"
    )
    problems_path = (
        report_dir /
        "oddb_v1_drug_clinical_refined_validation_problems.tsv"
    )
    manifest_path = (
        report_dir /
        "ODDB_v1_drug_clinical_refined_manifest.json"
    )

    summary.to_csv(summary_path, sep="\t", index=False)

    pd.DataFrame(
        problems,
        columns=["Table", "Problem", "Count", "Detail"],
    ).to_csv(
        problems_path,
        sep="\t",
        index=False,
    )

    manifest = {
        "release_name":
            "ODDB_v1_drug_clinical_refined_2026-09-30",
        "status":
            "VALIDATION_PASSED"
            if not problems else "VALIDATION_FAILED",
        "supersedes_for_future_work":
            "ODDB_v1_drug_clinical_2026-09-30",
        "note":
            "Earlier frozen release remains immutable; this refined "
            "snapshot incorporates verified drug identity corrections.",
        "principles": [
            "Direct disease-drug evidence is distinct from drug-target pharmacology.",
            "Target overlap is discovery context, not therapeutic evidence.",
            "Clinical-trial investigation is not automatically approval.",
            "Multi-entity clinical reports are not expanded into disease-drug cross-products.",
            "Drug salts/forms remain distinct entities linked through Drug_Form_Relationship.",
            "Source drug identifiers are preserved and identity conflicts are explicitly flagged.",
            "RETINOL and TRETINOIN are distinct molecular entities.",
            "Pegaptanib source-ID conflicts remain flagged rather than silently normalized.",
        ],
        "files": {},
        "metrics": {k: int(v) for k, v in metrics},
    }

    for name, path in files.items():
        manifest["files"][name] = {
            "filename": path.name,
            "source_path": str(path),
            "rows": len(data[name]),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("ODDB v1 REFINED DRUG / CLINICAL FINAL VALIDATION")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION FAILED")
        print(pd.DataFrame(problems).to_string(index=False))
        print("\nNothing was frozen.")
        raise SystemExit(1)

    print("\nVALIDATION PASSED.")

    # ------------------------------------------------------------
    # Freeze
    # ------------------------------------------------------------
    if release_dir.exists():
        raise SystemExit(
            f"Release directory already exists: {release_dir}\n"
            "Refusing to overwrite an existing frozen release."
        )

    release_dir.mkdir(parents=True)

    for name, path in files.items():
        shutil.copy2(path, release_dir / path.name)

    shutil.copy2(summary_path, release_dir / summary_path.name)
    shutil.copy2(problems_path, release_dir / problems_path.name)
    shutil.copy2(manifest_path, release_dir / manifest_path.name)

    for p in release_dir.rglob("*"):
        if p.is_file():
            p.chmod(0o444)
        elif p.is_dir():
            p.chmod(0o555)

    release_dir.chmod(0o555)

    print("\nFROZEN REFINED RELEASE CREATED:")
    print(release_dir)

    print("\nManifest:")
    print(release_dir / manifest_path.name)

    print(
        "\nEarlier frozen release was not modified:"
        "\nreleases/ODDB_v1_drug_clinical_2026-09-30"
    )


if __name__ == "__main__":
    main()
