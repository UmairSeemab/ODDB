#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd

def clean(x):
    return str(x or "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True,
                    help="v2 detailed disease mapping TSV")
    ap.add_argument("--oddb-hgnc", required=True,
                    help="HGNC-normalized cleaned ODDB TSV")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    m = pd.read_csv(args.mapping, sep="\t", dtype=str).fillna("")
    oddb = pd.read_csv(args.oddb_hgnc, sep="\t", dtype=str).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Use only gene rows from cleaned ODDB when entity type is available.
    g = oddb.copy()
    if "Genetic_Entity_Type" in g.columns:
        et = g["Genetic_Entity_Type"].astype(str).str.strip().str.lower()
        g = g[et.isin(["", "gene"])]

    oddb_pairs = {
        (clean(d), clean(h))
        for d, h in zip(g["DiseaseID"], g["HGNC_ID"])
        if clean(d) and clean(h)
    }
    oddb_genes = {clean(h) for h in g["HGNC_ID"] if clean(h)}

    def pair_status(row):
        did = clean(row.get("Suggested_ODDB_DiseaseID", ""))
        hid = clean(row.get("HGNC_ID", ""))

        if not did or not hid:
            return ""

        if (did, hid) in oddb_pairs:
            return "existing_oddb_association"
        if hid in oddb_genes:
            return "new_association_existing_gene"
        return "new_gene_for_oddb"

    m["Detailed_ODDB_Pair_Status"] = m.apply(pair_status, axis=1)

    # Strict exact queue: only exact disease match, inheritance compatible,
    # valid HGNC ID, and no inheritance conflict.
    exact = m[
        (m["Detailed_Disease_Match_Status"] == "exact")
        & (m["Inheritance_Compatible"] == "Yes")
        & (m["HGNC_ID"].str.strip() != "")
    ].copy()

    parent = m[
        (m["Detailed_Disease_Match_Status"] == "parent_disease_suggestion")
        & (m["Inheritance_Compatible"] == "Yes")
    ].copy()

    new_disease = m[
        m["Detailed_Disease_Match_Status"] == "no_close_oddb_match"
    ].copy()

    conflicts = m[
        m["Detailed_Disease_Match_Status"] == "inheritance_conflict"
    ].copy()

    fuzzy = m[
        m["Detailed_Disease_Match_Status"].isin(
            ["high_confidence_suggestion", "review_suggestion"]
        )
    ].copy()

    manual = m[
        m["Detailed_Disease_Match_Status"].isin(
            ["no_detailed_record", "no_parsed_phenotype"]
        )
    ].copy()

    # Deduplicate the exact queue at the gene+disease+inheritance level.
    exact_unique = exact.drop_duplicates(
        subset=[
            "HGNC_ID",
            "Suggested_ODDB_DiseaseID",
            "Inheritance",
            "Detailed_Phenotype_Raw"
        ]
    ).copy()

    # A candidate for automatic promotion must still be independently verified.
    exact_unique["Promotion_Eligibility"] = exact_unique["Detailed_ODDB_Pair_Status"].map({
        "existing_oddb_association": "do_not_add_duplicate",
        "new_association_existing_gene": "verify_before_add",
        "new_gene_for_oddb": "verify_before_add",
    }).fillna("manual_review")

    exact_path = outdir / "exact_disease_matches.tsv"
    parent_path = outdir / "parent_disease_review.tsv"
    new_path = outdir / "possible_new_diseases.tsv"
    conflict_path = outdir / "inheritance_conflicts.tsv"
    fuzzy_path = outdir / "fuzzy_disease_review.tsv"
    manual_path = outdir / "manual_review.tsv"
    summary_path = outdir / "triage_summary.tsv"

    exact_unique.to_csv(exact_path, sep="\t", index=False)
    parent.to_csv(parent_path, sep="\t", index=False)
    new_disease.to_csv(new_path, sep="\t", index=False)
    conflicts.to_csv(conflict_path, sep="\t", index=False)
    fuzzy.to_csv(fuzzy_path, sep="\t", index=False)
    manual.to_csv(manual_path, sep="\t", index=False)

    summary_rows = [
        {"Queue": "Exact disease matches", "Rows": len(exact_unique),
         "Unique_HGNC_Genes": exact_unique["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
        {"Queue": "Parent disease review", "Rows": len(parent),
         "Unique_HGNC_Genes": parent["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
        {"Queue": "Possible new diseases", "Rows": len(new_disease),
         "Unique_HGNC_Genes": new_disease["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
        {"Queue": "Inheritance conflicts", "Rows": len(conflicts),
         "Unique_HGNC_Genes": conflicts["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
        {"Queue": "Fuzzy disease review", "Rows": len(fuzzy),
         "Unique_HGNC_Genes": fuzzy["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
        {"Queue": "Manual review", "Rows": len(manual),
         "Unique_HGNC_Genes": manual["HGNC_ID"].replace("", pd.NA).dropna().nunique()},
    ]
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(summary_path, sep="\t", index=False)

    print("TRIAGE SUMMARY")
    print(summary.to_string(index=False))

    print("\nEXACT MATCH PAIR STATUS")
    if len(exact_unique):
        print(exact_unique["Detailed_ODDB_Pair_Status"].value_counts().to_string())
    else:
        print("No exact matches.")

    print("\nEXACT MATCHES ELIGIBLE FOR VERIFICATION")
    verify = exact_unique[
        exact_unique["Promotion_Eligibility"] == "verify_before_add"
    ]
    print("Rows:", len(verify))
    print("Unique genes:", verify["HGNC_ID"].replace("", pd.NA).dropna().nunique())

    print(f"\nFiles written under: {outdir}")
    print("No ODDB records were changed.")

if __name__ == "__main__":
    main()
