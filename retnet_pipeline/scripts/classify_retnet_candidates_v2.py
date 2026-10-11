#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path

ACCEPTED_DISEASE_MATCH = {"exact", "synonym_rule", "high_confidence"}
NON_GENE = {"OPSIN-LCR", "KSS"}
MANUAL = {"LHON", "RP17"}

def norm(x):
    return str(x).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--oddb-hgnc", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    cand = pd.read_csv(args.candidates, sep="\t", dtype=str).fillna("")
    oddb = pd.read_csv(args.oddb_hgnc, sep="\t", dtype=str).fillna("")

    required = {
        "RetNet_Symbol", "HGNC_Match_Status", "Approved_GeneSymbol", "HGNC_ID",
        "ODDB_DiseaseID", "Disease_Match_Status"
    }
    missing = required - set(cand.columns)
    if missing:
        raise SystemExit(f"Candidate file missing columns: {sorted(missing)}")

    if "DiseaseID" not in oddb.columns or "HGNC_ID" not in oddb.columns:
        raise SystemExit("ODDB HGNC file must contain DiseaseID and HGNC_ID.")

    # Exclude rows explicitly reclassified as non-gene entities, if present.
    oddb_gene_rows = oddb.copy()
    if "Genetic_Entity_Type" in oddb_gene_rows.columns:
        et = oddb_gene_rows["Genetic_Entity_Type"].astype(str).str.strip().str.lower()
        oddb_gene_rows = oddb_gene_rows[et.isin(["", "gene"])]

    oddb_pairs = {
        (norm(d), norm(h))
        for d, h in zip(oddb_gene_rows["DiseaseID"], oddb_gene_rows["HGNC_ID"])
        if norm(d) and norm(h)
    }
    oddb_hgnc_ids = {
        norm(h) for h in oddb_gene_rows["HGNC_ID"] if norm(h)
    }

    classes = []
    reasons = []

    for _, r in cand.iterrows():
        original = norm(r["RetNet_Symbol"]).upper()
        hgnc_status = norm(r["HGNC_Match_Status"]).lower()
        hgnc_id = norm(r["HGNC_ID"])
        disease_id = norm(r["ODDB_DiseaseID"])
        disease_status = norm(r["Disease_Match_Status"]).lower()

        if original in NON_GENE:
            cls = "E_non_gene_entity"
            reason = "Known non-gene/special genetic entity."
        elif original in MANUAL:
            cls = "D_manual_review"
            reason = "Historical phenotype/locus label requires biological review."
        elif hgnc_status in {"not_found", "unmatched"} or not hgnc_id:
            cls = "D_manual_review"
            reason = "No unambiguous current HGNC gene ID."
        elif disease_status not in ACCEPTED_DISEASE_MATCH or not disease_id:
            cls = "D_disease_mapping_review"
            reason = f"Disease mapping status '{disease_status or 'missing'}' is not accepted automatically."
        elif (disease_id, hgnc_id) in oddb_pairs:
            cls = "A_existing_association"
            reason = "Same ODDB DiseaseID + HGNC ID already exists."
        elif hgnc_id in oddb_hgnc_ids:
            cls = "B_new_association_existing_gene"
            reason = "Gene exists in ODDB, but not for this matched ODDB DiseaseID."
        else:
            cls = "C_new_gene_for_ODDB"
            reason = "HGNC gene ID is absent from current ODDB gene records."

        classes.append(cls)
        reasons.append(reason)

    cand["Integration_Class"] = classes
    cand["Integration_Reason"] = reasons

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    cand.to_csv(args.output, sep="\t", index=False)

    print("ROW COUNTS")
    print(cand["Integration_Class"].value_counts().to_string())

    print("\nUNIQUE HGNC GENES BY CLASS")
    print(
        cand[cand["HGNC_ID"].ne("")]
        .groupby("Integration_Class")["HGNC_ID"]
        .nunique()
        .sort_values(ascending=False)
        .to_string()
    )

    print(f"\nWritten: {args.output}")
    print("Verified output column: Integration_Class")
    print("Accepted disease-match statuses:", ", ".join(sorted(ACCEPTED_DISEASE_MATCH)))

if __name__ == "__main__":
    main()
