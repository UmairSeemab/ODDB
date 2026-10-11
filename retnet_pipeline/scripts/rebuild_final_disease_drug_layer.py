#!/usr/bin/env python3
"""
Rebuild final ODDB v1 disease-drug layer using source-level direct evidence.

Canonical direct evidence sources
---------------------------------
1. Normalized legacy ODDB disease-drug associations.
2. Pair-specific Open Targets clinical reports where the report has:
   - exactly one mapped ODDB disease
   - exactly one mapped ODDB drug
   - Report_Type == INDICATION

NOT used to create canonical direct pairs
-----------------------------------------
Aggregated Open Targets clinical_target disease-drug context.

The aggregate context is preserved separately and labelled according to
whether the same DiseaseID + Drug_ID is corroborated by a pair-specific
clinical report.

Outputs
-------
- Disease_Drug_Association_v1_final
- Disease_Drug_Evidence_v1_final
- Disease_Drug_Aggregate_Clinical_Context_v1
- Disease_Drug_Aggregate_Context_Demoted_v1
- QC reports

Existing Disease_Drug_Association_ID values remain deterministic from
DiseaseID + Drug_ID.
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
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


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


def split_pipe(x):
    return [v.strip() for v in clean(x).split("|") if v.strip()]


def find_col(df, candidates, required=False):
    norm = {
        re.sub(r"[^a-z0-9]+", "", c.lower()): c
        for c in df.columns
    }

    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in norm:
            return norm[key]

    if required:
        raise SystemExit(
            f"Required column not found among {candidates}. "
            f"Available columns: {list(df.columns)}"
        )

    return None


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--legacy-dda", required=True)
    ap.add_argument("--pair-report-evidence", required=True)
    ap.add_argument("--aggregate-opentargets-evidence", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--drugs", required=True)

    ap.add_argument("--association-output", required=True)
    ap.add_argument("--evidence-output", required=True)
    ap.add_argument("--aggregate-context-output", required=True)
    ap.add_argument("--demoted-output", required=True)
    ap.add_argument("--report-dir", required=True)

    args = ap.parse_args()

    legacy = pd.read_csv(
        args.legacy_dda, sep="\t", dtype=str
    ).fillna("")

    pair_reports = pd.read_csv(
        args.pair_report_evidence, sep="\t", dtype=str
    ).fillna("")

    aggregate_ot = pd.read_csv(
        args.aggregate_opentargets_evidence, sep="\t", dtype=str
    ).fillna("")

    diseases = pd.read_csv(
        args.diseases, sep="\t", dtype=str
    ).fillna("")

    drugs = pd.read_csv(
        args.drugs, sep="\t", dtype=str
    ).fillna("")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    for path in [
        args.association_output,
        args.evidence_output,
        args.aggregate_context_output,
        args.demoted_output,
    ]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # Canonical names / FKs
    # -------------------------------------------------------------
    disease_name_col = find_col(
        diseases,
        ["Disease_Name", "Ocular.disease", "Disease"],
        required=True,
    )

    drug_name_col = find_col(
        drugs,
        ["Preferred_Name", "Drug_Name", "Name"],
        required=True,
    )

    disease_name_map = dict(
        zip(diseases["DiseaseID"], diseases[disease_name_col])
    )

    drug_name_map = dict(
        zip(drugs["Drug_ID"], drugs[drug_name_col])
    )

    valid_diseases = set(diseases["DiseaseID"])
    valid_drugs = set(drugs["Drug_ID"])

    # -------------------------------------------------------------
    # Validate required pair-report columns
    # -------------------------------------------------------------
    pair_required = {
        "Clinical_Report_ID",
        "DiseaseID",
        "Drug_ID",
        "Evidence_Subtype",
        "Origin",
        "Source",
        "Provider",
        "Clinical_Stage",
        "Phase_From_Source",
        "Trial_Phase",
        "Trial_Overall_Status",
        "NCT_IDs",
        "Title",
        "URL",
    }

    missing_pair = pair_required - set(pair_reports.columns)

    if missing_pair:
        raise SystemExit(
            "pair-report evidence missing columns: "
            + ", ".join(sorted(missing_pair))
        )

    # -------------------------------------------------------------
    # Optional legacy columns
    # -------------------------------------------------------------
    legacy_phase_col = find_col(
        legacy,
        ["Observed_Development_Phases", "Phase"],
        required=False,
    )

    legacy_max_phase_col = find_col(
        legacy,
        ["Maximum_Observed_Phase"],
        required=False,
    )

    legacy_refs_col = find_col(
        legacy,
        ["References", "Merged_RefNew", "Reference"],
        required=False,
    )

    legacy_status_col = find_col(
        legacy,
        ["Curation_Status", "Relationship_Type"],
        required=False,
    )

    # -------------------------------------------------------------
    # Pair sets
    # -------------------------------------------------------------
    legacy_pairs = set(
        zip(legacy["DiseaseID"], legacy["Drug_ID"])
    )

    report_pairs = set(
        zip(pair_reports["DiseaseID"], pair_reports["Drug_ID"])
    )

    canonical_pairs = legacy_pairs | report_pairs
    shared_pairs = legacy_pairs & report_pairs

    aggregate_pairs = set(
        zip(
            aggregate_ot["DiseaseID"],
            aggregate_ot["Drug_ID"],
        )
    )

    # -------------------------------------------------------------
    # Build source-specific evidence table
    # -------------------------------------------------------------
    evidence_rows = []

    # Legacy evidence
    for _, r in legacy.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        assoc_id = stable_id("ODDB-DDA", did, drug_id)

        source_record_id = clean(
            r.get("Disease_Drug_Association_ID", "")
        )

        evidence_rows.append({
            "Disease_Drug_Evidence_ID": stable_id(
                "ODDB-DDE",
                "legacy_oddb",
                source_record_id or assoc_id,
            ),
            "Disease_Drug_Association_ID": assoc_id,
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(
                drug_id,
                clean(r.get("Drug_Name", "")),
            ),
            "Evidence_Source_Class": "legacy_curated",
            "Evidence_Type": "legacy_disease_drug_evidence",
            "Evidence_Source": "ODDB_legacy",
            "Evidence_Origin": "legacy",
            "Provider": "",
            "Source_Record_ID": source_record_id,
            "Clinical_Report_ID": "",
            "NCT_IDs": "",
            "Clinical_Stage": "",
            "Phase_From_Source":
                clean(r.get(legacy_phase_col, ""))
                if legacy_phase_col else "",
            "Trial_Phase": "",
            "Trial_Overall_Status": "",
            "Legacy_Maximum_Development_Phase":
                clean(r.get(legacy_max_phase_col, ""))
                if legacy_max_phase_col else "",
            "Title": "",
            "URL": "",
            "References":
                clean(r.get(legacy_refs_col, ""))
                if legacy_refs_col else "",
            "Source_Curation_Status":
                clean(r.get(legacy_status_col, ""))
                if legacy_status_col else "",
            "Pair_Specificity":
                "legacy_curated_disease_drug_pair",
            "Interpretation":
                "Direct disease-drug evidence retained from the "
                "normalized ODDB legacy layer.",
        })

    # Pair-specific clinical report evidence
    for _, r in pair_reports.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        clinical_report_id = clean(r["Clinical_Report_ID"])
        assoc_id = stable_id("ODDB-DDA", did, drug_id)

        subtype = clean(r["Evidence_Subtype"])

        evidence_rows.append({
            "Disease_Drug_Evidence_ID": stable_id(
                "ODDB-DDE",
                "clinical_report",
                clinical_report_id,
                did,
                drug_id,
            ),
            "Disease_Drug_Association_ID": assoc_id,
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(
                did,
                clean(r.get("Disease_Name", "")),
            ),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(
                drug_id,
                clean(r.get("Drug_Name", "")),
            ),
            "Evidence_Source_Class": subtype,
            "Evidence_Type": "pair_specific_indication_report",
            "Evidence_Source": clean(r["Source"]),
            "Evidence_Origin": clean(r["Origin"]),
            "Provider": clean(r["Provider"]),
            "Source_Record_ID": clean(
                r.get("OpenTargets_Clinical_Report_ID", "")
            ),
            "Clinical_Report_ID": clinical_report_id,
            "NCT_IDs": clean(r["NCT_IDs"]),
            "Clinical_Stage": clean(r["Clinical_Stage"]),
            "Phase_From_Source": clean(r["Phase_From_Source"]),
            "Trial_Phase": clean(r["Trial_Phase"]),
            "Trial_Overall_Status":
                clean(r["Trial_Overall_Status"]),
            "Legacy_Maximum_Development_Phase": "",
            "Title": clean(r["Title"]),
            "URL": clean(r["URL"]),
            "References": "",
            "Source_Curation_Status":
                "pair_specific_exact_disease_and_drug_mapping",
            "Pair_Specificity":
                "single_disease_single_drug_indication_report",
            "Interpretation":
                (
                    "Pair-specific source-level indication evidence. "
                    "Clinical-trial investigation is not interpreted as "
                    "regulatory approval unless label/regulatory evidence "
                    "is separately present."
                ),
        })

    evidence = pd.DataFrame(evidence_rows)

    # -------------------------------------------------------------
    # Build canonical association table
    # -------------------------------------------------------------
    association_rows = []

    for did, drug_id in sorted(canonical_pairs):
        ev = evidence[
            (evidence["DiseaseID"] == did)
            & (evidence["Drug_ID"] == drug_id)
        ].copy()

        classes = set(
            clean(x)
            for x in ev["Evidence_Source_Class"]
            if clean(x)
        )

        has_legacy = "legacy_curated" in classes
        has_trial = "clinical_trial_investigation" in classes
        has_label = "drug_label_indication" in classes
        has_regulatory = "regulatory_indication" in classes
        has_curated = "curated_indication" in classes

        ncts = []
        for x in ev["NCT_IDs"]:
            ncts.extend(split_pipe(x))
        ncts = uniq(ncts)

        if has_legacy and len(classes - {"legacy_curated"}) > 0:
            provenance = "legacy_plus_pair_specific_source_evidence"
        elif has_legacy:
            provenance = "legacy_only_direct_evidence"
        else:
            provenance = "pair_specific_source_evidence_without_legacy"

        association_rows.append({
            "Disease_Drug_Association_ID":
                stable_id("ODDB-DDA", did, drug_id),
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, ""),
            "Relationship_Type": "direct_disease_drug_evidence",
            "Evidence_Record_Count": len(ev),
            "Evidence_Source_Classes":
                uniq_join(ev["Evidence_Source_Class"]),
            "Evidence_Sources":
                uniq_join(ev["Evidence_Source"]),
            "Has_Legacy_Evidence": "Yes" if has_legacy else "No",
            "Has_ClinicalTrial_Evidence":
                "Yes" if has_trial else "No",
            "Has_DrugLabel_Evidence":
                "Yes" if has_label else "No",
            "Has_Regulatory_Evidence":
                "Yes" if has_regulatory else "No",
            "Has_Curated_Indication_Evidence":
                "Yes" if has_curated else "No",
            "NCT_ID_Count": len(ncts),
            "NCT_IDs": " | ".join(ncts),
            "Observed_Clinical_Stages":
                uniq_join(ev["Clinical_Stage"]),
            "Observed_Trial_Phases":
                uniq_join(ev["Trial_Phase"]),
            "Observed_Trial_Statuses":
                uniq_join(ev["Trial_Overall_Status"]),
            "Legacy_Development_Phases":
                uniq_join(
                    ev.loc[
                        ev["Evidence_Source_Class"] == "legacy_curated",
                        "Phase_From_Source",
                    ]
                ),
            "Evidence_Provenance_Class": provenance,
            "Curation_Status":
                "canonical_pair_supported_by_source_level_direct_evidence",
            "Interpretation":
                (
                    "Canonical disease-drug pair supported by legacy "
                    "curation and/or pair-specific source-level indication "
                    "evidence. Clinical-trial evidence indicates "
                    "investigation, not automatically approval."
                ),
        })

    association = pd.DataFrame(association_rows)

    # -------------------------------------------------------------
    # Preserve aggregated Open Targets clinical_target as context
    # -------------------------------------------------------------
    context_rows = []

    for _, r in aggregate_ot.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        key = (did, drug_id)

        row = r.to_dict()

        row["Pair_Specific_Source_Report_Support"] = (
            "Yes" if key in report_pairs else "No"
        )
        row["Legacy_ODDB_Support"] = (
            "Yes" if key in legacy_pairs else "No"
        )
        row["Included_In_Final_Canonical_DDA"] = (
            "Yes" if key in canonical_pairs else "No"
        )

        if key in report_pairs:
            context_class = (
                "aggregate_context_corroborated_by_pair_specific_report"
            )
        elif key in legacy_pairs:
            context_class = (
                "aggregate_context_with_independent_legacy_support"
            )
        else:
            context_class = (
                "aggregate_context_only_not_direct_pair_evidence"
            )

        row["Aggregate_Context_Class"] = context_class
        row["Interpretation_Final"] = (
            "Open Targets clinical_target aggregate context is retained "
            "for provenance/discovery. It is not independently used to "
            "assert a canonical direct disease-drug relationship."
        )

        context_rows.append(row)

    aggregate_context = pd.DataFrame(context_rows)

    demoted = aggregate_context[
        aggregate_context[
            "Aggregate_Context_Class"
        ].eq("aggregate_context_only_not_direct_pair_evidence")
    ].copy()

    # -------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------
    problems = []

    # Input FKs
    for table_name, df in [
        ("legacy", legacy),
        ("pair reports", pair_reports),
        ("aggregate context", aggregate_ot),
    ]:
        if (~df["DiseaseID"].isin(valid_diseases)).any():
            problems.append(
                f"{table_name}: invalid DiseaseID foreign key"
            )

        if (~df["Drug_ID"].isin(valid_drugs)).any():
            problems.append(
                f"{table_name}: invalid Drug_ID foreign key"
            )

    if association[
        "Disease_Drug_Association_ID"
    ].duplicated().any():
        problems.append(
            "duplicate canonical Disease_Drug_Association_ID"
        )

    if association.duplicated(
        ["DiseaseID", "Drug_ID"]
    ).any():
        problems.append(
            "duplicate canonical DiseaseID + Drug_ID pair"
        )

    if evidence[
        "Disease_Drug_Evidence_ID"
    ].duplicated().any():
        problems.append(
            "duplicate Disease_Drug_Evidence_ID"
        )

    valid_assoc_ids = set(
        association["Disease_Drug_Association_ID"]
    )

    if (~evidence[
        "Disease_Drug_Association_ID"
    ].isin(valid_assoc_ids)).any():
        problems.append(
            "evidence contains invalid canonical association FK"
        )

    calculated_expected = (
        len(legacy_pairs)
        + len(report_pairs)
        - len(shared_pairs)
    )

    if len(association) != calculated_expected:
        problems.append(
            "canonical association count does not equal "
            "legacy U pair-specific union"
        )

    expected_demoted = aggregate_pairs - canonical_pairs

    demoted_pairs = set(
        zip(demoted["DiseaseID"], demoted["Drug_ID"])
    )

    if demoted_pairs != expected_demoted:
        problems.append(
            "demoted aggregate-only pair set differs from expected set"
        )

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    summary = pd.DataFrame([
        ["Legacy_direct_pairs", len(legacy_pairs)],
        ["Pair_specific_source_report_pairs", len(report_pairs)],
        ["Legacy_and_pair_specific_shared_pairs", len(shared_pairs)],
        ["Final_canonical_direct_pairs", len(association)],
        ["Final_canonical_unique_diseases",
         association["DiseaseID"].nunique()],
        ["Final_canonical_unique_drugs",
         association["Drug_ID"].nunique()],
        ["Source_specific_evidence_rows", len(evidence)],
        ["Legacy_evidence_rows",
         int(
             evidence["Evidence_Source_Class"]
             .eq("legacy_curated")
             .sum()
         )],
        ["Pair_specific_clinical_report_evidence_rows",
         int(
             evidence["Evidence_Type"]
             .eq("pair_specific_indication_report")
             .sum()
         )],
        ["Canonical_pairs_with_clinical_trial_evidence",
         int(
             association["Has_ClinicalTrial_Evidence"]
             .eq("Yes")
             .sum()
         )],
        ["Canonical_pairs_with_drug_label_evidence",
         int(
             association["Has_DrugLabel_Evidence"]
             .eq("Yes")
             .sum()
         )],
        ["Canonical_pairs_with_regulatory_evidence",
         int(
             association["Has_Regulatory_Evidence"]
             .eq("Yes")
             .sum()
         )],
        ["Canonical_pairs_with_curated_indication_evidence",
         int(
             association[
                 "Has_Curated_Indication_Evidence"
             ].eq("Yes")
             .sum()
         )],
        ["Aggregate_OpenTargets_context_rows",
         len(aggregate_context)],
        ["Aggregate_context_rows_corroborated_by_pair_specific",
         int(
             aggregate_context[
                 "Pair_Specific_Source_Report_Support"
             ].eq("Yes").sum()
         )],
        ["Aggregate_context_only_pairs_demoted",
         len(demoted)],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # -------------------------------------------------------------
    # Write
    # -------------------------------------------------------------
    association.to_csv(
        args.association_output,
        sep="\t",
        index=False,
    )

    evidence.to_csv(
        args.evidence_output,
        sep="\t",
        index=False,
    )

    aggregate_context.to_csv(
        args.aggregate_context_output,
        sep="\t",
        index=False,
    )

    demoted.to_csv(
        args.demoted_output,
        sep="\t",
        index=False,
    )

    summary.to_csv(
        report_dir / "final_disease_drug_build_summary.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        report_dir / "final_disease_drug_build_problems.tsv",
        sep="\t",
        index=False,
    )

    # Additional useful partitions
    association[
        association["Has_ClinicalTrial_Evidence"].eq("Yes")
    ].to_csv(
        report_dir / "canonical_pairs_with_clinical_trial_evidence.tsv",
        sep="\t",
        index=False,
    )

    association[
        association["Has_DrugLabel_Evidence"].eq("Yes")
        | association["Has_Regulatory_Evidence"].eq("Yes")
    ].to_csv(
        report_dir / "canonical_pairs_with_label_or_regulatory_evidence.tsv",
        sep="\t",
        index=False,
    )

    association[
        association["Evidence_Provenance_Class"].eq(
            "legacy_only_direct_evidence"
        )
    ].to_csv(
        report_dir / "canonical_pairs_legacy_only.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB FINAL SOURCE-LEVEL DISEASE–DRUG LAYER BUILD")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nCanonical associations:", args.association_output)
    print("Source-specific evidence:", args.evidence_output)
    print("Aggregate clinical context:", args.aggregate_context_output)
    print("Demoted aggregate-only context:", args.demoted_output)
    print("Reports:", report_dir)

    print(
        "\nOpen Targets clinical_target aggregate context was preserved "
        "but was not independently used to create direct canonical pairs."
    )


if __name__ == "__main__":
    main()
