#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path

# Conservative rules:
# - Only a small set of high-confidence symbol corrections are proposed automatically.
# - Locus/phenotype labels are reclassified, not converted to genes.
# - Ambiguous cases remain manual review.

SAFE_CORRECTIONS = {
    "CDK2NA": ("CDKN2A", "Gene", "Correct_gene_symbol",
               "Likely typographical error; validate against existing ODDB description/location before approval."),
    "PGDFRA": ("PDGFRA", "Gene", "Correct_gene_symbol",
               "Likely typographical error; validate against existing ODDB description/location before approval."),
    "FHASD": ("SLC38A8", "Gene", "Correct_gene_symbol",
              "Historical/alternative disease-associated symbol; verify against ODDB row metadata before approval."),
    "RNANC": ("ATOH7", "Gene", "Correct_gene_symbol",
              "Historical/alternative symbol; verify against ODDB row metadata before approval."),
    "USH2B": ("ADGRV1", "Gene", "Correct_gene_symbol",
              "Historical locus/syndrome-associated symbol; verify against ODDB row metadata before approval."),
}

# These should not be forced into an HGNC gene record.
MAPPED_LOCI = {
    "CORD1","CORD17","CORD4","EVR3","MCDR3","MCDR4","MCDR5","MYP11",
    "OPA2","OPA4","OPA5","OPA6","OPA8","RCD1","RP8","RP16","RP22",
    "RP24","RP29","RP34","RP6","RP63","USH1A","USH1E","USH1H","USH1K",
    "VMD1","VRD1"
}

PHENOTYPE_OR_DISEASE = {
    "BCAMD","CACD","MDDC","MRST","PRD","KSS"
}

REGULATORY_OR_OTHER = {
    "DHS6S1"
}

NCBI_ONLY = {
    "LOC157273","LOC338694","LOC730338"
}

MANUAL_GENE_OR_LOCUS = {
    "CODA1"
}

def clean(x):
    return str(x).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True,
                    help="oddb_gene_hgnc_mapping_YYYY-MM-DD.tsv")
    ap.add_argument("--oddb", required=True,
                    help="Original ODDB Gene_Disease_Drug_merged.tsv")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    mapping = pd.read_csv(args.mapping, sep="\t", dtype=str).fillna("")
    oddb = pd.read_csv(args.oddb, sep="\t", dtype=str).fillna("")

    mapping["ODDB_Original_GeneSymbol"] = mapping["ODDB_Original_GeneSymbol"].map(clean)

    problem = mapping[
        mapping["HGNC_Match_Status"].isin(["not_found", "ambiguous_alias"])
    ].copy()

    # Collect diseases in which each problematic symbol occurs.
    disease_col = "Ocular.disease" if "Ocular.disease" in oddb.columns else None
    disease_id_col = "DiseaseID" if "DiseaseID" in oddb.columns else None

    disease_map = {}
    for sym, g in oddb.groupby(oddb["GeneSymbol"].astype(str).str.strip()):
        info = {}
        if disease_col:
            info["ODDB_Diseases"] = " | ".join(sorted(set(
                x.strip() for x in g[disease_col].astype(str) if x.strip()
            )))
        else:
            info["ODDB_Diseases"] = ""
        if disease_id_col:
            info["ODDB_DiseaseIDs"] = " | ".join(sorted(set(
                x.strip() for x in g[disease_id_col].astype(str) if x.strip()
            )))
        else:
            info["ODDB_DiseaseIDs"] = ""
        disease_map[sym] = info

    rows = []
    for _, r in problem.iterrows():
        sym = clean(r["ODDB_Original_GeneSymbol"])
        approved = clean(r.get("Approved_GeneSymbol", ""))
        hgnc_id = clean(r.get("HGNC_ID", ""))

        entity_type = "Needs review"
        action = "Manual_review"
        proposed = ""
        reason = "HGNC normalization did not yield an unambiguous current gene."
        review = "pending"

        if sym in SAFE_CORRECTIONS:
            proposed, entity_type, action, reason = SAFE_CORRECTIONS[sym]

        elif sym in MAPPED_LOCI:
            entity_type = "Mapped locus"
            action = "Reclassify_entity"
            reason = "Symbol is treated as a mapped/phenotype locus rather than an HGNC gene."

        elif sym in PHENOTYPE_OR_DISEASE:
            entity_type = "Phenotype/disease identifier"
            action = "Reclassify_entity"
            reason = "Symbol represents a phenotype/disease designation rather than a gene."

        elif sym in REGULATORY_OR_OTHER:
            entity_type = "Regulatory/other genetic entity"
            action = "Reclassify_entity"
            reason = "Should not be forced into the HGNC gene table; requires separate entity representation."

        elif sym in NCBI_ONLY:
            entity_type = "NCBI-only/legacy locus"
            action = "Manual_review"
            reason = "Legacy LOC identifier without a resolved HGNC match; retain until independently reviewed."

        elif sym in MANUAL_GENE_OR_LOCUS:
            entity_type = "Needs review"
            action = "Manual_review"
            reason = "Possible gene/locus naming issue; do not auto-correct without checking ODDB metadata and primary source."

        info = disease_map.get(sym, {"ODDB_Diseases": "", "ODDB_DiseaseIDs": ""})

        rows.append({
            "Original_Symbol": sym,
            "HGNC_Match_Status": clean(r.get("HGNC_Match_Status", "")),
            "Current_HGNC_Suggestion": approved,
            "Current_HGNC_ID": hgnc_id,
            "ODDB_DiseaseIDs": info["ODDB_DiseaseIDs"],
            "ODDB_Diseases": info["ODDB_Diseases"],
            "Entity_Type": entity_type,
            "Proposed_GeneSymbol": proposed,
            "Proposed_HGNC_ID": "",
            "NCBI_Gene_ID": "",
            "Locus_or_Region": "",
            "Action": action,
            "Review_Status": review,
            "Reason": reason,
            "Curator_Notes": ""
        })

    out = pd.DataFrame(rows).sort_values(["Action", "Original_Symbol"])
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)

    print(f"Wrote {len(out)} cleanup candidates to {args.output}")
    print("\nBy proposed action:")
    print(out["Action"].value_counts().to_string())
    print("\nBy entity type:")
    print(out["Entity_Type"].value_counts().to_string())
    print("\nIMPORTANT: Review_Status is 'pending' for every row. Nothing is approved automatically.")

if __name__ == "__main__":
    main()
