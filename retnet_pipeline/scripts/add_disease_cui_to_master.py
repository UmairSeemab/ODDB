#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd

def clean(x):
    return str(x or "").strip()

def unique_join(values):
    out, seen = [], set()
    for x in values:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return " | ".join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disease-master", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    d = pd.read_csv(args.disease_master, sep="\t", dtype=str).fillna("")
    legacy = pd.read_csv(args.legacy, sep="\t", dtype=str).fillna("")

    if "DiseaseID" not in d.columns:
        raise SystemExit("Disease master must contain DiseaseID.")
    if "DiseaseID" not in legacy.columns or "Disease_UML_CUI" not in legacy.columns:
        raise SystemExit("Legacy file must contain DiseaseID and Disease_UML_CUI.")

    cui = (
        legacy.groupby("DiseaseID")["Disease_UML_CUI"]
        .apply(unique_join)
        .reset_index(name="MedGen_UMLS_CUI")
    )

    out = d.drop(columns=["MedGen_UMLS_CUI"], errors="ignore").merge(
        cui, how="left", on="DiseaseID"
    )
    out["MedGen_UMLS_CUI"] = out["MedGen_UMLS_CUI"].fillna("")

    vals = out["MedGen_UMLS_CUI"].astype(str).str.strip()
    multi = vals.str.contains(r"\|", regex=True)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)

    print("DISEASE CUI ENRICHMENT")
    print("Disease rows:", len(out))
    print("Diseases with MedGen/UMLS CUI:", int(vals.ne("").sum()))
    print("Diseases without MedGen/UMLS CUI:", int(vals.eq("").sum()))
    print("Diseases with multiple legacy CUIs:", int(multi.sum()))
    print("Written:", args.output)

if __name__ == "__main__":
    main()
