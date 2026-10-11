#!/usr/bin/env python3
"""
Resolve a confirmed duplicate ODDB disease concept while preserving legacy IDs.

Default rule:
  ODDB-76  FUNDUS FLAVIMACULATUS
      -> canonical ODDB-225 STARGARDT DISEASE

Outputs:
  1) canonical Disease master (duplicate concept removed)
  2) Disease alias/redirect table preserving the retired DiseaseID
  3) canonical Disease_Gene_Association table with DiseaseIDs remapped
  4) QC report for any relationships collapsed by the merge

The ClinVar Disease_Variant_Association table should be REBUILT from the
canonical Disease master rather than remapped, so ambiguous identifier mapping
is recalculated correctly.
"""

import argparse
import hashlib
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def uniq_join(values, sep=" | "):
    out, seen = [], set()
    for x in values:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return sep.join(out)


def dga_id(disease_id, hgnc_id, inheritance):
    key = f"{clean(disease_id)}|{clean(hgnc_id)}|{clean(inheritance).lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-DGA-{digest}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--dga", required=True)
    ap.add_argument("--disease-output", required=True)
    ap.add_argument("--alias-output", required=True)
    ap.add_argument("--dga-output", required=True)
    ap.add_argument("--report-dir", required=True)

    ap.add_argument("--retired-id", default="ODDB-76")
    ap.add_argument("--canonical-id", default="ODDB-225")
    ap.add_argument("--retired-name", default="FUNDUS FLAVIMACULATUS")
    ap.add_argument("--canonical-name", default="STARGARDT DISEASE")
    args = ap.parse_args()

    disease = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")
    dga = pd.read_csv(args.dga, sep="\t", dtype=str).fillna("")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    for did in [args.retired_id, args.canonical_id]:
        if did not in set(disease["DiseaseID"]):
            raise SystemExit(f"DiseaseID not found in disease master: {did}")

    retired = disease.loc[disease["DiseaseID"] == args.retired_id].iloc[0]
    canon_idx = disease.index[disease["DiseaseID"] == args.canonical_id][0]

    # -------------------------------------------------------
    # Build alias/redirect table
    # -------------------------------------------------------
    alias = pd.DataFrame([{
        "Alias_DiseaseID": args.retired_id,
        "Alias_Name": clean(retired.get("Disease_Name")) or args.retired_name,
        "Canonical_DiseaseID": args.canonical_id,
        "Canonical_Disease_Name": args.canonical_name,
        "Relationship": "exact_synonym_of",
        "Status": "retired_alias",
        "Reason":
            "Same disease concept according to authoritative disease identifiers; "
            "Fundus flavimaculatus is retained as a historical/clinical synonym "
            "of Stargardt disease.",
        "MONDO_ID": clean(retired.get("MONDO_ID")),
        "Orphanet_ID": clean(retired.get("Orphanet_ID")),
        "MedGen_UMLS_CUI": clean(retired.get("MedGen_UMLS_CUI")),
    }])

    # -------------------------------------------------------
    # Update canonical Disease row
    # -------------------------------------------------------
    synonym_values = []
    synonym_values.extend(clean(disease.at[canon_idx, "Synonyms"]).split(" | "))
    synonym_values.append(clean(retired.get("Disease_Name")))
    synonym_values.extend(clean(retired.get("Synonyms", "")).split(" | "))

    disease.at[canon_idx, "Synonyms"] = uniq_join(synonym_values)

    # Preserve retired legacy name as alternative name too.
    if "Alternative_Disease_Names_From_Legacy" in disease.columns:
        alts = clean(
            disease.at[canon_idx, "Alternative_Disease_Names_From_Legacy"]
        ).split(" | ")
        alts.append(clean(retired.get("Disease_Name")))
        disease.at[
            canon_idx, "Alternative_Disease_Names_From_Legacy"
        ] = uniq_join(alts)

    # Keep canonical identifiers. If any are missing, fill from retired row.
    for col in [
        "MONDO_ID", "OMIM_ID", "Orphanet_ID", "MedGen_UMLS_CUI",
        "MONDO_Preferred_Label"
    ]:
        if col in disease.columns:
            if not clean(disease.at[canon_idx, col]):
                disease.at[canon_idx, col] = clean(retired.get(col, ""))

    # Remove the duplicate disease concept from canonical master.
    disease_canonical = disease[
        disease["DiseaseID"] != args.retired_id
    ].copy()

    # -------------------------------------------------------
    # Remap Disease-Gene associations
    # -------------------------------------------------------
    dga2 = dga.copy()
    affected_before = int((dga2["DiseaseID"] == args.retired_id).sum())

    dga2.loc[
        dga2["DiseaseID"] == args.retired_id, "DiseaseID"
    ] = args.canonical_id
    dga2.loc[
        dga2["DiseaseID"] == args.canonical_id, "Disease"
    ] = args.canonical_name

    key = ["DiseaseID", "HGNC_ID", "Inheritance"]

    dup_mask = dga2.duplicated(key, keep=False)
    dup_before_collapse = dga2.loc[dup_mask].copy()
    dup_before_collapse.to_csv(
        report_dir / "dga_duplicates_created_by_disease_merge.tsv",
        sep="\t",
        index=False
    )

    # Merge duplicate association rows conservatively, preserving all distinct
    # textual provenance/evidence values across duplicate records.
    merged_rows = []
    for _, group in dga2.groupby(key, dropna=False, sort=False):
        row = group.iloc[0].copy()

        for col in dga2.columns:
            if col in key or col == "Association_ID":
                continue
            values = [clean(x) for x in group[col] if clean(x)]
            if len(set(values)) > 1:
                row[col] = uniq_join(values)
            elif values:
                row[col] = values[0]
            else:
                row[col] = ""

        row["Association_ID"] = dga_id(
            row["DiseaseID"], row["HGNC_ID"], row["Inheritance"]
        )
        merged_rows.append(row)

    dga_canonical = pd.DataFrame(merged_rows, columns=dga2.columns)

    # Recalculate disease gene counts in canonical Disease master.
    counts = (
        dga_canonical.groupby("DiseaseID")
        .agg(
            Gene_Association_Count=("Association_ID", "nunique"),
            Unique_Gene_Count=("HGNC_ID", "nunique"),
        )
        .reset_index()
    )

    for col in ["Gene_Association_Count", "Unique_Gene_Count"]:
        if col in disease_canonical.columns:
            disease_canonical = disease_canonical.drop(columns=[col])

    disease_canonical = disease_canonical.merge(
        counts, how="left", on="DiseaseID"
    )
    disease_canonical["Gene_Association_Count"] = (
        disease_canonical["Gene_Association_Count"].fillna(0).astype(int)
    )
    disease_canonical["Unique_Gene_Count"] = (
        disease_canonical["Unique_Gene_Count"].fillna(0).astype(int)
    )

    if "Has_Gene_Association" in disease_canonical.columns:
        disease_canonical["Has_Gene_Association"] = (
            disease_canonical["Gene_Association_Count"]
            .map(lambda n: "Yes" if n > 0 else "No")
        )

    # -------------------------------------------------------
    # Validation
    # -------------------------------------------------------
    dga_dup_after = dga_canonical.duplicated(key, keep=False).sum()
    id_dup_after = dga_canonical["Association_ID"].duplicated(keep=False).sum()

    report = pd.DataFrame([
        ["Disease_rows_before", len(disease)],
        ["Disease_rows_after", len(disease_canonical)],
        ["Retired_DiseaseID", args.retired_id],
        ["Canonical_DiseaseID", args.canonical_id],
        ["DGA_rows_before", len(dga)],
        ["DGA_rows_using_retired_ID_before", affected_before],
        ["DGA_duplicate_rows_created_by_merge", len(dup_before_collapse)],
        ["DGA_rows_after", len(dga_canonical)],
        ["DGA_duplicate_keys_after", int(dga_dup_after)],
        ["DGA_duplicate_Association_IDs_after", int(id_dup_after)],
    ], columns=["Metric", "Value"])

    Path(args.disease_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.alias_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.dga_output).parent.mkdir(parents=True, exist_ok=True)

    disease_canonical.sort_values("DiseaseID").to_csv(
        args.disease_output, sep="\t", index=False
    )
    alias.to_csv(args.alias_output, sep="\t", index=False)
    dga_canonical.sort_values(
        ["DiseaseID", "GeneSymbol", "Inheritance"]
    ).to_csv(
        args.dga_output, sep="\t", index=False
    )
    report.to_csv(
        report_dir / "disease_alias_resolution_summary.tsv",
        sep="\t",
        index=False
    )

    print("ODDB DISEASE ALIAS RESOLUTION")
    print(report.to_string(index=False))
    print(f"\nCanonical disease master: {args.disease_output}")
    print(f"Disease alias table: {args.alias_output}")
    print(f"Canonical disease-gene table: {args.dga_output}")

    if dga_dup_after == 0 and id_dup_after == 0:
        print("\nALIAS RESOLUTION VALIDATION PASSED.")
    else:
        print("\nALIAS RESOLUTION NEEDS REVIEW.")


if __name__ == "__main__":
    main()
