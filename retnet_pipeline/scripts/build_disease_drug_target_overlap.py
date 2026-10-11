#!/usr/bin/env python3
"""
Build ODDB v1 Disease–Drug Target Overlap discovery layer.

This is a COMPUTED / DISCOVERY layer.

It joins:
    Disease_Gene_Association_v1_final
        ×
    Drug_Target_Association_v1

through HGNC_ID, and then checks whether the same DiseaseID + Drug_ID
already has direct disease-drug evidence in:
    Disease_Drug_Association_v1_normalized

IMPORTANT:
- Target overlap is NOT therapeutic evidence.
- A drug targeting a disease-associated gene does NOT imply that the drug
  treats the disease.
- Existing Disease_Drug_Association records remain the direct therapeutic
  evidence layer.

Outputs
-------
1. Disease_Drug_Target_Overlap_v1
   one row per Disease + Drug + Target Gene mechanistic path

2. Disease_Drug_Target_Overlap_Summary_v1
   one row per Disease + Drug

3. Disease_Drug_Direct_Evidence_Without_Target_Overlap
   legacy/direct disease-drug records with no overlap to an ODDB disease gene

4. QC summary
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
    out = []
    seen = set()
    for value in values:
        value = clean(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return " | ".join(out)


def find_col(df, candidates, required=True):
    norm = {
        "".join(ch.lower() for ch in c if ch.isalnum()): c
        for c in df.columns
    }

    for candidate in candidates:
        key = "".join(
            ch.lower() for ch in candidate if ch.isalnum()
        )
        if key in norm:
            return norm[key]

    if required:
        raise SystemExit(
            f"Required column not found. Tried {candidates}. "
            f"Available columns: {list(df.columns)}"
        )

    return None


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--dga", required=True)
    ap.add_argument("--dta", required=True)
    ap.add_argument("--dda", required=True)
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--diseases", required=True)

    ap.add_argument("--path-output", required=True)
    ap.add_argument("--summary-output", required=True)
    ap.add_argument("--direct-without-overlap-output", required=True)
    ap.add_argument("--report-dir", required=True)

    args = ap.parse_args()

    dga = pd.read_csv(args.dga, sep="\t", dtype=str).fillna("")
    dta = pd.read_csv(args.dta, sep="\t", dtype=str).fillna("")
    dda = pd.read_csv(args.dda, sep="\t", dtype=str).fillna("")
    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    diseases = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")

    # -------------------------------------------------------------
    # Required columns
    # -------------------------------------------------------------
    dga_required = [
        "Association_ID",
        "DiseaseID",
        "HGNC_ID",
        "Inheritance",
    ]
    dta_required = [
        "Drug_Target_Association_ID",
        "Drug_ID",
        "HGNC_ID",
        "GeneSymbol",
        "Ensembl_Gene_ID",
        "Mechanism_of_Action",
        "Action_Type",
        "Target_Type",
    ]
    dda_required = [
        "Disease_Drug_Association_ID",
        "DiseaseID",
        "Drug_ID",
    ]

    for table_name, df, required in [
        ("DGA", dga, dga_required),
        ("DTA", dta, dta_required),
        ("DDA", dda, dda_required),
    ]:
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise SystemExit(
                f"{table_name} missing required columns: {missing}"
            )

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

    # Optional DDA fields
    dda_phase_col = find_col(
        dda,
        ["Observed_Development_Phases", "Maximum_Observed_Phase", "Phase"],
        required=False,
    )
    dda_status_col = find_col(
        dda,
        ["Curation_Status", "Relationship_Type"],
        required=False,
    )

    # -------------------------------------------------------------
    # Canonical FK sets
    # -------------------------------------------------------------
    disease_ids = set(diseases["DiseaseID"])
    drug_ids = set(drugs["Drug_ID"])

    problems = []

    if (~dga["DiseaseID"].isin(disease_ids)).any():
        problems.append("DGA contains invalid DiseaseID foreign keys")

    if (~dta["Drug_ID"].isin(drug_ids)).any():
        problems.append("DTA contains invalid Drug_ID foreign keys")

    if (~dda["DiseaseID"].isin(disease_ids)).any():
        problems.append("DDA contains invalid DiseaseID foreign keys")

    if (~dda["Drug_ID"].isin(drug_ids)).any():
        problems.append("DDA contains invalid Drug_ID foreign keys")

    # -------------------------------------------------------------
    # Direct disease-drug lookup
    # -------------------------------------------------------------
    direct_lookup = {}

    for (did, drug_id), g in dda.groupby(["DiseaseID", "Drug_ID"]):
        direct_lookup[(did, drug_id)] = {
            "Association_IDs": uniq_join(
                g["Disease_Drug_Association_ID"]
            ),
            "Phases": (
                uniq_join(g[dda_phase_col])
                if dda_phase_col else ""
            ),
            "Statuses": (
                uniq_join(g[dda_status_col])
                if dda_status_col else ""
            ),
        }

    # -------------------------------------------------------------
    # Join Disease-Gene to Drug-Target through HGNC_ID
    # -------------------------------------------------------------
    merged = dga.merge(
        dta,
        how="inner",
        on="HGNC_ID",
        suffixes=("_DGA", "_DTA"),
    )

    path_rows = []

    for _, r in merged.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])
        hgnc = clean(r["HGNC_ID"])

        direct = direct_lookup.get((did, drug_id))
        has_direct = direct is not None

        path_rows.append({
            "Disease_Drug_Target_Overlap_ID": stable_id(
                "ODDB-DDTO",
                did,
                drug_id,
                hgnc,
                clean(r["Drug_Target_Association_ID"]),
            ),
            "DiseaseID": did,
            "Disease_Name": disease_name_map.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name_map.get(drug_id, ""),
            "HGNC_ID": hgnc,
            "GeneSymbol": clean(r.get("GeneSymbol", "")),
            "Ensembl_Gene_ID": clean(r.get("Ensembl_Gene_ID", "")),
            "Disease_Gene_Association_ID":
                clean(r.get("Association_ID", "")),
            "Inheritance": clean(r.get("Inheritance", "")),
            "Drug_Target_Association_ID":
                clean(r.get("Drug_Target_Association_ID", "")),
            "Action_Type": clean(r.get("Action_Type", "")),
            "Mechanism_of_Action":
                clean(r.get("Mechanism_of_Action", "")),
            "Target_Type": clean(r.get("Target_Type", "")),
            "Direct_Disease_Drug_Evidence":
                "Yes" if has_direct else "No",
            "Disease_Drug_Association_IDs":
                direct["Association_IDs"] if direct else "",
            "Direct_Disease_Drug_Phases":
                direct["Phases"] if direct else "",
            "Direct_Disease_Drug_Status":
                direct["Statuses"] if direct else "",
            "Overlap_Class":
                (
                    "target_overlap_plus_direct_disease_drug_evidence"
                    if has_direct
                    else "target_overlap_only"
                ),
            "Interpretation":
                (
                    "Drug targets an ODDB disease-associated gene and ODDB "
                    "also contains direct disease-drug evidence."
                    if has_direct
                    else
                    "Drug targets an ODDB disease-associated gene. "
                    "This target overlap is a discovery connection only and "
                    "does not establish therapeutic efficacy for the disease."
                ),
        })

    path = pd.DataFrame(path_rows)

    if len(path):
        # Multiple DGA records can sometimes produce the same mechanistic path.
        path = (
            path.sort_values("Disease_Drug_Target_Overlap_ID")
            .drop_duplicates(
                [
                    "DiseaseID",
                    "Drug_ID",
                    "HGNC_ID",
                    "Drug_Target_Association_ID",
                ],
                keep="first",
            )
            .reset_index(drop=True)
        )

    # -------------------------------------------------------------
    # Disease + Drug summary
    # -------------------------------------------------------------
    summary_rows = []

    if len(path):
        for (did, drug_id), g in path.groupby(
            ["DiseaseID", "Drug_ID"],
            sort=True,
        ):
            has_direct = (
                g["Direct_Disease_Drug_Evidence"]
                .eq("Yes")
                .any()
            )

            summary_rows.append({
                "Disease_Drug_Target_Summary_ID": stable_id(
                    "ODDB-DDTS",
                    did,
                    drug_id,
                ),
                "DiseaseID": did,
                "Disease_Name": disease_name_map.get(did, ""),
                "Drug_ID": drug_id,
                "Drug_Name": drug_name_map.get(drug_id, ""),
                "Target_Gene_Count": g["HGNC_ID"].nunique(),
                "Target_Genes": uniq_join(g["GeneSymbol"]),
                "Target_HGNC_IDs": uniq_join(g["HGNC_ID"]),
                "Action_Types": uniq_join(g["Action_Type"]),
                "Mechanisms_of_Action":
                    uniq_join(g["Mechanism_of_Action"]),
                "Target_Types": uniq_join(g["Target_Type"]),
                "Direct_Disease_Drug_Evidence":
                    "Yes" if has_direct else "No",
                "Disease_Drug_Association_IDs":
                    uniq_join(g["Disease_Drug_Association_IDs"]),
                "Direct_Disease_Drug_Phases":
                    uniq_join(g["Direct_Disease_Drug_Phases"]),
                "Overlap_Class":
                    (
                        "target_overlap_plus_direct_disease_drug_evidence"
                        if has_direct
                        else "target_overlap_only"
                    ),
                "Interpretation":
                    (
                        "Molecular target overlap is accompanied by direct "
                        "ODDB disease-drug evidence."
                        if has_direct
                        else
                        "Molecular target overlap only; not therapeutic "
                        "evidence and not an ODDB treatment assertion."
                    ),
            })

    summary = pd.DataFrame(summary_rows)

    # -------------------------------------------------------------
    # Direct disease-drug evidence that does NOT overlap an ODDB gene target
    # -------------------------------------------------------------
    overlap_pairs = set()

    if len(summary):
        overlap_pairs = set(
            zip(summary["DiseaseID"], summary["Drug_ID"])
        )

    direct_without_rows = []

    for _, r in dda.iterrows():
        pair = (clean(r["DiseaseID"]), clean(r["Drug_ID"]))

        if pair in overlap_pairs:
            continue

        row = r.to_dict()
        row["Disease_Name"] = disease_name_map.get(pair[0], "")
        row["Drug_Name_Canonical"] = drug_name_map.get(pair[1], "")
        row["Target_Overlap_Status"] = "no_ODDB_disease_gene_target_overlap"
        row["Interpretation"] = (
            "Direct disease-drug evidence exists in ODDB, but no "
            "Open Targets drug-target relationship was found for an "
            "ODDB gene associated with this disease."
        )
        direct_without_rows.append(row)

    direct_without = pd.DataFrame(direct_without_rows)

    # -------------------------------------------------------------
    # QC
    # -------------------------------------------------------------
    if len(path):
        if path["Disease_Drug_Target_Overlap_ID"].duplicated().any():
            problems.append("duplicate path overlap IDs")

        if (~path["DiseaseID"].isin(disease_ids)).any():
            problems.append("path overlap invalid DiseaseID FK")

        if (~path["Drug_ID"].isin(drug_ids)).any():
            problems.append("path overlap invalid Drug_ID FK")

    if len(summary):
        if summary["Disease_Drug_Target_Summary_ID"].duplicated().any():
            problems.append("duplicate summary overlap IDs")

        if summary.duplicated(["DiseaseID", "Drug_ID"]).any():
            problems.append("duplicate DiseaseID + Drug_ID summary pairs")

    direct_pairs = set(zip(dda["DiseaseID"], dda["Drug_ID"]))

    overlap_only_pairs = (
        int(
            summary["Direct_Disease_Drug_Evidence"]
            .eq("No")
            .sum()
        )
        if len(summary) else 0
    )

    direct_plus_overlap_pairs = (
        int(
            summary["Direct_Disease_Drug_Evidence"]
            .eq("Yes")
            .sum()
        )
        if len(summary) else 0
    )

    report = pd.DataFrame([
        ["Disease_Gene_Association_rows", len(dga)],
        ["Drug_Target_Association_rows", len(dta)],
        ["Direct_Disease_Drug_Association_rows", len(dda)],
        ["Mechanistic_overlap_path_rows", len(path)],
        ["Unique_disease_drug_overlap_pairs", len(summary)],
        ["Unique_diseases_with_target_overlap",
         summary["DiseaseID"].nunique() if len(summary) else 0],
        ["Unique_drugs_with_disease_target_overlap",
         summary["Drug_ID"].nunique() if len(summary) else 0],
        ["Unique_target_genes_in_overlap",
         path["HGNC_ID"].nunique() if len(path) else 0],
        ["Target_overlap_only_pairs", overlap_only_pairs],
        ["Target_overlap_plus_direct_evidence_pairs",
         direct_plus_overlap_pairs],
        ["Direct_disease_drug_pairs_total", len(direct_pairs)],
        ["Direct_disease_drug_rows_without_target_overlap",
         len(direct_without)],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # -------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------
    for output in [
        args.path_output,
        args.summary_output,
        args.direct_without_overlap_output,
    ]:
        Path(output).parent.mkdir(parents=True, exist_ok=True)

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    path.to_csv(
        args.path_output,
        sep="\t",
        index=False,
    )

    summary.to_csv(
        args.summary_output,
        sep="\t",
        index=False,
    )

    direct_without.to_csv(
        args.direct_without_overlap_output,
        sep="\t",
        index=False,
    )

    report.to_csv(
        report_dir / "disease_drug_target_overlap_summary.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame(
        {"Problem": problems}
    ).to_csv(
        report_dir / "disease_drug_target_overlap_problems.tsv",
        sep="\t",
        index=False,
    )

    if len(summary):
        (
            summary[
                summary["Direct_Disease_Drug_Evidence"] == "Yes"
            ]
            .to_csv(
                report_dir /
                "target_overlap_with_direct_disease_drug_evidence.tsv",
                sep="\t",
                index=False,
            )
        )

        (
            summary[
                summary["Direct_Disease_Drug_Evidence"] == "No"
            ]
            .to_csv(
                report_dir / "target_overlap_only.tsv",
                sep="\t",
                index=False,
            )
        )

    print("ODDB DISEASE–DRUG TARGET OVERLAP BUILD")
    print(report.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nPath-level overlap:", args.path_output)
    print("Disease-drug summary:", args.summary_output)
    print(
        "Direct disease-drug evidence without target overlap:",
        args.direct_without_overlap_output,
    )
    print("Reports:", report_dir)

    print(
        "\nIMPORTANT: target_overlap_only records are discovery connections, "
        "not therapeutic assertions."
    )


if __name__ == "__main__":
    main()
