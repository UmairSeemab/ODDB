#!/usr/bin/env python3
"""
Enrich canonical ODDB disease-drug evidence with Open Targets clinicalReportIds.

This restores provenance that is present in:
    OpenTargets_Clinical_Target_Context_v1
but was not carried into:
    Disease_Drug_Evidence_v1

For each Open Targets disease-drug evidence record:
- resolve its OpenTargets_Clinical_Target_IDs
- aggregate Clinical_Report_IDs_JSON
- extract NCT identifiers
- preserve non-NCT report identifiers separately

Existing canonical IDs are NOT changed.
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd


def clean(x):
    return str(x or "").strip()


def split_pipe(x):
    return [v.strip() for v in clean(x).split("|") if v.strip()]


def uniq(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def uniq_join(values):
    return " | ".join(uniq(values))


def parse_json_list(x):
    x = clean(x)
    if not x:
        return []
    try:
        value = json.loads(x)
        if isinstance(value, list):
            return value
    except Exception:
        pass
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical-evidence", required=True)
    ap.add_argument("--opentargets-evidence", required=True)
    ap.add_argument("--clinical-context", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    canonical = pd.read_csv(
        args.canonical_evidence, sep="\t", dtype=str
    ).fillna("")
    ot_ev = pd.read_csv(
        args.opentargets_evidence, sep="\t", dtype=str
    ).fillna("")
    context = pd.read_csv(
        args.clinical_context, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    required_canonical = {
        "Disease_Drug_Evidence_ID",
        "Evidence_Source",
        "Source_Record_ID",
    }
    required_ot = {
        "Disease_Drug_OpenTargets_Evidence_ID",
        "OpenTargets_Clinical_Target_IDs",
    }
    required_context = {
        "OpenTargets_Clinical_Target_ID",
        "Clinical_Report_IDs_JSON",
    }

    for name, df, required in [
        ("canonical", canonical, required_canonical),
        ("OpenTargets evidence", ot_ev, required_ot),
        ("clinical context", context, required_context),
    ]:
        missing = required - set(df.columns)
        if missing:
            raise SystemExit(
                f"{name} missing required columns: {sorted(missing)}"
            )

    # ------------------------------------------------------------------
    # Clinical target ID -> report IDs
    # ------------------------------------------------------------------
    report_lookup = {}

    for _, r in context.iterrows():
        ctid = clean(r["OpenTargets_Clinical_Target_ID"])
        if not ctid:
            continue

        report_ids = [
            clean(x)
            for x in parse_json_list(r["Clinical_Report_IDs_JSON"])
            if clean(x)
        ]

        report_lookup.setdefault(ctid, [])
        report_lookup[ctid].extend(report_ids)

    report_lookup = {
        k: uniq(v)
        for k, v in report_lookup.items()
    }

    # ------------------------------------------------------------------
    # Open Targets disease-drug evidence -> clinical report provenance
    # ------------------------------------------------------------------
    ot_provenance = {}
    missing_target_ids = []

    for _, r in ot_ev.iterrows():
        source_record_id = clean(
            r["Disease_Drug_OpenTargets_Evidence_ID"]
        )

        clinical_target_ids = split_pipe(
            r["OpenTargets_Clinical_Target_IDs"]
        )

        report_ids = []

        for ctid in clinical_target_ids:
            if ctid not in report_lookup:
                missing_target_ids.append(ctid)
                continue
            report_ids.extend(report_lookup[ctid])

        report_ids = uniq(report_ids)

        nct_ids = uniq(
            x.upper()
            for x in report_ids
            if re.fullmatch(r"NCT\d{8}", x, flags=re.I)
        )

        non_nct = uniq(
            x for x in report_ids
            if not re.fullmatch(r"NCT\d{8}", x, flags=re.I)
        )

        ot_provenance[source_record_id] = {
            "Clinical_Report_IDs": uniq_join(report_ids),
            "NCT_IDs": uniq_join(nct_ids),
            "Non_NCT_Clinical_Report_IDs": uniq_join(non_nct),
            "Clinical_Report_ID_Count": len(report_ids),
            "NCT_ID_Count": len(nct_ids),
            "ClinicalTrial_Link_Status":
                "has_nct_id" if nct_ids else "no_nct_id",
        }

    # ------------------------------------------------------------------
    # Add provenance columns without changing IDs
    # ------------------------------------------------------------------
    for col in [
        "Clinical_Report_IDs",
        "NCT_IDs",
        "Non_NCT_Clinical_Report_IDs",
        "Clinical_Report_ID_Count",
        "NCT_ID_Count",
        "ClinicalTrial_Link_Status",
    ]:
        canonical[col] = ""

    ot_rows = 0
    ot_rows_matched = 0
    ot_rows_with_nct = 0
    canonical_missing_source_records = []

    for idx, r in canonical.iterrows():
        if clean(r["Evidence_Source"]) != "Open_Targets":
            continue

        ot_rows += 1
        source_record_id = clean(r["Source_Record_ID"])

        prov = ot_provenance.get(source_record_id)

        if prov is None:
            canonical_missing_source_records.append(source_record_id)
            continue

        ot_rows_matched += 1

        for col, value in prov.items():
            canonical.at[idx, col] = str(value)

        if prov["NCT_ID_Count"] > 0:
            ot_rows_with_nct += 1

    # ------------------------------------------------------------------
    # NCT seed table
    # ------------------------------------------------------------------
    seed_rows = []

    for _, r in canonical.iterrows():
        ncts = split_pipe(r["NCT_IDs"])

        for nct in ncts:
            seed_rows.append({
                "NCT_ID": nct,
                "Disease_Drug_Evidence_ID":
                    clean(r["Disease_Drug_Evidence_ID"]),
                "Disease_Drug_Association_ID":
                    clean(r.get("Disease_Drug_Association_ID")),
                "DiseaseID": clean(r.get("DiseaseID")),
                "Disease_Name": clean(r.get("Disease_Name")),
                "Drug_ID": clean(r.get("Drug_ID")),
                "Drug_Name": clean(r.get("Drug_Name")),
                "Evidence_Source": clean(r.get("Evidence_Source")),
                "OpenTargets_Source_Record_ID":
                    clean(r.get("Source_Record_ID")),
            })

    seed = pd.DataFrame(seed_rows)

    if len(seed):
        unique_nct = (
            seed[["NCT_ID"]]
            .drop_duplicates()
            .sort_values("NCT_ID")
            .reset_index(drop=True)
        )
    else:
        unique_nct = pd.DataFrame(columns=["NCT_ID"])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    problems = []

    if canonical[
        "Disease_Drug_Evidence_ID"
    ].duplicated().any():
        problems.append(
            "Disease_Drug_Evidence_ID uniqueness changed"
        )

    if canonical_missing_source_records:
        problems.append(
            "Some Open Targets canonical evidence rows could not be linked "
            "back to Disease_Drug_OpenTargets_Evidence"
        )

    if missing_target_ids:
        problems.append(
            "Some OpenTargets_Clinical_Target_IDs were absent from "
            "clinical-context input"
        )

    summary = pd.DataFrame([
        ["Canonical_evidence_rows", len(canonical)],
        ["OpenTargets_evidence_rows_in_canonical", ot_rows],
        ["OpenTargets_rows_linked_to_source_record", ot_rows_matched],
        ["OpenTargets_rows_with_at_least_one_NCT", ot_rows_with_nct],
        ["Unique_NCT_IDs", unique_nct["NCT_ID"].nunique()],
        ["Disease_drug_NCT_link_rows", len(seed)],
        ["Unique_diseases_with_NCT_links",
         seed["DiseaseID"].nunique() if len(seed) else 0],
        ["Unique_drugs_with_NCT_links",
         seed["Drug_ID"].nunique() if len(seed) else 0],
        ["Missing_OpenTargets_source_records",
         len(set(canonical_missing_source_records))],
        ["Missing_clinical_target_IDs",
         len(set(missing_target_ids))],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    canonical.to_csv(
        args.output, sep="\t", index=False
    )

    seed.to_csv(
        outdir / "disease_drug_nct_links.tsv",
        sep="\t", index=False
    )

    unique_nct.to_csv(
        outdir / "clinicaltrial_nct_seed_ids.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "clinical_report_provenance_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({
        "Missing_Source_Record_ID":
            sorted(set(canonical_missing_source_records))
    }).to_csv(
        outdir / "missing_opentargets_source_records.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({
        "Missing_OpenTargets_Clinical_Target_ID":
            sorted(set(missing_target_ids))
    }).to_csv(
        outdir / "missing_clinical_target_ids.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        outdir / "clinical_report_provenance_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB OPEN TARGETS CLINICAL-REPORT PROVENANCE ENRICHMENT")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nEnriched evidence:", args.output)
    print("NCT linkage table:",
          outdir / "disease_drug_nct_links.tsv")
    print("Unique NCT seed IDs:",
          outdir / "clinicaltrial_nct_seed_ids.tsv")
    print("Reports:", outdir)


if __name__ == "__main__":
    main()
