#!/usr/bin/env python3
"""
Audit whether ODDB v1 drug-identity refinements require Drug_Target_Association
rebuilding.

AUDIT ONLY. No canonical/frozen files are modified.

It checks the Open Targets 26.09 drug_mechanism_of_action dataset for:
- the drugs that gained a ChEMBL ID in the refined Drug_v1;
- newly added drug entities such as RETINOL / CHEMBL986.

Only mechanisms whose targets map to ODDB genes are counted.
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds


def clean(x):
    if x is None:
        return ""
    return str(x).strip()


def as_list(x):
    if x is None:
        return []
    if hasattr(x, "tolist"):
        x = x.tolist()
    if isinstance(x, (list, tuple, set)):
        return [clean(v) for v in x if clean(v)]
    s = clean(x)
    if not s:
        return []
    return [v.strip() for v in re.split(r"\s*[|;,]\s*", s) if v.strip()]


def json_safe(x):
    if x is None:
        return None
    if hasattr(x, "tolist"):
        return json_safe(x.tolist())
    if isinstance(x, dict):
        return {str(k): json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [json_safe(v) for v in x]
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    return x


def find_col(df, candidates, required=True):
    normalized = {
        re.sub(r"[^a-z0-9]", "", c.lower()): c
        for c in df.columns
    }
    for cand in candidates:
        k = re.sub(r"[^a-z0-9]", "", cand.lower())
        if k in normalized:
            return normalized[k]
    if required:
        raise SystemExit(
            f"Could not find any of {candidates}. Columns: {list(df.columns)}"
        )
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original-drugs", required=True)
    ap.add_argument("--refined-drugs", required=True)
    ap.add_argument("--genes", required=True)
    ap.add_argument("--existing-dta", required=True)
    ap.add_argument("--moa-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    original = pd.read_csv(
        args.original_drugs, sep="\t", dtype=str
    ).fillna("")
    refined = pd.read_csv(
        args.refined_drugs, sep="\t", dtype=str
    ).fillna("")
    genes = pd.read_csv(
        args.genes, sep="\t", dtype=str
    ).fillna("")
    dta = pd.read_csv(
        args.existing_dta, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    problems = []

    gene_ens_col = find_col(
        genes,
        [
            "Ensembl_Gene_ID",
            "Ensembl_ID",
            "EnsemblGeneID",
            "Ensembl_Gene",
        ],
    )
    gene_symbol_col = find_col(
        genes,
        ["Gene_Symbol", "Approved_Symbol", "GeneSymbol", "Symbol"],
        required=False,
    )

    orig_by_id = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in original.iterrows()
    }

    candidate_rows = []

    for _, r in refined.iterrows():
        did = clean(r["Drug_ID"])
        new_chembl = clean(r.get("ChEMBL_ID")).upper()

        if not new_chembl.startswith("CHEMBL"):
            continue

        old = orig_by_id.get(did)
        old_chembl = clean(old.get("ChEMBL_ID")) if old else ""

        is_new_drug = old is None
        is_new_chembl = (
            not old_chembl
            or old_chembl.upper() != new_chembl
        )

        if not (is_new_drug or is_new_chembl):
            continue

        candidate_rows.append({
            "Drug_ID": did,
            "Drug_Name": clean(r.get("Preferred_Name")),
            "Old_ChEMBL_ID": old_chembl,
            "Refined_ChEMBL_ID": new_chembl,
            "Candidate_Type":
                "new_drug_entity" if is_new_drug
                else "newly_enriched_chembl",
        })

    candidates = pd.DataFrame(candidate_rows)

    candidate_chembl = set(
        candidates["Refined_ChEMBL_ID"]
    ) if len(candidates) else set()

    ensembl_to_gene = {}
    for _, r in genes.iterrows():
        ens = clean(r[gene_ens_col])
        if not ens:
            continue
        ens0 = ens.split(".")[0]
        ensembl_to_gene[ens0] = {
            "HGNC_ID": clean(r.get("HGNC_ID")),
            "Gene_Symbol":
                clean(r.get(gene_symbol_col)) if gene_symbol_col else "",
        }

    moa_path = Path(args.moa_dir)
    if not moa_path.exists():
        raise SystemExit(f"MOA directory does not exist: {moa_path}")

    dataset = ds.dataset(
        str(moa_path),
        format="parquet",
        partitioning="hive",
    )

    needed = [
        "mechanismOfAction",
        "actionType",
        "chemblIds",
        "references",
        "targetName",
        "targetType",
        "targets",
    ]
    cols = [c for c in needed if c in dataset.schema.names]

    if "chemblIds" not in cols or "targets" not in cols:
        raise SystemExit(
            f"Unexpected MOA schema. Available: {dataset.schema.names}"
        )

    moa = dataset.to_table(columns=cols).to_pandas()

    hit_rows = []

    for idx, r in moa.iterrows():
        chembl_ids = [
            x.upper() for x in as_list(r.get("chemblIds"))
            if x.upper().startswith("CHEMBL")
        ]

        matched_chembl = sorted(
            candidate_chembl.intersection(chembl_ids)
        )

        if not matched_chembl:
            continue

        target_ids = [
            x.split(".")[0]
            for x in as_list(r.get("targets"))
            if x
        ]

        matched_targets = [
            x for x in target_ids
            if x in ensembl_to_gene
        ]

        if not matched_targets:
            continue

        for chembl in matched_chembl:
            csub = candidates[
                candidates["Refined_ChEMBL_ID"].eq(chembl)
            ]

            for _, c in csub.iterrows():
                for ens in matched_targets:
                    gm = ensembl_to_gene[ens]

                    hit_rows.append({
                        "Drug_ID": clean(c["Drug_ID"]),
                        "Drug_Name": clean(c["Drug_Name"]),
                        "ChEMBL_ID": chembl,
                        "Candidate_Type": clean(c["Candidate_Type"]),
                        "HGNC_ID": clean(gm["HGNC_ID"]),
                        "Gene_Symbol": clean(gm["Gene_Symbol"]),
                        "Ensembl_Gene_ID": ens,
                        "Mechanism_Of_Action":
                            clean(r.get("mechanismOfAction")),
                        "Action_Type": clean(r.get("actionType")),
                        "Target_Name": clean(r.get("targetName")),
                        "Target_Type": clean(r.get("targetType")),
                        "OpenTargets_References_JSON":
                            json.dumps(
                                json_safe(r.get("references")),
                                ensure_ascii=False,
                            ),
                        "MOA_Source_Row_Index": idx,
                    })

    hits = pd.DataFrame(hit_rows)

    existing_pairs = set()
    if {"Drug_ID", "HGNC_ID"}.issubset(dta.columns):
        existing_pairs = set(
            zip(dta["Drug_ID"], dta["HGNC_ID"])
        )

    if len(hits):
        pair_rows = []

        for (did, hgnc), g in hits.groupby(
            ["Drug_ID", "HGNC_ID"], sort=True
        ):
            pair_rows.append({
                "Drug_ID": did,
                "Drug_Name": clean(g.iloc[0]["Drug_Name"]),
                "ChEMBL_ID": clean(g.iloc[0]["ChEMBL_ID"]),
                "HGNC_ID": hgnc,
                "Gene_Symbol": clean(g.iloc[0]["Gene_Symbol"]),
                "MOA_Record_Count": len(g),
                "Mechanisms": " | ".join(
                    sorted(set(
                        clean(x) for x in g["Mechanism_Of_Action"]
                        if clean(x)
                    ))
                ),
                "Action_Types": " | ".join(
                    sorted(set(
                        clean(x) for x in g["Action_Type"]
                        if clean(x)
                    ))
                ),
                "Already_In_Existing_DTA":
                    "Yes" if (did, hgnc) in existing_pairs else "No",
            })

        candidate_pairs = pd.DataFrame(pair_rows)
    else:
        candidate_pairs = pd.DataFrame(
            columns=[
                "Drug_ID", "Drug_Name", "ChEMBL_ID",
                "HGNC_ID", "Gene_Symbol", "MOA_Record_Count",
                "Mechanisms", "Action_Types",
                "Already_In_Existing_DTA",
            ]
        )

    new_pairs = candidate_pairs[
        candidate_pairs["Already_In_Existing_DTA"].eq("No")
    ].copy()

    summary = pd.DataFrame([
        ["Original_Drug_rows", len(original)],
        ["Refined_Drug_rows", len(refined)],
        ["New_or_newly_ChEMBL_identified_drugs", len(candidates)],
        ["Newly_enriched_existing_drugs",
         int(candidates["Candidate_Type"].eq(
             "newly_enriched_chembl"
         ).sum()) if len(candidates) else 0],
        ["New_drug_entities",
         int(candidates["Candidate_Type"].eq(
             "new_drug_entity"
         ).sum()) if len(candidates) else 0],
        ["Candidate_ChEMBL_IDs", len(candidate_chembl)],
        ["MOA_rows_total", len(moa)],
        ["MOA_ODDB_gene_hit_rows_for_candidates", len(hits)],
        ["Unique_candidate_drug_gene_pairs", len(candidate_pairs)],
        ["Candidate_pairs_already_in_existing_DTA",
         int(candidate_pairs["Already_In_Existing_DTA"]
             .eq("Yes").sum()) if len(candidate_pairs) else 0],
        ["NEW_DTA_pairs_required",
         int(candidate_pairs["Already_In_Existing_DTA"]
             .eq("No").sum()) if len(candidate_pairs) else 0],
        ["Candidate_drugs_with_ODDB_gene_MOA",
         hits["Drug_ID"].nunique() if len(hits) else 0],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    candidates.to_csv(
        outdir / "refined_drug_new_chembl_candidates.tsv",
        sep="\t", index=False
    )

    hits.to_csv(
        outdir / "refined_drug_new_chembl_moa_oddb_gene_hits.tsv",
        sep="\t", index=False
    )

    candidate_pairs.to_csv(
        outdir / "refined_drug_new_dta_candidate_pairs.tsv",
        sep="\t", index=False
    )

    new_pairs.to_csv(
        outdir / "refined_drug_new_dta_pairs_required.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "refined_dta_rebuild_audit_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame(
        problems,
        columns=["Table", "Problem", "Detail"]
    ).to_csv(
        outdir / "refined_dta_rebuild_audit_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB REFINED DRUG-TARGET REBUILD AUDIT")
    print(summary.to_string(index=False))

    if len(new_pairs):
        print("\nNEW DTA PAIRS REQUIRED:")
        print(new_pairs.to_string(index=False))
    else:
        print("\nNo new Drug_Target_Association pairs are required.")

    if problems:
        print("\nVALIDATION NEEDS REVIEW.")
    else:
        print("\nVALIDATION PASSED.")

    print("\nReports:", outdir)
    print("\nAUDIT ONLY: no DTA/canonical/frozen files were modified.")


if __name__ == "__main__":
    main()
