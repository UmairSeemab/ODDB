#!/usr/bin/env python3
"""
Apply the high-confidence ODDB-101 legacy-name correction:

  LAND ISLAND EYE DISEASE
      -> ÅLAND ISLANDS EYE DISEASE

Preserve the old label as a disease alias and update disease display names
in the disease-gene association table. Also generate a focused review file
for ODDB-143 and ODDB-146 using the previous lost-link audit.

No automatic changes are made to:
  ODDB-143 OPTIC DISC ANOMALIES
  ODDB-146 OREGON EYE DISEASE
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def append_alias(existing, row):
    if existing is None or existing.empty:
        return pd.DataFrame([row])
    mask = (
        existing["Alias_DiseaseID"].astype(str).eq(row["Alias_DiseaseID"])
        if "Alias_DiseaseID" in existing.columns
        else pd.Series(False, index=existing.index)
    )
    if mask.any():
        for k, v in row.items():
            if k not in existing.columns:
                existing[k] = ""
            existing.loc[mask, k] = v
        return existing
    return pd.concat([existing, pd.DataFrame([row])], ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--dga", required=True)
    ap.add_argument("--lost-links", required=True)
    ap.add_argument("--disease-output", required=True)
    ap.add_argument("--alias-output", required=True)
    ap.add_argument("--dga-output", required=True)
    ap.add_argument("--review-output", required=True)
    args = ap.parse_args()

    disease = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")
    aliases = pd.read_csv(args.aliases, sep="\t", dtype=str).fillna("")
    dga = pd.read_csv(args.dga, sep="\t", dtype=str).fillna("")
    lost = pd.read_csv(args.lost_links, sep="\t", dtype=str).fillna("")

    did = "ODDB-101"
    old_name = "LAND ISLAND EYE DISEASE"
    new_name = "ÅLAND ISLANDS EYE DISEASE"

    hit = disease["DiseaseID"].eq(did)
    if hit.sum() != 1:
        raise SystemExit(f"Expected exactly one {did} disease row; found {hit.sum()}")

    old_row = disease.loc[hit].iloc[0].copy()

    disease.loc[hit, "Disease_Name"] = new_name
    disease.loc[hit, "MONDO_ID"] = "MONDO:0010371"
    disease.loc[hit, "OMIM_ID"] = "300600"
    disease.loc[hit, "Orphanet_ID"] = "ORPHA:178333"
    disease.loc[hit, "MedGen_UMLS_CUI"] = "C0268505"

    if "MONDO_Preferred_Label" in disease.columns:
        disease.loc[hit, "MONDO_Preferred_Label"] = "Aland island eye disease"
    if "MONDO_Match_Method" in disease.columns:
        disease.loc[hit, "MONDO_Match_Method"] = "manual_verified_legacy_name_correction"
    if "MONDO_Ambiguous_Candidates" in disease.columns:
        disease.loc[hit, "MONDO_Ambiguous_Candidates"] = ""
    if "Disease_Identifier_Curation_Status" in disease.columns:
        disease.loc[hit, "Disease_Identifier_Curation_Status"] = "mapped_verified_manual"

    # Preserve the legacy disease label as a synonym on the canonical row.
    if "Synonyms" in disease.columns:
        current = [x.strip() for x in clean(disease.loc[hit, "Synonyms"].iloc[0]).split(" | ") if x.strip()]
        for x in [
            old_name,
            "ALAND ISLAND EYE DISEASE",
            "FORSIUS ERIKSSON TYPE OCULAR ALBINISM",
        ]:
            if x not in current:
                current.append(x)
        disease.loc[hit, "Synonyms"] = " | ".join(current)

    if "Alternative_Disease_Names_From_Legacy" in disease.columns:
        current = [
            x.strip()
            for x in clean(
                disease.loc[hit, "Alternative_Disease_Names_From_Legacy"].iloc[0]
            ).split(" | ")
            if x.strip()
        ]
        if old_name not in current:
            current.append(old_name)
        disease.loc[hit, "Alternative_Disease_Names_From_Legacy"] = " | ".join(current)

    alias_row = {
        "Alias_DiseaseID": did,
        "Alias_Name": old_name,
        "Canonical_DiseaseID": did,
        "Canonical_Disease_Name": new_name,
        "Relationship": "legacy_name_of",
        "Status": "active_alias",
        "Reason": (
            "Verified correction of legacy label to Åland Islands eye disease; "
            "current authoritative identifiers: MONDO:0010371, OMIM:300600, "
            "ORPHA:178333, MedGen/UMLS C0268505."
        ),
        "MONDO_ID": "MONDO:0010371",
        "Orphanet_ID": "ORPHA:178333",
        "MedGen_UMLS_CUI": "C0268505",
    }
    aliases = append_alias(aliases, alias_row)

    # Association key does not change because DiseaseID stays ODDB-101.
    if "Disease" in dga.columns:
        dga.loc[dga["DiseaseID"].eq(did), "Disease"] = new_name

    # Focused manual-review file for the two unresolved legacy entities.
    review_ids = ["ODDB-143", "ODDB-146"]
    disease_review = disease[disease["DiseaseID"].isin(review_ids)].copy()

    dga_summary = (
        dga[dga["DiseaseID"].isin(review_ids)]
        .groupby("DiseaseID")
        .agg(
            DGA_Rows=("Association_ID", "nunique"),
            Genes=("GeneSymbol", lambda x: " | ".join(sorted(set(map(str, x))))),
            HGNC_IDs=("HGNC_ID", lambda x: " | ".join(sorted(set(map(str, x))))),
        )
        .reset_index()
    )

    lost_summary = (
        lost[lost["DiseaseID"].isin(review_ids)]
        .groupby([
            "DiseaseID",
            "ClinVar_Phenotype_Name",
            "ClinVar_Phenotype_IDs",
            "Current_DiseaseIDs",
            "Current_Disease_Names",
        ], dropna=False)
        .agg(
            Lost_Link_Count=("Variant_ID", "size"),
            Unique_Variants=("Variant_ID", "nunique"),
        )
        .reset_index()
        .sort_values(["DiseaseID", "Lost_Link_Count"], ascending=[True, False])
    )

    review = lost_summary.merge(
        disease_review[
            [c for c in [
                "DiseaseID", "Disease_Name", "MONDO_ID", "OMIM_ID",
                "Orphanet_ID", "MedGen_UMLS_CUI"
            ] if c in disease_review.columns]
        ],
        how="left",
        on="DiseaseID"
    ).merge(
        dga_summary,
        how="left",
        on="DiseaseID"
    )

    review["Curator_Action"] = "manual_review"
    review["Curator_Notes"] = review["DiseaseID"].map({
        "ODDB-143": (
            "Generic/truncated label. Do not automatically equate with a specific "
            "optic-disc disorder until legacy provenance/gene evidence is checked."
        ),
        "ODDB-146": (
            "Historical Oregon eye disease phenotype associated with Xp21 contiguous "
            "deletion/complex glycerol kinase deficiency. Review whether this belongs "
            "as a disease entity, structural-variant syndrome phenotype, or alias."
        ),
    })

    Path(args.disease_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.alias_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.dga_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.review_output).parent.mkdir(parents=True, exist_ok=True)

    disease.to_csv(args.disease_output, sep="\t", index=False)
    aliases.to_csv(args.alias_output, sep="\t", index=False)
    dga.to_csv(args.dga_output, sep="\t", index=False)
    review.to_csv(args.review_output, sep="\t", index=False)

    print("ODDB LEGACY DISEASE REVIEW PATCH")
    print(f"Corrected: {did} {old_name} -> {new_name}")
    print("MONDO_ID: MONDO:0010371")
    print("OMIM_ID: 300600")
    print("Orphanet_ID: ORPHA:178333")
    print("MedGen_UMLS_CUI: C0268505")
    print(f"Disease-gene rows renamed: {(dga['DiseaseID'] == did).sum()}")
    print(f"Manual-review rows for ODDB-143/ODDB-146: {len(review)}")
    print(f"\nDisease master: {args.disease_output}")
    print(f"Alias table: {args.alias_output}")
    print(f"Disease-gene table: {args.dga_output}")
    print(f"Focused review: {args.review_output}")


if __name__ == "__main__":
    main()
