#!/usr/bin/env python3
"""
Audit why direct ODDB disease-drug evidence has zero target overlap.

For every Disease_Drug_Association row, determine:
- whether the drug has any Drug_Target_Association in ODDB
- which ODDB genes it targets
- whether any of those targets are genes associated with the same disease
- whether it targets genes associated with other ODDB diseases

No files are modified.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def uniq_join(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return " | ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dda", required=True)
    ap.add_argument("--dta", required=True)
    ap.add_argument("--dga", required=True)
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    dda = pd.read_csv(args.dda, sep="\t", dtype=str).fillna("")
    dta = pd.read_csv(args.dta, sep="\t", dtype=str).fillna("")
    dga = pd.read_csv(args.dga, sep="\t", dtype=str).fillna("")
    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    diseases = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    drug_name = dict(zip(drugs["Drug_ID"], drugs["Preferred_Name"]))
    disease_name = dict(zip(diseases["DiseaseID"], diseases["Disease_Name"]))

    # Disease -> HGNC set
    disease_genes = (
        dga.groupby("DiseaseID")["HGNC_ID"]
        .apply(lambda x: set(v for v in x if clean(v)))
        .to_dict()
    )

    # HGNC -> diseases
    gene_diseases = {}
    for hgnc, g in dga.groupby("HGNC_ID"):
        gene_diseases[hgnc] = set(g["DiseaseID"])

    # Drug -> target rows
    dta_by_drug = {k: g.copy() for k, g in dta.groupby("Drug_ID")}

    rows = []

    for _, r in dda.iterrows():
        did = clean(r["DiseaseID"])
        drug_id = clean(r["Drug_ID"])

        tg = dta_by_drug.get(drug_id)
        disease_hgnc = disease_genes.get(did, set())

        if tg is None or tg.empty:
            rows.append({
                "DiseaseID": did,
                "Disease_Name": disease_name.get(did, ""),
                "Drug_ID": drug_id,
                "Drug_Name": drug_name.get(drug_id, clean(r.get("Drug_Name"))),
                "Has_Any_ODDB_Drug_Target": "No",
                "ODDB_Target_Gene_Count": 0,
                "ODDB_Target_Genes": "",
                "Same_Disease_Target_Count": 0,
                "Same_Disease_Target_Genes": "",
                "Targets_Genes_From_Other_ODDB_Diseases": "No",
                "Other_ODDB_Disease_Count": 0,
                "Other_ODDB_Diseases": "",
                "Interpretation":
                    "Direct disease-drug evidence exists, but this drug has "
                    "no Open Targets drug-target relationship among ODDB genes."
            })
            continue

        targets = set(tg["HGNC_ID"])
        same = targets & disease_hgnc

        other_diseases = set()
        for hgnc in targets:
            other_diseases |= gene_diseases.get(hgnc, set())
        other_diseases.discard(did)

        rows.append({
            "DiseaseID": did,
            "Disease_Name": disease_name.get(did, ""),
            "Drug_ID": drug_id,
            "Drug_Name": drug_name.get(drug_id, clean(r.get("Drug_Name"))),
            "Has_Any_ODDB_Drug_Target": "Yes",
            "ODDB_Target_Gene_Count": len(targets),
            "ODDB_Target_Genes": uniq_join(tg["GeneSymbol"]),
            "Same_Disease_Target_Count": len(same),
            "Same_Disease_Target_Genes":
                uniq_join(tg.loc[tg["HGNC_ID"].isin(same), "GeneSymbol"]),
            "Targets_Genes_From_Other_ODDB_Diseases":
                "Yes" if other_diseases else "No",
            "Other_ODDB_Disease_Count": len(other_diseases),
            "Other_ODDB_Diseases":
                " | ".join(
                    sorted(disease_name.get(x, x) for x in other_diseases)
                ),
            "Interpretation":
                (
                    "Drug has Open Targets target(s) among ODDB genes, but "
                    "none are genes associated with this same disease."
                    if not same
                    else
                    "Drug directly targets at least one ODDB gene associated "
                    "with this disease."
                )
        })

    audit = pd.DataFrame(rows)

    summary = pd.DataFrame([
        ["Direct_disease_drug_rows", len(audit)],
        ["Direct_rows_drug_has_any_ODDB_target",
         int(audit["Has_Any_ODDB_Drug_Target"].eq("Yes").sum())],
        ["Direct_rows_drug_has_no_ODDB_target",
         int(audit["Has_Any_ODDB_Drug_Target"].eq("No").sum())],
        ["Direct_rows_with_same_disease_target",
         int((audit["Same_Disease_Target_Count"] > 0).sum())],
        ["Direct_rows_targeting_only_other_ODDB_disease_genes",
         int((
             audit["Has_Any_ODDB_Drug_Target"].eq("Yes")
             & audit["Same_Disease_Target_Count"].eq(0)
         ).sum())],
        ["Unique_direct_drugs", audit["Drug_ID"].nunique()],
        ["Unique_direct_drugs_with_any_ODDB_target",
         audit.loc[
             audit["Has_Any_ODDB_Drug_Target"].eq("Yes"),
             "Drug_ID"
         ].nunique()],
    ], columns=["Metric", "Value"])

    audit.to_csv(
        outdir / "direct_disease_drug_target_coverage.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "direct_disease_drug_target_coverage_summary.tsv",
        sep="\t", index=False
    )

    audit[
        audit["Has_Any_ODDB_Drug_Target"].eq("Yes")
    ].to_csv(
        outdir / "direct_drugs_with_any_oddb_target.tsv",
        sep="\t", index=False
    )

    audit[
        audit["Has_Any_ODDB_Drug_Target"].eq("No")
    ].to_csv(
        outdir / "direct_drugs_without_oddb_target.tsv",
        sep="\t", index=False
    )

    print("ODDB DIRECT DISEASE-DRUG TARGET COVERAGE AUDIT")
    print(summary.to_string(index=False))

    print("\nDirect disease-drug rows whose drug has an ODDB target:")
    hit = audit[audit["Has_Any_ODDB_Drug_Target"].eq("Yes")]
    if len(hit):
        print(
            hit[
                [
                    "DiseaseID",
                    "Disease_Name",
                    "Drug_Name",
                    "ODDB_Target_Genes",
                    "Same_Disease_Target_Genes",
                    "Other_ODDB_Disease_Count",
                ]
            ].to_string(index=False)
        )
    else:
        print("None")

    print(f"\nReports: {outdir}")


if __name__ == "__main__":
    main()
