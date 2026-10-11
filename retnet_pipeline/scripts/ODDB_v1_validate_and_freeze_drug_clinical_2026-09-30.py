#!/usr/bin/env python3
"""
Validate and freeze the ODDB v1 drug / clinical layer.

The script:
1. validates primary keys and major foreign keys;
2. validates disease-drug evidence integrity;
3. validates clinical report / trial link tables;
4. validates aggregate-context demotion;
5. validates final disease-drug target-overlap semantics;
6. writes a validation summary, problem table, and SHA256 manifest;
7. copies validated files into an immutable release directory.

It does not modify the source processed files.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_tsv(path):
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def add_problem(problems, table, problem, count, detail=""):
    if int(count) > 0:
        problems.append({
            "Table": table,
            "Problem": problem,
            "Count": int(count),
            "Detail": detail,
        })


def require_columns(df, table, cols, problems):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        add_problem(
            problems,
            table,
            "missing_required_columns",
            len(missing),
            " | ".join(missing),
        )
    return not missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-dir", default="data/processed")
    ap.add_argument(
        "--report-dir",
        default="reports/oddb_v1_drug_clinical_freeze_2026-09-30",
    )
    ap.add_argument(
        "--release-dir",
        default="releases/ODDB_v1_drug_clinical_2026-09-30",
    )
    args = ap.parse_args()

    pdir = Path(args.processed_dir)
    report_dir = Path(args.report_dir)
    release_dir = Path(args.release_dir)

    files = {
        "Disease":
            pdir / "Disease_v1_final_2026-09-29.tsv",
        "Gene":
            pdir / "Gene_v1_2026-09-29.tsv",
        "DGA":
            pdir / "Disease_Gene_Association_v1_final_2026-09-29.tsv",
        "Drug":
            pdir / "Drug_v1_opentargets_2026-09-29.tsv",
        "DTA":
            pdir / "Drug_Target_Association_v1_2026-09-29.tsv",
        "DDA":
            pdir / "Disease_Drug_Association_v1_final_2026-09-30.tsv",
        "DDE":
            pdir / "Disease_Drug_Evidence_v1_final_2026-09-30.tsv",
        "Clinical_Report":
            pdir / "Clinical_Report_v1_2026-09-30.tsv",
        "Disease_Clinical_Report":
            pdir / "Disease_Clinical_Report_Association_v1_2026-09-30.tsv",
        "Drug_Clinical_Report":
            pdir / "Drug_Clinical_Report_Association_v1_2026-09-30.tsv",
        "ClinicalTrial":
            pdir / "ClinicalTrial_v1_2026-09-30.tsv",
        "Disease_ClinicalTrial":
            pdir / "Disease_ClinicalTrial_Association_v1_2026-09-30.tsv",
        "Drug_ClinicalTrial":
            pdir / "Drug_ClinicalTrial_Association_v1_2026-09-30.tsv",
        "Aggregate_Context":
            pdir / "Disease_Drug_Aggregate_Clinical_Context_v1_2026-09-30.tsv",
        "Demoted_Aggregate_Context":
            pdir / "Disease_Drug_Aggregate_Context_Demoted_v1_2026-09-30.tsv",
        "Target_Overlap":
            pdir / "Disease_Drug_Target_Overlap_v1_final_2026-09-30.tsv",
        "Target_Overlap_Summary":
            pdir / "Disease_Drug_Target_Overlap_Summary_v1_final_2026-09-30.tsv",
        "Direct_Without_Target_Overlap":
            pdir / "Disease_Drug_Direct_Evidence_Without_Target_Overlap_v1_final_2026-09-30.tsv",
    }

    problems = []

    missing_files = [
        f"{name}: {path}"
        for name, path in files.items()
        if not path.exists()
    ]

    if missing_files:
        raise SystemExit(
            "Required files are missing:\n" + "\n".join(missing_files)
        )

    data = {name: read_tsv(path) for name, path in files.items()}

    disease = data["Disease"]
    gene = data["Gene"]
    dga = data["DGA"]
    drug = data["Drug"]
    dta = data["DTA"]
    dda = data["DDA"]
    dde = data["DDE"]
    cr = data["Clinical_Report"]
    dcr = data["Disease_Clinical_Report"]
    dgcr = data["Drug_Clinical_Report"]
    ct = data["ClinicalTrial"]
    dct = data["Disease_ClinicalTrial"]
    dgct = data["Drug_ClinicalTrial"]
    agg = data["Aggregate_Context"]
    demoted = data["Demoted_Aggregate_Context"]
    overlap = data["Target_Overlap"]
    overlap_summary = data["Target_Overlap_Summary"]
    no_overlap = data["Direct_Without_Target_Overlap"]

    # --------------------------------------------------------------
    # Required columns
    # --------------------------------------------------------------
    requirements = {
        "Disease": ["DiseaseID"],
        "Gene": ["HGNC_ID"],
        "DGA": ["Association_ID", "DiseaseID", "HGNC_ID"],
        "Drug": ["Drug_ID"],
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
            "Clinical_Report_ID",
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
            "ClinicalTrial_ID",
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

    for name, cols in requirements.items():
        require_columns(data[name], name, cols, problems)

    # If fundamental columns are missing, still write a problem report but
    # avoid cascading KeyErrors.
    if problems:
        report_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(problems).to_csv(
            report_dir / "oddb_v1_drug_clinical_validation_problems.tsv",
            sep="\t",
            index=False,
        )
        raise SystemExit(
            "Validation stopped because required columns are missing."
        )

    # --------------------------------------------------------------
    # Primary-key uniqueness
    # --------------------------------------------------------------
    pk_checks = {
        "Disease": ("DiseaseID", disease),
        "Gene": ("HGNC_ID", gene),
        "DGA": ("Association_ID", dga),
        "Drug": ("Drug_ID", drug),
        "DTA": ("Drug_Target_Association_ID", dta),
        "DDA": ("Disease_Drug_Association_ID", dda),
        "DDE": ("Disease_Drug_Evidence_ID", dde),
        "Clinical_Report": ("Clinical_Report_ID", cr),
        "Disease_Clinical_Report":
            ("Disease_Clinical_Report_Association_ID", dcr),
        "Drug_Clinical_Report":
            ("Drug_Clinical_Report_Association_ID", dgcr),
        "ClinicalTrial": ("ClinicalTrial_ID", ct),
        "Disease_ClinicalTrial":
            ("Disease_ClinicalTrial_Association_ID", dct),
        "Drug_ClinicalTrial":
            ("Drug_ClinicalTrial_Association_ID", dgct),
        "Target_Overlap":
            ("Disease_Drug_Target_Overlap_ID", overlap),
        "Target_Overlap_Summary":
            ("Disease_Drug_Target_Summary_ID", overlap_summary),
    }

    for name, (pk, df) in pk_checks.items():
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
            df[pk].astype(str).str.strip().eq("").sum(),
            pk,
        )

    # Natural key uniqueness
    add_problem(
        problems,
        "DDA",
        "duplicate_DiseaseID_Drug_ID_pair",
        dda.duplicated(["DiseaseID", "Drug_ID"]).sum(),
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "duplicate_DiseaseID_Drug_ID_pair",
        overlap_summary.duplicated(["DiseaseID", "Drug_ID"]).sum(),
    )

    # --------------------------------------------------------------
    # FK sets
    # --------------------------------------------------------------
    disease_ids = set(disease["DiseaseID"])
    gene_ids = set(gene["HGNC_ID"])
    drug_ids = set(drug["Drug_ID"])
    dda_ids = set(dda["Disease_Drug_Association_ID"])
    cr_ids = set(cr["Clinical_Report_ID"])
    ct_ids = set(ct["ClinicalTrial_ID"])

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
        ("Disease_Clinical_Report", dcr, "DiseaseID", disease_ids),
        ("Disease_Clinical_Report", dcr, "Clinical_Report_ID", cr_ids),
        ("Drug_Clinical_Report", dgcr, "Drug_ID", drug_ids),
        ("Drug_Clinical_Report", dgcr, "Clinical_Report_ID", cr_ids),
        ("ClinicalTrial", ct, "Clinical_Report_ID", cr_ids),
        ("Disease_ClinicalTrial", dct, "DiseaseID", disease_ids),
        ("Disease_ClinicalTrial", dct, "ClinicalTrial_ID", ct_ids),
        ("Drug_ClinicalTrial", dgct, "Drug_ID", drug_ids),
        ("Drug_ClinicalTrial", dgct, "ClinicalTrial_ID", ct_ids),
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

    # --------------------------------------------------------------
    # Evidence -> canonical pair consistency
    # --------------------------------------------------------------
    dda_key_to_id = {
        (r["DiseaseID"], r["Drug_ID"]):
            r["Disease_Drug_Association_ID"]
        for _, r in dda.iterrows()
    }

    evidence_pair_mismatch = 0
    evidence_assoc_mismatch = 0

    for _, r in dde.iterrows():
        key = (r["DiseaseID"], r["Drug_ID"])
        expected_id = dda_key_to_id.get(key)

        if expected_id is None:
            evidence_pair_mismatch += 1
        elif r["Disease_Drug_Association_ID"] != expected_id:
            evidence_assoc_mismatch += 1

    add_problem(
        problems,
        "DDE",
        "evidence_pair_not_present_in_DDA",
        evidence_pair_mismatch,
    )

    add_problem(
        problems,
        "DDE",
        "evidence_association_ID_does_not_match_pair",
        evidence_assoc_mismatch,
    )

    # Every DDA should have at least one evidence row.
    evidence_assoc_ids = set(dde["Disease_Drug_Association_ID"])
    add_problem(
        problems,
        "DDA",
        "canonical_pair_without_evidence_record",
        sum(x not in evidence_assoc_ids for x in dda_ids),
    )

    # --------------------------------------------------------------
    # Clinical trial sanity
    # --------------------------------------------------------------
    add_problem(
        problems,
        "ClinicalTrial",
        "NCT_ID_not_matching_expected_pattern",
        (~ct["NCT_ID"].str.fullmatch(r"NCT\d{8}", na=False)).sum(),
    )

    add_problem(
        problems,
        "ClinicalTrial",
        "ClinicalTrial_ID_not_equal_to_NCT_ID",
        (ct["ClinicalTrial_ID"] != ct["NCT_ID"]).sum(),
    )

    # Trial associations must point to report-linked same entity.
    report_disease_pairs = set(
        zip(dcr["Clinical_Report_ID"], dcr["DiseaseID"])
    )
    report_drug_pairs = set(
        zip(dgcr["Clinical_Report_ID"], dgcr["Drug_ID"])
    )
    trial_to_report = dict(
        zip(ct["ClinicalTrial_ID"], ct["Clinical_Report_ID"])
    )

    bad_dct_context = 0
    for _, r in dct.iterrows():
        report_id = trial_to_report.get(r["ClinicalTrial_ID"], "")
        if (report_id, r["DiseaseID"]) not in report_disease_pairs:
            bad_dct_context += 1

    bad_dgct_context = 0
    for _, r in dgct.iterrows():
        report_id = trial_to_report.get(r["ClinicalTrial_ID"], "")
        if (report_id, r["Drug_ID"]) not in report_drug_pairs:
            bad_dgct_context += 1

    add_problem(
        problems,
        "Disease_ClinicalTrial",
        "trial_disease_not_linked_to_parent_clinical_report",
        bad_dct_context,
    )

    add_problem(
        problems,
        "Drug_ClinicalTrial",
        "trial_drug_not_linked_to_parent_clinical_report",
        bad_dgct_context,
    )

    # --------------------------------------------------------------
    # Aggregate-context semantics
    # --------------------------------------------------------------
    demoted_expected_class = (
        "aggregate_context_only_not_direct_pair_evidence"
    )

    add_problem(
        problems,
        "Demoted_Aggregate_Context",
        "unexpected_aggregate_context_class",
        (~demoted["Aggregate_Context_Class"].eq(
            demoted_expected_class
        )).sum(),
    )

    agg_pairs = set(zip(agg["DiseaseID"], agg["Drug_ID"]))
    demoted_pairs = set(zip(demoted["DiseaseID"], demoted["Drug_ID"]))
    dda_pairs = set(zip(dda["DiseaseID"], dda["Drug_ID"]))

    add_problem(
        problems,
        "Demoted_Aggregate_Context",
        "demoted_pair_not_in_aggregate_context",
        sum(x not in agg_pairs for x in demoted_pairs),
    )

    add_problem(
        problems,
        "Demoted_Aggregate_Context",
        "demoted_pair_still_present_in_canonical_DDA",
        sum(x in dda_pairs for x in demoted_pairs),
    )

    # --------------------------------------------------------------
    # Final target-overlap semantics
    # --------------------------------------------------------------
    overlap_pairs = set(
        zip(overlap_summary["DiseaseID"], overlap_summary["Drug_ID"])
    )

    direct_yes_pairs = set(
        zip(
            overlap_summary.loc[
                overlap_summary[
                    "Direct_Disease_Drug_Evidence"
                ].eq("Yes"),
                "DiseaseID",
            ],
            overlap_summary.loc[
                overlap_summary[
                    "Direct_Disease_Drug_Evidence"
                ].eq("Yes"),
                "Drug_ID",
            ],
        )
    )

    direct_no_pairs = set(
        zip(
            overlap_summary.loc[
                overlap_summary[
                    "Direct_Disease_Drug_Evidence"
                ].eq("No"),
                "DiseaseID",
            ],
            overlap_summary.loc[
                overlap_summary[
                    "Direct_Disease_Drug_Evidence"
                ].eq("No"),
                "Drug_ID",
            ],
        )
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "direct_yes_pair_missing_from_final_DDA",
        sum(x not in dda_pairs for x in direct_yes_pairs),
    )

    add_problem(
        problems,
        "Target_Overlap_Summary",
        "direct_no_pair_present_in_final_DDA",
        sum(x in dda_pairs for x in direct_no_pairs),
    )

    no_overlap_pairs = set(zip(no_overlap["DiseaseID"], no_overlap["Drug_ID"]))

    expected_no_overlap_pairs = dda_pairs - overlap_pairs

    add_problem(
        problems,
        "Direct_Without_Target_Overlap",
        "pair_set_differs_from_DDA_minus_overlap",
        len(no_overlap_pairs.symmetric_difference(
            expected_no_overlap_pairs
        )),
    )

    # Path-level direct flag must agree with pair-level summary.
    summary_flag = {
        (r["DiseaseID"], r["Drug_ID"]):
            r["Direct_Disease_Drug_Evidence"]
        for _, r in overlap_summary.iterrows()
    }

    path_flag_mismatch = 0

    for _, r in overlap.iterrows():
        expected = summary_flag.get(
            (r["DiseaseID"], r["Drug_ID"])
        )
        if expected != r["Direct_Disease_Drug_Evidence"]:
            path_flag_mismatch += 1

    add_problem(
        problems,
        "Target_Overlap",
        "path_direct_flag_disagrees_with_summary",
        path_flag_mismatch,
    )

    # --------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------
    metrics = [
        ("Disease_rows", len(disease)),
        ("Gene_rows", len(gene)),
        ("DGA_rows", len(dga)),
        ("Drug_rows", len(drug)),
        ("Drug_Target_Association_rows", len(dta)),
        ("Final_Disease_Drug_Association_rows", len(dda)),
        ("Final_Disease_Drug_Evidence_rows", len(dde)),
        ("Final_DDA_unique_diseases", dda["DiseaseID"].nunique()),
        ("Final_DDA_unique_drugs", dda["Drug_ID"].nunique()),
        ("Clinical_Report_rows", len(cr)),
        ("Disease_Clinical_Report_links", len(dcr)),
        ("Drug_Clinical_Report_links", len(dgcr)),
        ("ClinicalTrial_rows", len(ct)),
        ("Disease_ClinicalTrial_links", len(dct)),
        ("Drug_ClinicalTrial_links", len(dgct)),
        ("Aggregate_context_rows", len(agg)),
        ("Demoted_aggregate_context_rows", len(demoted)),
        ("Target_overlap_path_rows", len(overlap)),
        ("Target_overlap_unique_pairs", len(overlap_summary)),
        ("Target_overlap_plus_direct_pairs", len(direct_yes_pairs)),
        ("Target_overlap_only_pairs", len(direct_no_pairs)),
        ("Direct_pairs_without_target_overlap", len(no_overlap_pairs)),
        ("Validation_problem_types", len(problems)),
        ("Validation_problem_rows_total",
         sum(int(x["Count"]) for x in problems)),
    ]

    summary = pd.DataFrame(metrics, columns=["Metric", "Value"])

    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = (
        report_dir / "oddb_v1_drug_clinical_validation_summary.tsv"
    )
    problems_path = (
        report_dir / "oddb_v1_drug_clinical_validation_problems.tsv"
    )
    manifest_path = (
        report_dir / "ODDB_v1_drug_clinical_manifest.json"
    )

    summary.to_csv(
        summary_path,
        sep="\t",
        index=False,
    )

    pd.DataFrame(
        problems,
        columns=["Table", "Problem", "Count", "Detail"],
    ).to_csv(
        problems_path,
        sep="\t",
        index=False,
    )

    manifest = {
        "release_name": "ODDB_v1_drug_clinical_2026-09-30",
        "status": "VALIDATION_PASSED" if not problems
                  else "VALIDATION_FAILED",
        "principles": [
            "Disease-drug direct evidence is distinct from drug-target pharmacology.",
            "Target overlap is discovery context, not therapeutic evidence.",
            "Clinical-trial investigation is not automatically regulatory approval.",
            "Multi-entity clinical reports are not converted into disease-drug cross-products.",
            "Aggregate Open Targets clinical_target context is not independently used to assert direct disease-drug pairs.",
        ],
        "files": {},
        "metrics": {k: int(v) for k, v in metrics},
    }

    for name, path in files.items():
        manifest["files"][name] = {
            "filename": path.name,
            "source_path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "rows": len(data[name]),
        }

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("ODDB v1 DRUG / CLINICAL FINAL VALIDATION")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION FAILED")
        print(
            pd.DataFrame(problems).to_string(index=False)
        )
        print("\nNothing was frozen.")
        raise SystemExit(1)

    print("\nVALIDATION PASSED.")

    # --------------------------------------------------------------
    # Freeze immutable snapshot only after validation passes.
    # --------------------------------------------------------------
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

    # Make release tree read-only.
    for path in release_dir.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)

    release_dir.chmod(0o555)

    print("\nFROZEN RELEASE CREATED:")
    print(release_dir)
    print("\nManifest:")
    print(release_dir / manifest_path.name)


if __name__ == "__main__":
    main()
