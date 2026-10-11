#!/usr/bin/env python3
"""
Compare legacy ODDB disease-drug evidence with Open Targets disease-drug
clinical evidence and build a normalized canonical disease-drug layer.

Design
------
Disease_Drug_Association_v1
    One row per canonical DiseaseID + Drug_ID.

Disease_Drug_Evidence_v1
    One row per source-specific evidence record supporting a canonical
    disease-drug pair.

This avoids mixing source-specific concepts such as:
- legacy Phase
- Open Targets Maximum Clinical Stage

No fuzzy disease mapping is performed here. Inputs are assumed already curated.

Outputs
-------
1) Disease_Drug_Association_v1
2) Disease_Drug_Evidence_v1
3) source comparison table
4) summary / QC reports
"""

import argparse
import hashlib
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def uniq_join(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return " | ".join(out)


def find_col(df, candidates, required=False):
    norm = {
        "".join(ch.lower() for ch in c if ch.isalnum()): c
        for c in df.columns
    }
    for cand in candidates:
        key = "".join(ch.lower() for ch in cand if ch.isalnum())
        if key in norm:
            return norm[key]
    if required:
        raise SystemExit(
            f"Required column not found among {candidates}. "
            f"Available: {list(df.columns)}"
        )
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy-dda", required=True)
    ap.add_argument("--opentargets-evidence", required=True)
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--association-output", required=True)
    ap.add_argument("--evidence-output", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    legacy = pd.read_csv(
        args.legacy_dda, sep="\t", dtype=str
    ).fillna("")
    ot = pd.read_csv(
        args.opentargets_evidence, sep="\t", dtype=str
    ).fillna("")
    drugs = pd.read_csv(
        args.drugs, sep="\t", dtype=str
    ).fillna("")
    diseases = pd.read_csv(
        args.diseases, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.association_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.evidence_output).parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # Canonical names
    # -------------------------------------------------------------
    disease_name_col = find_col(
        diseases, ["Disease_Name", "Ocular.disease"], required=True
    )
    drug_name_col = find_col(
        drugs, ["Preferred_Name", "Drug_Name", "Name"], required=True
    )

    disease_name_map = dict(
        zip(diseases["DiseaseID"], diseases[disease_name_col])
    )
    drug_name_map = dict(
        zip(drugs["Drug_ID"], drugs[drug_name_col])
    )

    valid_disease_ids = set(diseases["DiseaseID"])
    valid_drug_ids = set(drugs["Drug_ID"])

    # -------------------------------------------------------------
    # Detect source-specific optional fields
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

    ot_stage_col = find_col(
        ot,
        ["Observed_Clinical_Stages", "Maximum_Clinical_Stage"],
        required=False,
    )
    ot_target_genes_col = find_col(
        ot,
        ["Target_Genes"],
        required=False,
    )
    ot_target_hgnc_col = find_col(
        ot,
        ["Target_HGNC_IDs"],
        required=False,
    )
    ot_ct_ids_col = find_col(
        ot,
        ["OpenTargets_Clinical_Target_IDs"],
        required=False,
    )
    ot_disease_ids_col = find_col(
        ot,
        ["Mapped_OpenTargets_Disease_IDs"],
        required=False,
    )
    ot_disease_names_col = find_col(
        ot,
        ["Mapped_OpenTargets_Disease_Names"],
        required=False,
    )
    ot_match_col = find_col(
        ot,
        ["Match_Methods"],
        required=False,
    )

    # -------------------------------------------------------------
    # QC input FKs
    # -------------------------------------------------------------
    problems = []

    for table_name, df in [
        ("legacy", legacy),
        ("OpenTargets", ot),
    ]:
        if (~df["DiseaseID"].isin(valid_disease_ids)).any():
            problems.append(
                f"{table_name}: invalid DiseaseID foreign key"
            )
        if (~df["Drug_ID"].isin(valid_drug_ids)).any():
            problems.append(
                f"{table_name}: invalid Drug_ID foreign key"
            )

    # -------------------------------------------------------------
    # Source pair sets
    # -------------------------------------------------------------
    legacy_pairs = set(zip(legacy["DiseaseID"], legacy["Drug_ID"]))
    ot_pairs = set(zip(ot["DiseaseID"], ot["Drug_ID"]))
    all_pairs = legacy_pairs | ot_pairs
    shared_pairs = legacy_pairs & ot_pairs

    # -------------------------------------------------------------
    # Evidence table
    # -------------------------------------------------------------
    evidence_rows = []

    # Legacy evidence
    for _, r in legacy.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        assoc_id = stable_id("ODDB-DDA", did, drug_id)

        source_record = clean(
            r.get("Disease_Drug_Association_ID", "")
        )

        evidence_rows.append({
            "Disease_Drug_Evidence_ID": stable_id(
                "ODDB-DDE",
                "legacy_oddb",
                source_record or assoc_id,
            ),
            "Disease_Drug_Association_ID": assoc_id,
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, clean(r.get("Drug_Name"))),
            "Evidence_Source": "ODDB_legacy",
            "Evidence_Source_Release": "legacy_normalized_2026-09-29",
            "Evidence_Type": "legacy_disease_drug_evidence",
            "Source_Record_ID": source_record,
            "Development_Phase":
                clean(r.get(legacy_phase_col, "")) if legacy_phase_col else "",
            "Maximum_Development_Phase":
                clean(r.get(legacy_max_phase_col, ""))
                if legacy_max_phase_col else "",
            "Clinical_Stage": "",
            "Target_Genes": "",
            "Target_HGNC_IDs": "",
            "Source_Disease_IDs": "",
            "Source_Disease_Names": "",
            "Source_Clinical_Target_IDs": "",
            "Source_Match_Method": "",
            "References":
                clean(r.get(legacy_refs_col, "")) if legacy_refs_col else "",
            "Source_Curation_Status":
                clean(r.get(legacy_status_col, "")) if legacy_status_col else "",
            "Interpretation":
                "Disease-specific therapeutic evidence retained from the "
                "normalized ODDB legacy layer."
        })

    # Open Targets evidence
    for _, r in ot.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        assoc_id = stable_id("ODDB-DDA", did, drug_id)

        source_record = clean(
            r.get("Disease_Drug_OpenTargets_Evidence_ID", "")
        )

        evidence_rows.append({
            "Disease_Drug_Evidence_ID": stable_id(
                "ODDB-DDE",
                "opentargets_26.09",
                source_record or assoc_id,
            ),
            "Disease_Drug_Association_ID": assoc_id,
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, clean(r.get("Drug_Name"))),
            "Evidence_Source": "Open_Targets",
            "Evidence_Source_Release": "26.09",
            "Evidence_Type":
                clean(r.get("Evidence_Type"))
                or "OpenTargets_clinical_target_context",
            "Source_Record_ID": source_record,
            "Development_Phase": "",
            "Maximum_Development_Phase": "",
            "Clinical_Stage":
                clean(r.get(ot_stage_col, "")) if ot_stage_col else "",
            "Target_Genes":
                clean(r.get(ot_target_genes_col, ""))
                if ot_target_genes_col else "",
            "Target_HGNC_IDs":
                clean(r.get(ot_target_hgnc_col, ""))
                if ot_target_hgnc_col else "",
            "Source_Disease_IDs":
                clean(r.get(ot_disease_ids_col, ""))
                if ot_disease_ids_col else "",
            "Source_Disease_Names":
                clean(r.get(ot_disease_names_col, ""))
                if ot_disease_names_col else "",
            "Source_Clinical_Target_IDs":
                clean(r.get(ot_ct_ids_col, ""))
                if ot_ct_ids_col else "",
            "Source_Match_Method":
                clean(r.get(ot_match_col, ""))
                if ot_match_col else "",
            "References": "",
            "Source_Curation_Status":
                clean(r.get("Curation_Status", "")),
            "Interpretation":
                "Open Targets disease-specific clinical target context mapped "
                "to an ODDB disease by exact identifier/name/alias evidence."
        })

    evidence = pd.DataFrame(evidence_rows)

    # -------------------------------------------------------------
    # Canonical association table: one Disease + Drug pair
    # -------------------------------------------------------------
    association_rows = []

    for did, drug_id in sorted(all_pairs):
        ev = evidence[
            (evidence["DiseaseID"] == did)
            & (evidence["Drug_ID"] == drug_id)
        ]

        sources = uniq_join(ev["Evidence_Source"])
        source_count = ev["Evidence_Source"].nunique()

        in_legacy = (did, drug_id) in legacy_pairs
        in_ot = (did, drug_id) in ot_pairs

        if in_legacy and in_ot:
            provenance_class = "multi_source_direct_evidence"
        elif in_legacy:
            provenance_class = "legacy_only_direct_evidence"
        else:
            provenance_class = "opentargets_only_direct_evidence"

        association_rows.append({
            "Disease_Drug_Association_ID":
                stable_id("ODDB-DDA", did, drug_id),
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, ""),
            "Relationship_Type": "direct_disease_drug_evidence",
            "Evidence_Source_Count": source_count,
            "Evidence_Sources": sources,
            "Evidence_Record_Count": len(ev),
            "Has_Legacy_ODDB_Evidence": "Yes" if in_legacy else "No",
            "Has_OpenTargets_Evidence": "Yes" if in_ot else "No",
            "Evidence_Provenance_Class": provenance_class,
            "Legacy_Development_Phases":
                uniq_join(
                    ev.loc[
                        ev["Evidence_Source"] == "ODDB_legacy",
                        "Development_Phase",
                    ]
                ),
            "OpenTargets_Clinical_Stages":
                uniq_join(
                    ev.loc[
                        ev["Evidence_Source"] == "Open_Targets",
                        "Clinical_Stage",
                    ]
                ),
            "Curation_Status":
                "canonical_direct_evidence_pair",
            "Interpretation":
                "Canonical disease-drug pair supported by one or more "
                "source-specific evidence records. Source-specific phase/"
                "stage semantics are retained in Disease_Drug_Evidence_v1."
        })

    association = pd.DataFrame(association_rows)

    # -------------------------------------------------------------
    # Source comparison report
    # -------------------------------------------------------------
    comparison_rows = []

    for did, drug_id in sorted(all_pairs):
        comparison_rows.append({
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, ""),
            "Legacy_ODDB": "Yes" if (did, drug_id) in legacy_pairs else "No",
            "Open_Targets": "Yes" if (did, drug_id) in ot_pairs else "No",
            "Source_Class": (
                "shared"
                if (did, drug_id) in shared_pairs
                else "legacy_only"
                if (did, drug_id) in legacy_pairs
                else "opentargets_only"
            ),
        })

    comparison = pd.DataFrame(comparison_rows)

    # -------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------
    if association["Disease_Drug_Association_ID"].duplicated().any():
        problems.append("duplicate canonical Disease_Drug_Association_ID")

    if association.duplicated(["DiseaseID", "Drug_ID"]).any():
        problems.append("duplicate canonical DiseaseID + Drug_ID pair")

    if evidence["Disease_Drug_Evidence_ID"].duplicated().any():
        problems.append("duplicate Disease_Drug_Evidence_ID")

    if (~evidence["Disease_Drug_Association_ID"].isin(
        set(association["Disease_Drug_Association_ID"])
    )).any():
        problems.append(
            "Disease_Drug_Evidence contains invalid association foreign key"
        )

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    summary = pd.DataFrame([
        ["Legacy_direct_pairs", len(legacy_pairs)],
        ["OpenTargets_direct_pairs", len(ot_pairs)],
        ["Shared_pairs_legacy_and_OpenTargets", len(shared_pairs)],
        ["Legacy_only_pairs", len(legacy_pairs - ot_pairs)],
        ["OpenTargets_only_pairs", len(ot_pairs - legacy_pairs)],
        ["Canonical_Disease_Drug_Association_rows", len(association)],
        ["Disease_Drug_Evidence_rows", len(evidence)],
        ["Canonical_unique_diseases", association["DiseaseID"].nunique()],
        ["Canonical_unique_drugs", association["Drug_ID"].nunique()],
        ["Multi_source_pairs",
         int(association["Evidence_Source_Count"].astype(int).gt(1).sum())],
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

    comparison.to_csv(
        outdir / "legacy_vs_opentargets_disease_drug_pairs.tsv",
        sep="\t",
        index=False,
    )

    comparison[
        comparison["Source_Class"] == "shared"
    ].to_csv(
        outdir / "shared_legacy_opentargets_pairs.tsv",
        sep="\t",
        index=False,
    )

    comparison[
        comparison["Source_Class"] == "legacy_only"
    ].to_csv(
        outdir / "legacy_only_pairs.tsv",
        sep="\t",
        index=False,
    )

    comparison[
        comparison["Source_Class"] == "opentargets_only"
    ].to_csv(
        outdir / "opentargets_only_pairs.tsv",
        sep="\t",
        index=False,
    )

    summary.to_csv(
        outdir / "canonical_disease_drug_build_summary.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        outdir / "canonical_disease_drug_build_problems.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB CANONICAL DISEASE–DRUG LAYER BUILD")
    print(summary.to_string(index=False))

    print("\nSource comparison:")
    print(
        comparison["Source_Class"]
        .value_counts()
        .rename_axis("Source_Class")
        .reset_index(name="Pairs")
        .to_string(index=False)
    )

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nCanonical association table:", args.association_output)
    print("Source-specific evidence table:", args.evidence_output)
    print("Reports:", outdir)

    print(
        "\nPhase/stage values remain source-specific and are not collapsed "
        "into one universal clinical-phase field."
    )


if __name__ == "__main__":
    main()
