#!/usr/bin/env python3
"""
Final ODDB v1 legacy disease curation for:
  - ODDB-143: normalize to Familial Cavitary Optic Disk Anomaly (CODA)
  - ODDB-146: reclassify DMD-only association as a structural/locus relationship

Outputs:
  * updated canonical Disease master
  * updated Disease alias table
  * updated canonical Disease-Gene Association table
  * reclassified legacy disease-gene rows
  * Disease-Locus Association table

No disease-variant rows are edited directly; rebuild those afterward.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def append_alias(df, row):
    if df is None or df.empty:
        return pd.DataFrame([row])

    for c in row:
        if c not in df.columns:
            df[c] = ""

    mask = (
        df["Alias_DiseaseID"].astype(str).eq(row["Alias_DiseaseID"])
        & df["Alias_Name"].astype(str).eq(row["Alias_Name"])
    )
    if mask.any():
        for k, v in row.items():
            df.loc[mask, k] = v
        return df

    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def add_synonym(value, synonym):
    vals = [x.strip() for x in clean(value).split(" | ") if x.strip()]
    if synonym and synonym not in vals:
        vals.append(synonym)
    return " | ".join(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--dga", required=True)
    ap.add_argument("--disease-output", required=True)
    ap.add_argument("--alias-output", required=True)
    ap.add_argument("--dga-output", required=True)
    ap.add_argument("--reclassified-output", required=True)
    ap.add_argument("--locus-output", required=True)
    ap.add_argument("--report-output", required=True)
    args = ap.parse_args()

    disease = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")
    aliases = pd.read_csv(args.aliases, sep="\t", dtype=str).fillna("")
    dga = pd.read_csv(args.dga, sep="\t", dtype=str).fillna("")

    # =========================================================
    # ODDB-143: Familial cavitary optic disk anomaly
    # =========================================================
    did = "ODDB-143"
    mask = disease["DiseaseID"].eq(did)
    if mask.sum() != 1:
        raise SystemExit(f"Expected exactly one {did} row, found {mask.sum()}")

    old_name_143 = clean(disease.loc[mask, "Disease_Name"].iloc[0])
    new_name_143 = "FAMILIAL CAVITARY OPTIC DISK ANOMALY"

    disease.loc[mask, "Disease_Name"] = new_name_143
    disease.loc[mask, "MONDO_ID"] = "MONDO:0012687"
    disease.loc[mask, "OMIM_ID"] = "611543"
    disease.loc[mask, "Orphanet_ID"] = "ORPHA:464760"
    disease.loc[mask, "MedGen_UMLS_CUI"] = "C1969063"

    if "MONDO_Preferred_Label" in disease.columns:
        disease.loc[mask, "MONDO_Preferred_Label"] = \
            "familial cavitary optic disk anomaly"

    if "MONDO_Match_Method" in disease.columns:
        disease.loc[mask, "MONDO_Match_Method"] = \
            "manual_verified_legacy_disease_normalization"

    if "MONDO_Ambiguous_Candidates" in disease.columns:
        disease.loc[mask, "MONDO_Ambiguous_Candidates"] = ""

    if "Disease_Identifier_Curation_Status" in disease.columns:
        disease.loc[mask, "Disease_Identifier_Curation_Status"] = \
            "mapped_verified_manual"

    if "Synonyms" in disease.columns:
        syn = clean(disease.loc[mask, "Synonyms"].iloc[0])
        for x in [
            old_name_143,
            "CAVITARY OPTIC DISC ANOMALIES",
            "CAVITARY OPTIC DISC ANOMALY",
            "CODA",
        ]:
            syn = add_synonym(syn, x)
        disease.loc[mask, "Synonyms"] = syn

    if "Alternative_Disease_Names_From_Legacy" in disease.columns:
        alt = clean(
            disease.loc[mask, "Alternative_Disease_Names_From_Legacy"].iloc[0]
        )
        alt = add_synonym(alt, old_name_143)
        disease.loc[mask, "Alternative_Disease_Names_From_Legacy"] = alt

    aliases = append_alias(
        aliases,
        {
            "Alias_DiseaseID": did,
            "Alias_Name": old_name_143,
            "Canonical_DiseaseID": did,
            "Canonical_Disease_Name": new_name_143,
            "Relationship": "legacy_name_of",
            "Status": "active_alias",
            "Reason":
                "Legacy broad label normalized to familial cavitary optic disk "
                "anomaly (CODA), supported by current MONDO/MedGen/OMIM/Orphanet "
                "identifiers and ClinVar condition records.",
            "MONDO_ID": "MONDO:0012687",
            "Orphanet_ID": "ORPHA:464760",
            "MedGen_UMLS_CUI": "C1969063",
        },
    )

    # =========================================================
    # ODDB-146: Oregon eye disease
    # Remove DMD-only row from canonical DGA and preserve it
    # as a reclassified structural/locus relationship.
    # =========================================================
    ore_mask = dga["DiseaseID"].eq("ODDB-146")
    reclassified = dga.loc[ore_mask].copy()

    if len(reclassified):
        reclassified.insert(
            0,
            "Reclassification",
            "removed_from_simple_disease_gene_association"
        )
        reclassified.insert(
            1,
            "Reclassification_Reason",
            "Oregon eye disease was described in Xp21 contiguous deletions / "
            "complex glycerol kinase deficiency; DMD alone is not established "
            "as the causal gene for the ocular phenotype."
        )
        reclassified.insert(
            2,
            "Recommended_Model",
            "Disease-Locus / structural-variant association"
        )

    dga_out = dga.loc[~ore_mask].copy()

    # =========================================================
    # Disease-locus relationships
    # =========================================================
    locus_rows = [
        {
            "Disease_Locus_Association_ID": "ODDB-DLA-ODDB143-CODA12Q13",
            "DiseaseID": "ODDB-143",
            "Disease_Name": new_name_143,
            "Locus_Name":
                "12q13.2 regulatory CNV upstream of MMP19",
            "Chromosome": "12",
            "Cytoband": "12q13.2",
            "Genetic_Entity_Type": "regulatory_structural_variant_locus",
            "Related_Genes": "MMP19",
            "Relationship":
                "regulatory CNV associated with disease; MMP19 dysregulation "
                "implicated",
            "Evidence_Status": "supported_with_limited_gene_validity",
            "PMID": "25581579",
            "DOI": "10.1002/humu.22754",
            "Notes":
                "Pathogenic upstream triplication reported in familial CODA; "
                "gene-disease validity for MMP19 should remain evidence-qualified."
        },
        {
            "Disease_Locus_Association_ID": "ODDB-DLA-ODDB146-XP21",
            "DiseaseID": "ODDB-146",
            "Disease_Name": "OREGON EYE DISEASE",
            "Locus_Name":
                "Xp21 contiguous gene deletion / complex glycerol kinase deficiency",
            "Chromosome": "X",
            "Cytoband": "Xp21",
            "Genetic_Entity_Type": "contiguous_gene_deletion_syndrome",
            "Related_Genes": "DMD | GK | NR0B1",
            "Relationship":
                "ocular phenotype observed in Xp21 deletion syndrome; not "
                "established as DMD-only causation",
            "Evidence_Status": "historical_supported_contextual",
            "PMID": "8240114",
            "DOI": "",
            "Notes":
                "Original Oregon eye disease report involved patients with "
                "complex glycerol kinase deficiency and demonstrated Xp21 "
                "chromosomal deletions."
        },
    ]
    locus = pd.DataFrame(locus_rows)

    # Disease gene counts must be recalculated after removing ODDB-146 DMD.
    counts = (
        dga_out.groupby("DiseaseID")
        .agg(
            Gene_Association_Count=("Association_ID", "nunique"),
            Unique_Gene_Count=("HGNC_ID", "nunique")
        )
        .reset_index()
    )

    for col in ["Gene_Association_Count", "Unique_Gene_Count"]:
        if col in disease.columns:
            disease = disease.drop(columns=[col])

    disease = disease.merge(counts, how="left", on="DiseaseID")
    disease["Gene_Association_Count"] = (
        disease["Gene_Association_Count"].fillna(0).astype(int)
    )
    disease["Unique_Gene_Count"] = (
        disease["Unique_Gene_Count"].fillna(0).astype(int)
    )

    if "Has_Gene_Association" in disease.columns:
        disease["Has_Gene_Association"] = disease[
            "Gene_Association_Count"
        ].map(lambda n: "Yes" if n > 0 else "No")

    # Validation
    duplicate_dga = dga_out.duplicated(
        ["DiseaseID", "HGNC_ID", "Inheritance"],
        keep=False
    ).sum()

    report = pd.DataFrame([
        ["Disease_rows", len(disease)],
        ["DGA_rows_before", len(dga)],
        ["ODDB146_DGA_rows_reclassified", len(reclassified)],
        ["DGA_rows_after", len(dga_out)],
        ["DGA_duplicate_keys_after", int(duplicate_dga)],
        ["ODDB143_MONDO_ID", "MONDO:0012687"],
        ["ODDB143_OMIM_ID", "611543"],
        ["ODDB143_Orphanet_ID", "ORPHA:464760"],
        ["ODDB143_CUI", "C1969063"],
        ["Disease_locus_rows", len(locus)],
    ], columns=["Metric", "Value"])

    for p in [
        args.disease_output,
        args.alias_output,
        args.dga_output,
        args.reclassified_output,
        args.locus_output,
        args.report_output,
    ]:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    disease.sort_values("DiseaseID").to_csv(
        args.disease_output, sep="\t", index=False
    )
    aliases.to_csv(args.alias_output, sep="\t", index=False)
    dga_out.to_csv(args.dga_output, sep="\t", index=False)
    reclassified.to_csv(args.reclassified_output, sep="\t", index=False)
    locus.to_csv(args.locus_output, sep="\t", index=False)
    report.to_csv(args.report_output, sep="\t", index=False)

    print("ODDB FINAL LEGACY DISEASE CURATION")
    print(report.to_string(index=False))
    print("\nODDB-143 normalized to Familial Cavitary Optic Disk Anomaly.")
    print("ODDB-146 DMD-only association removed from canonical DGA and preserved")
    print("as a reclassified structural/locus relationship.")
    print(f"\nDisease master: {args.disease_output}")
    print(f"Alias table: {args.alias_output}")
    print(f"Canonical DGA: {args.dga_output}")
    print(f"Reclassified rows: {args.reclassified_output}")
    print(f"Disease-locus table: {args.locus_output}")
    print(f"Report: {args.report_output}")


if __name__ == "__main__":
    main()
