#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path

def clean(x):
    return str(x).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oddb", required=True,
                    help="Original ODDB Gene_Disease_Drug_merged.tsv")
    ap.add_argument("--cleanup", required=True,
                    help="Reviewed cleanup TSV. Only Review_Status=approved rows are applied.")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    oddb = pd.read_csv(args.oddb, sep="\t", dtype=str).fillna("")
    cleanup = pd.read_csv(args.cleanup, sep="\t", dtype=str).fillna("")

    required = {"Original_Symbol", "Action", "Review_Status", "Entity_Type", "Proposed_GeneSymbol"}
    missing = required - set(cleanup.columns)
    if missing:
        raise SystemExit(f"Cleanup table missing columns: {sorted(missing)}")

    approved = cleanup[
        cleanup["Review_Status"].str.strip().str.lower().eq("approved")
    ].copy()

    # Never overwrite the original symbol silently.
    if "Original_GeneSymbol" not in oddb.columns:
        oddb.insert(
            oddb.columns.get_loc("GeneSymbol") + 1,
            "Original_GeneSymbol",
            oddb["GeneSymbol"].astype(str)
        )

    if "Genetic_Entity_Type" not in oddb.columns:
        oddb["Genetic_Entity_Type"] = "Gene"
    if "Cleanup_Action" not in oddb.columns:
        oddb["Cleanup_Action"] = ""
    if "Cleanup_Review_Status" not in oddb.columns:
        oddb["Cleanup_Review_Status"] = ""
    if "Cleanup_Notes" not in oddb.columns:
        oddb["Cleanup_Notes"] = ""

    n_symbol_changes = 0
    n_reclassified = 0

    for _, r in approved.iterrows():
        original = clean(r["Original_Symbol"])
        action = clean(r["Action"])
        entity = clean(r["Entity_Type"])
        proposed = clean(r["Proposed_GeneSymbol"])
        notes = clean(r.get("Curator_Notes", ""))

        mask = oddb["GeneSymbol"].astype(str).str.strip().eq(original)
        if not mask.any():
            continue

        oddb.loc[mask, "Genetic_Entity_Type"] = entity
        oddb.loc[mask, "Cleanup_Action"] = action
        oddb.loc[mask, "Cleanup_Review_Status"] = "approved"
        oddb.loc[mask, "Cleanup_Notes"] = notes

        if action == "Correct_gene_symbol":
            if not proposed:
                raise SystemExit(
                    f"{original}: Correct_gene_symbol approved but Proposed_GeneSymbol is empty."
                )
            n_symbol_changes += int(mask.sum())
            oddb.loc[mask, "GeneSymbol"] = proposed

        elif action == "Reclassify_entity":
            n_reclassified += int(mask.sum())
            # Preserve GeneSymbol for traceability. Downstream pipeline should use
            # Genetic_Entity_Type to exclude non-gene entities from gene analyses.

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    oddb.to_csv(args.output, sep="\t", index=False)

    print(f"Approved cleanup rows: {len(approved)}")
    print(f"ODDB rows with corrected gene symbols: {n_symbol_changes}")
    print(f"ODDB rows reclassified as non-standard genetic entities: {n_reclassified}")
    print(f"Wrote cleaned copy to: {args.output}")
    print("Original input file was not modified.")

if __name__ == "__main__":
    main()
