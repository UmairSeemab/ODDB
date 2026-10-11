#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd

def clean(x):
    return str(x or "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exact", required=True,
                    help="retnet_triage/.../exact_disease_matches.tsv")
    ap.add_argument("--details", required=True,
                    help="RetNet structured-all details TSV")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    exact = pd.read_csv(args.exact, sep="\t", dtype=str).fillna("")
    details = pd.read_csv(args.details, sep="\t", dtype=str).fillna("")

    required = {
        "Approved_GeneSymbol",
        "HGNC_ID",
        "Suggested_ODDB_DiseaseID",
        "Suggested_ODDB_Disease",
        "Detailed_Phenotype_Raw",
        "Inheritance",
        "Detailed_ODDB_Pair_Status",
        "Promotion_Eligibility",
    }
    missing = required - set(exact.columns)
    if missing:
        raise SystemExit(f"Exact-match file missing columns: {sorted(missing)}")

    q = exact[
        exact["Promotion_Eligibility"].eq("verify_before_add")
    ].copy()

    # One structured RetNet detail record per primary symbol.
    detail_cols = [
        "RetNet_Primary_Symbol",
        "Location",
        "How_Identified_Comments_Text",
        "References_Text",
        "References_Links",
        "Symbols_OMIM_Links",
        "Diseases_Protein_Links",
    ]
    d = details[[c for c in detail_cols if c in details.columns]].copy()
    d["RetNet_Primary_Symbol"] = (
        d["RetNet_Primary_Symbol"].astype(str).str.strip().str.upper()
    )
    d = d.drop_duplicates(subset=["RetNet_Primary_Symbol"], keep="first")

    q["_join_symbol"] = q["Approved_GeneSymbol"].astype(str).str.strip().str.upper()
    q = q.merge(
        d,
        how="left",
        left_on="_join_symbol",
        right_on="RetNet_Primary_Symbol",
        suffixes=("", "_RetNetDetail")
    ).drop(columns=["_join_symbol"])

    # Preserve discovery provenance, but clearly separate it from independent verification.
    q["Verification_Target"] = q["Detailed_ODDB_Pair_Status"].map({
        "new_association_existing_gene": "New disease association for existing ODDB gene",
        "new_gene_for_oddb": "New ODDB gene + disease association",
    }).fillna("Review")

    # Blank curator/evidence fields to be filled only from sources independent of RetNet.
    q["Primary_Reference_PMID_Verified"] = ""
    q["Primary_Reference_DOI_Verified"] = ""
    q["Primary_Reference_Support"] = ""
    q["ClinGen_Gene_Disease_Validity"] = ""
    q["ClinGen_Evidence_URL"] = ""
    q["ClinVar_Support"] = ""
    q["ClinVar_Evidence_URL"] = ""
    q["Independent_Verification_Status"] = "pending"
    q["Curator_Decision"] = "pending"
    q["Curator_Notes_Verification"] = ""

    preferred = [
        "Verification_Target",
        "Approved_GeneSymbol",
        "HGNC_ID",
        "Suggested_ODDB_DiseaseID",
        "Suggested_ODDB_Disease",
        "Detailed_Phenotype_Raw",
        "Inheritance",
        "Detailed_ODDB_Pair_Status",
        "Location",
        "How_Identified_Comments_Text",
        "References_Text",
        "References_Links",
        "Symbols_OMIM_Links",
        "Diseases_Protein_Links",
        "Primary_Reference_PMID_Verified",
        "Primary_Reference_DOI_Verified",
        "Primary_Reference_Support",
        "ClinGen_Gene_Disease_Validity",
        "ClinGen_Evidence_URL",
        "ClinVar_Support",
        "ClinVar_Evidence_URL",
        "Independent_Verification_Status",
        "Curator_Decision",
        "Curator_Notes_Verification",
    ]
    rest = [c for c in q.columns if c not in preferred]
    q = q[[c for c in preferred if c in q.columns] + rest]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    q.to_csv(args.output, sep="\t", index=False)

    print(f"Verification rows: {len(q)}")
    print(
        "Unique HGNC genes:",
        q["HGNC_ID"].replace("", pd.NA).dropna().nunique()
    )
    print("\nBy verification target:")
    print(q["Verification_Target"].value_counts().to_string())
    print(f"\nWritten: {args.output}")
    print("All independent verification fields remain pending/blank.")
    print("RetNet references are discovery provenance only, not verification.")

if __name__ == "__main__":
    main()
