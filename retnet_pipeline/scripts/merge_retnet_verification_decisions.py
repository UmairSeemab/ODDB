#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd

KEYS = ["Approved_GeneSymbol", "HGNC_ID", "Suggested_ODDB_Disease", "Inheritance"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    q = pd.read_csv(args.queue, sep="\t", dtype=str).fillna("")
    d = pd.read_csv(args.decisions, sep="\t", dtype=str).fillna("")

    missing_q = set(KEYS) - set(q.columns)
    missing_d = set(KEYS) - set(d.columns)
    if missing_q or missing_d:
        raise SystemExit(f"Missing keys: queue={sorted(missing_q)}, decisions={sorted(missing_d)}")

    # avoid collisions with the blank verification fields already in queue
    update_cols = [
        "Independent_Verification_Status",
        "Primary_Reference_PMID_Verified",
        "Primary_Reference_DOI_Verified",
        "Curator_Decision",
        "Curator_Notes_Verification",
    ]
    for c in update_cols:
        if c not in d.columns:
            raise SystemExit(f"Decision file missing required column: {c}")

    # Validate uniqueness
    dup = d.duplicated(KEYS, keep=False)
    if dup.any():
        print("WARNING: duplicate decision keys found:")
        print(d.loc[dup, KEYS].to_string(index=False))
        raise SystemExit("Resolve duplicate decision keys before merging.")

    dec = d[KEYS + update_cols].copy()
    for c in update_cols:
        dec = dec.rename(columns={c: f"{c}__verified"})

    out = q.merge(dec, how="left", on=KEYS, validate="one_to_one")

    matched = out["Independent_Verification_Status__verified"].ne("")
    for c in update_cols:
        vc = f"{c}__verified"
        out.loc[matched, c] = out.loc[matched, vc]
        out = out.drop(columns=[vc])

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)

    print(f"Queue rows: {len(q)}")
    print(f"Verification decisions matched: {matched.sum()}")
    print(f"Unmatched queue rows: {(~matched).sum()}")
    print("\nIndependent verification status:")
    print(out["Independent_Verification_Status"].value_counts().to_string())
    print("\nCurator decision:")
    print(out["Curator_Decision"].value_counts().to_string())
    print(f"\nWritten: {args.output}")

if __name__ == "__main__":
    main()
