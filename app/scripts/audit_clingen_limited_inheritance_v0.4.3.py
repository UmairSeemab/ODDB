#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path

import pymysql


CATEGORY_ORDER = [
    "Autosomal dominant",
    "Autosomal recessive",
    "Mitochondrial",
    "Other",
    "X-linked dominant",
    "X-linked recessive",
]


def read_tsv(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"File not found: {p}")
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--limited",
        default="reports/web_taxonomy_inheritance_clingen_v0.4.2/"
                "clingen_limited_exact_mondo_candidates.tsv",
    )
    ap.add_argument(
        "--missing",
        default="reports/web_taxonomy_inheritance_clingen_v0.4.2/"
                "still_missing_after_clingen.tsv",
    )
    ap.add_argument(
        "--combined",
        default="reports/web_taxonomy_inheritance_clingen_v0.4.2/"
                "combined_inheritance_memberships.tsv",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_clingen_limited_audit_v0.4.3",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    limited_rows = read_tsv(args.limited)
    missing_rows = read_tsv(args.missing)
    combined_rows = read_tsv(args.combined)

    missing_ids = {r["DiseaseID"] for r in missing_rows}
    already_classified = {r["DiseaseID"] for r in combined_rows}

    by_disease = defaultdict(list)
    for r in limited_rows:
        by_disease[r["DiseaseID"]].append(r)

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

    try:
        with conn.cursor() as cur:
            # DGA counts per disease help distinguish genetically characterized
            # diseases from diseases that currently have no gene-association evidence.
            cur.execute("""
                SELECT disease_id, COUNT(*) AS n
                FROM disease_gene_association
                GROUP BY disease_id
            """)
            dga_counts = {r["disease_id"]: int(r["n"]) for r in cur.fetchall()}

            cur.execute("""
                SELECT disease_id, COUNT(*) AS n
                FROM disease_variant_association
                GROUP BY disease_id
            """)
            dva_counts = {r["disease_id"]: int(r["n"]) for r in cur.fetchall()}

            cur.execute("SELECT disease_id, disease_name FROM disease")
            disease_names = {r["disease_id"]: r["disease_name"] for r in cur.fetchall()}

        unique_limited_diseases = set(by_disease)
        new_candidate_ids = unique_limited_diseases & missing_ids
        overlap_ids = unique_limited_diseases & already_classified

        consistent_new = []
        conflicting_new = []
        category_counts = Counter()

        for did in sorted(new_candidate_ids):
            rows = by_disease[did]
            cats = sorted({r["Mapped_Category"] for r in rows if r["Mapped_Category"]})
            mois = sorted({r["MOI"] for r in rows if r["MOI"]})
            genes = sorted({r["Gene"] for r in rows if r["Gene"]})
            hgncs = sorted({r["HGNC"] for r in rows if r["HGNC"]})
            mondos = sorted({r["MONDO"] for r in rows if r["MONDO"]})
            reports = sorted({r["Online_Report"] for r in rows if r["Online_Report"]})

            record = {
                "DiseaseID": did,
                "Disease_Name": disease_names.get(did, ""),
                "Categories": " | ".join(cats),
                "MOIs": " | ".join(mois),
                "Genes": " | ".join(genes),
                "HGNCs": " | ".join(hgncs),
                "MONDOs": " | ".join(mondos),
                "Limited_Row_Count": len(rows),
                "DGA_Count": dga_counts.get(did, 0),
                "DVA_Count": dva_counts.get(did, 0),
                "Report_Count": len(reports),
            }

            if len(cats) == 1:
                consistent_new.append(record)
                category_counts[cats[0]] += 1
            else:
                conflicting_new.append(record)

        # What remains if we hypothetically accepted only consistent limited candidates?
        hypothetical_covered = already_classified | {r["DiseaseID"] for r in consistent_new}
        all_current = set(disease_names)
        hypothetical_missing = all_current - hypothetical_covered

        print("ODDB v1 CLINGEN LIMITED INHERITANCE AUDIT v0.4.3")
        print("=" * 82)
        print(f"ClinGen Limited rows: {len(limited_rows):,}")
        print(f"Unique diseases represented by Limited rows: {len(unique_limited_diseases):,}")
        print(f"Limited diseases already classified by strict/other evidence: {len(overlap_ids):,}")
        print(f"Limited diseases among the 92 currently missing: {len(new_candidate_ids):,}")
        print(f"Missing diseases with one consistent Limited category: {len(consistent_new):,}")
        print(f"Missing diseases with conflicting/multiple Limited categories: {len(conflicting_new):,}")
        print(f"Hypothetical coverage if consistent Limited candidates were accepted: "
              f"{len(hypothetical_covered):,} / {len(all_current):,}")
        print(f"Hypothetical still missing: {len(hypothetical_missing):,}")

        print("\nConsistent Limited candidates by category:")
        for cat in CATEGORY_ORDER:
            print(f"{cat:28s} {category_counts[cat]:4d}")

        if consistent_new:
            print("\nConsistent Limited candidates:")
            for r in consistent_new:
                print(
                    f"{r['DiseaseID']:10s}  {r['Disease_Name'][:42]:42s}  "
                    f"{r['Categories']:22s}  genes={r['Genes']}  "
                    f"DGA={r['DGA_Count']} DVA={r['DVA_Count']}"
                )

        if conflicting_new:
            print("\nConflicting/multiple-category Limited candidates:")
            for r in conflicting_new:
                print(
                    f"{r['DiseaseID']:10s}  {r['Disease_Name'][:42]:42s}  "
                    f"{r['Categories']}  genes={r['Genes']}"
                )

        report_dir = Path(args.report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)

        cols = [
            "DiseaseID", "Disease_Name", "Categories", "MOIs", "Genes", "HGNCs",
            "MONDOs", "Limited_Row_Count", "DGA_Count", "DVA_Count", "Report_Count"
        ]

        with (report_dir / "consistent_limited_new_diseases.tsv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
            w.writeheader()
            w.writerows(consistent_new)

        with (report_dir / "conflicting_limited_new_diseases.tsv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
            w.writeheader()
            w.writerows(conflicting_new)

        with (report_dir / "still_missing_if_consistent_limited_accepted.tsv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["DiseaseID", "Disease_Name", "DGA_Count", "DVA_Count"])
            for did in sorted(hypothetical_missing):
                w.writerow([
                    did,
                    disease_names.get(did, ""),
                    dga_counts.get(did, 0),
                    dva_counts.get(did, 0),
                ])

        print("\nReports:")
        print(report_dir / "consistent_limited_new_diseases.tsv")
        print(report_dir / "conflicting_limited_new_diseases.tsv")
        print(report_dir / "still_missing_if_consistent_limited_accepted.tsv")
        print("\nREAD-ONLY: MySQL was not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
