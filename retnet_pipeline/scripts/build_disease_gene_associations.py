#!/usr/bin/env python3
import argparse
import hashlib
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def first_existing(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def stable_assoc_id(disease_id, hgnc_id, inheritance):
    key = f"{clean(disease_id)}|{clean(hgnc_id)}|{clean(inheritance).lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-DGA-{digest}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--oddb-hgnc",
        required=True,
        help="HGNC-normalized cleaned ODDB file"
    )
    ap.add_argument(
        "--verified",
        required=True,
        help="Verified RetNet associations ready for ODDB"
    )
    ap.add_argument(
        "--output",
        required=True,
        help="Output Disease_Gene_Association TSV"
    )
    ap.add_argument(
        "--new-only-output",
        required=False,
        help="Optional output containing only the newly verified RetNet additions"
    )
    args = ap.parse_args()

    oddb = pd.read_csv(args.oddb_hgnc, sep="\t", dtype=str).fillna("")
    verified = pd.read_csv(args.verified, sep="\t", dtype=str).fillna("")

    # ---------------------------------------------------------
    # 1. Prepare existing ODDB disease-gene associations
    # ---------------------------------------------------------
    disease_id_col = first_existing(
        oddb.columns,
        ["DiseaseID", "Disease_ID", "ODDB_DiseaseID"]
    )
    disease_col = first_existing(
        oddb.columns,
        ["Ocular.disease", "Disease", "ODDB_Disease"]
    )
    gene_col = first_existing(
        oddb.columns,
        ["Approved_GeneSymbol", "GeneSymbol", "Gene"]
    )
    hgnc_col = first_existing(
        oddb.columns,
        ["HGNC_ID", "HGNC.ID", "HGNC"]
    )
    inheritance_col = first_existing(
        oddb.columns,
        [
            "Inheritance",
            "Mode.of.Inheritance",
            "Mode_of_Inheritance",
            "Mode of Inheritance",
            "Inheritance_Mode",
        ]
    )

    required = {
        "DiseaseID": disease_id_col,
        "Disease": disease_col,
        "Gene": gene_col,
        "HGNC": hgnc_col,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise SystemExit(
            "Could not identify required ODDB columns: " + ", ".join(missing)
        )

    existing = oddb.copy()

    # Remove rows explicitly reclassified as non-gene entities.
    if "Genetic_Entity_Type" in existing.columns:
        entity = existing["Genetic_Entity_Type"].astype(str).str.strip().str.lower()
        existing = existing[entity.isin(["", "gene"])].copy()

    existing = pd.DataFrame({
        "DiseaseID": existing[disease_id_col].map(clean),
        "Disease": existing[disease_col].map(clean),
        "HGNC_ID": existing[hgnc_col].map(clean),
        "GeneSymbol": existing[gene_col].map(clean),
        "Inheritance": (
            existing[inheritance_col].map(clean)
            if inheritance_col
            else ""
        ),
    })

    # Only molecular gene associations with a stable disease and HGNC ID.
    existing = existing[
        (existing["DiseaseID"] != "")
        & (existing["HGNC_ID"] != "")
        & (existing["GeneSymbol"] != "")
    ].copy()

    existing["Evidence_Status"] = "legacy_unreviewed"
    existing["Evidence_Source"] = "ODDB legacy dataset"
    existing["Discovery_Source"] = ""
    existing["Discovery_URL"] = ""
    existing["Primary_Reference_PMID"] = ""
    existing["Primary_Reference_DOI"] = ""
    existing["ClinGen_Status"] = ""
    existing["ClinVar_Support"] = ""
    existing["Curator_Decision"] = "existing"
    existing["Curation_Status"] = "legacy_existing"
    existing["Curator_Notes"] = ""
    existing["Retrieved_Date"] = ""

    # Collapse duplicates caused by drug rows / variants / repeated legacy rows.
    existing = existing.drop_duplicates(
        subset=["DiseaseID", "HGNC_ID", "Inheritance"],
        keep="first"
    ).copy()

    # ---------------------------------------------------------
    # 2. Prepare newly verified RetNet-derived associations
    # ---------------------------------------------------------
    needed = [
        "Approved_GeneSymbol",
        "HGNC_ID",
        "Suggested_ODDB_DiseaseID",
        "Suggested_ODDB_Disease",
        "Inheritance",
        "Independent_Verification_Status",
        "Primary_Reference_PMID_Verified",
        "Primary_Reference_DOI_Verified",
        "Curator_Decision",
        "Curator_Notes_Verification",
    ]
    missing = [c for c in needed if c not in verified.columns]
    if missing:
        raise SystemExit(
            "Verified file is missing required columns: " + ", ".join(missing)
        )

    new = pd.DataFrame({
        "DiseaseID": verified["Suggested_ODDB_DiseaseID"].map(clean),
        "Disease": verified["Suggested_ODDB_Disease"].map(clean),
        "HGNC_ID": verified["HGNC_ID"].map(clean),
        "GeneSymbol": verified["Approved_GeneSymbol"].map(clean),
        "Inheritance": verified["Inheritance"].map(clean),
        "Evidence_Status": verified["Independent_Verification_Status"].map(clean),
        "Evidence_Source": "Independent literature/curated-resource verification",
        "Discovery_Source": (
            verified["Discovery_Source"].map(clean)
            if "Discovery_Source" in verified.columns
            else "RetNet"
        ),
        "Discovery_URL": (
            verified["Discovery_URL"].map(clean)
            if "Discovery_URL" in verified.columns
            else ""
        ),
        "Primary_Reference_PMID": verified["Primary_Reference_PMID_Verified"].map(clean),
        "Primary_Reference_DOI": verified["Primary_Reference_DOI_Verified"].map(clean),
        "ClinGen_Status": (
            verified["ClinGen_Status"].map(clean)
            if "ClinGen_Status" in verified.columns
            else ""
        ),
        "ClinVar_Support": (
            verified["ClinVar_Support"].map(clean)
            if "ClinVar_Support" in verified.columns
            else ""
        ),
        "Curator_Decision": verified["Curator_Decision"].map(clean),
        "Curation_Status": "verified_new",
        "Curator_Notes": verified["Curator_Notes_Verification"].map(clean),
        "Retrieved_Date": (
            verified["Retrieved_Date"].map(clean)
            if "Retrieved_Date" in verified.columns
            else ""
        ),
    })

    # Safety: main association table only receives approved records.
    new = new[
        new["Curator_Decision"].isin(["include", "include_with_note"])
    ].copy()

    new = new[
        (new["DiseaseID"] != "")
        & (new["HGNC_ID"] != "")
        & (new["GeneSymbol"] != "")
    ].copy()

    new = new.drop_duplicates(
        subset=["DiseaseID", "HGNC_ID", "Inheritance"],
        keep="first"
    ).copy()

    # ---------------------------------------------------------
    # 3. Detect duplicates against existing ODDB associations
    # ---------------------------------------------------------
    existing_keys = {
        (clean(r.DiseaseID), clean(r.HGNC_ID), clean(r.Inheritance))
        for r in existing.itertuples()
    }

    new["Already_In_Existing_ODDB"] = [
        "Yes" if (
            clean(r.DiseaseID),
            clean(r.HGNC_ID),
            clean(r.Inheritance)
        ) in existing_keys else "No"
        for r in new.itertuples()
    ]

    # The verification queue should contain new associations only.
    duplicate_new = new[new["Already_In_Existing_ODDB"] == "Yes"].copy()
    if len(duplicate_new):
        print("WARNING: verified additions already present in ODDB:")
        print(
            duplicate_new[
                ["DiseaseID", "Disease", "HGNC_ID", "GeneSymbol", "Inheritance"]
            ].to_string(index=False)
        )

    additions = new[new["Already_In_Existing_ODDB"] == "No"].copy()

    # ---------------------------------------------------------
    # 4. Combine into normalized association table
    # ---------------------------------------------------------
    existing["Association_Origin"] = "existing_oddb"
    additions["Association_Origin"] = "verified_retnet_discovery"

    if "Already_In_Existing_ODDB" in additions.columns:
        additions = additions.drop(columns=["Already_In_Existing_ODDB"])

    combined = pd.concat([existing, additions], ignore_index=True)

    combined["Association_ID"] = [
        stable_assoc_id(d, h, i)
        for d, h, i in zip(
            combined["DiseaseID"],
            combined["HGNC_ID"],
            combined["Inheritance"]
        )
    ]

    # Stable, readable ordering.
    cols = [
        "Association_ID",
        "DiseaseID",
        "Disease",
        "HGNC_ID",
        "GeneSymbol",
        "Inheritance",
        "Evidence_Status",
        "Evidence_Source",
        "Discovery_Source",
        "Discovery_URL",
        "Primary_Reference_PMID",
        "Primary_Reference_DOI",
        "ClinGen_Status",
        "ClinVar_Support",
        "Curator_Decision",
        "Curation_Status",
        "Association_Origin",
        "Curator_Notes",
        "Retrieved_Date",
    ]

    combined = combined[cols].sort_values(
        ["DiseaseID", "GeneSymbol", "Inheritance"]
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, sep="\t", index=False)

    if args.new_only_output:
        Path(args.new_only_output).parent.mkdir(parents=True, exist_ok=True)
        additions_out = combined[
            combined["Association_Origin"] == "verified_retnet_discovery"
        ].copy()
        additions_out.to_csv(args.new_only_output, sep="\t", index=False)

    print("DISEASE-GENE ASSOCIATION BUILD")
    print(f"Existing normalized ODDB associations: {len(existing)}")
    print(f"Verified RetNet-derived additions supplied: {len(new)}")
    print(f"Verified additions already present after normalization: {len(duplicate_new)}")
    print(f"Verified additions actually appended: {len(additions)}")
    print(f"Final association rows: {len(combined)}")
    print(f"Unique diseases: {combined['DiseaseID'].nunique()}")
    print(f"Unique HGNC genes: {combined['HGNC_ID'].nunique()}")
    print(f"\nWritten: {args.output}")
    if args.new_only_output:
        print(f"New additions only: {args.new_only_output}")
    print("\nNo legacy ODDB input file was modified.")


if __name__ == "__main__":
    main()
