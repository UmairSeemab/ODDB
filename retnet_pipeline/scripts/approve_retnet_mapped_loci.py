#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
import pandas as pd

def tokens(text):
    # RetNet locus symbols/regions are whitespace-separated in the rendered table.
    return [t.strip() for t in re.split(r"\s+", str(text).strip()) if t.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleanup", required=True,
                    help="Cleanup review TSV produced by prepare_oddb_genetic_cleanup.py")
    ap.add_argument("--retnet-loci", required=True,
                    help="Fresh RetNet rendered Table B TSV")
    ap.add_argument("--output", required=True,
                    help="Updated cleanup review TSV")
    args = ap.parse_args()

    cleanup = pd.read_csv(args.cleanup, sep="\t", dtype=str).fillna("")
    table = pd.read_csv(args.retnet_loci, sep="\t", header=None, dtype=str).fillna("")

    # Locate actual two-column header row.
    header_idx = None
    for i, row in table.iterrows():
        vals = [str(v).strip().lower() for v in row.tolist()]
        disease_cols = [j for j, v in enumerate(vals) if "disease category" in v]
        locus_cols = [j for j, v in enumerate(vals) if "mapped loci" in v and "gene not identified" in v]
        if disease_cols and locus_cols and disease_cols[0] != locus_cols[0]:
            header_idx = i
            locus_col = locus_cols[0]
            break

    if header_idx is None:
        raise SystemExit("Could not identify RetNet Table B header safely.")

    unresolved = set()
    for i in range(header_idx + 1, len(table)):
        cell = str(table.iloc[i, locus_col]).strip()
        if not cell:
            continue
        unresolved.update(tokens(cell))

    changed = []
    for idx, row in cleanup.iterrows():
        sym = str(row["Original_Symbol"]).strip()
        entity = str(row["Entity_Type"]).strip()
        action = str(row["Action"]).strip()
        status = str(row["Review_Status"]).strip().lower()

        if (
            status == "pending"
            and entity == "Mapped locus"
            and action == "Reclassify_entity"
            and sym in unresolved
        ):
            cleanup.at[idx, "Review_Status"] = "approved"
            note = str(row.get("Curator_Notes", "")).strip()
            evidence = "Confirmed in current RetNet Table B as mapped locus with gene not identified."
            cleanup.at[idx, "Curator_Notes"] = f"{note} {evidence}".strip()
            changed.append(sym)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    cleanup.to_csv(args.output, sep="\t", index=False)

    print(f"RetNet unresolved loci parsed: {len(unresolved)}")
    print(f"Newly approved mapped-locus reclassifications: {len(changed)}")
    if changed:
        print("Approved:")
        for s in sorted(changed):
            print(f"  {s}")
    print(f"\nUpdated cleanup table: {args.output}")

    still_pending = cleanup[cleanup["Review_Status"].str.lower().eq("pending")]
    print(f"Still pending: {len(still_pending)}")
    if len(still_pending):
        print("\nPending by entity type:")
        print(still_pending["Entity_Type"].value_counts().to_string())

if __name__ == "__main__":
    main()
