#!/usr/bin/env python3
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

def clean(x):
    return str(x or "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unresolved", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    counts = Counter()
    variants = defaultdict(set)
    status_counts = Counter()

    with open(args.unresolved, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        required = {
            "Status",
            "Variant_ID",
            "ClinVar_Phenotype_Name",
            "ClinVar_Phenotype_IDs",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Missing columns: {sorted(missing)}")

        for row in reader:
            status = clean(row["Status"])
            name = clean(row["ClinVar_Phenotype_Name"])
            ids = clean(row["ClinVar_Phenotype_IDs"])
            vid = clean(row["Variant_ID"])

            key = (status, name, ids)
            counts[key] += 1
            if vid:
                variants[key].add(vid)
            status_counts[status] += 1

    rows = []
    for (status, name, ids), n in counts.items():
        rows.append({
            "Status": status,
            "ClinVar_Phenotype_Name": name,
            "ClinVar_Phenotype_IDs": ids,
            "Occurrence_Count": n,
            "Unique_Variant_Count": len(variants[(status, name, ids)]),
        })

    rows.sort(
        key=lambda r: (
            -r["Occurrence_Count"],
            r["Status"],
            r["ClinVar_Phenotype_Name"]
        )
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "Status",
                "ClinVar_Phenotype_Name",
                "ClinVar_Phenotype_IDs",
                "Occurrence_Count",
                "Unique_Variant_Count",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    unique_unmapped = sum(1 for r in rows if r["Status"] == "unmapped")
    unique_ambiguous = sum(1 for r in rows if r["Status"].startswith("ambiguous"))

    print("CLINVAR UNRESOLVED CONCEPT SUMMARY")
    print(f"Unique unresolved concept records: {len(rows):,}")
    print(f"Unique unmapped concepts: {unique_unmapped:,}")
    print(f"Unique ambiguous concepts: {unique_ambiguous:,}")
    print("\nOccurrence counts by status:")
    for k, v in status_counts.most_common():
        print(f"{k}: {v:,}")

    print("\nTop 25 unresolved concepts:")
    for r in rows[:25]:
        print(
            f"{r['Occurrence_Count']:>8,} | "
            f"{r['Unique_Variant_Count']:>8,} variants | "
            f"{r['Status']:<20} | "
            f"{r['ClinVar_Phenotype_Name']} | "
            f"{r['ClinVar_Phenotype_IDs']}"
        )

    print(f"\nWritten: {out}")

if __name__ == "__main__":
    main()
