#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

import pymysql


def read_missing(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"Missing-disease report not found: {p}")

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["DiseaseID"] for r in rows if r.get("DiseaseID")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--missing",
        default="reports/web_taxonomy_inheritance_hpo_v0.4.4/"
                "still_missing_after_hpo.tsv",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_missing_audit_v0.4.5",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    missing_ids = read_missing(args.missing)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

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
            cur.execute("SHOW COLUMNS FROM disease")
            disease_cols = {r["Field"] for r in cur.fetchall()}

            select_cols = ["disease_id", "disease_name"]
            for c in [
                "mondo_id", "omim_id", "orphanet_id", "cui",
                "localization", "category"
            ]:
                if c in disease_cols:
                    select_cols.append(c)

            cur.execute(
                "SELECT " + ",".join(f"`{c}`" for c in select_cols) +
                " FROM disease"
            )
            disease_rows = {
                r["disease_id"]: r
                for r in cur.fetchall()
                if r["disease_id"] in missing_ids
            }

            # DGA + gene symbols
            cur.execute("""
                SELECT dga.disease_id,
                       COUNT(*) AS dga_count,
                       GROUP_CONCAT(DISTINCT g.gene_symbol
                                    ORDER BY g.gene_symbol SEPARATOR '|') AS genes
                FROM disease_gene_association dga
                LEFT JOIN gene g ON g.hgnc_id = dga.hgnc_id
                GROUP BY dga.disease_id
            """)
            dga = {
                r["disease_id"]: {
                    "count": int(r["dga_count"]),
                    "genes": r["genes"] or ""
                }
                for r in cur.fetchall()
            }

            # DVA
            cur.execute("""
                SELECT disease_id, COUNT(*) AS n
                FROM disease_variant_association
                GROUP BY disease_id
            """)
            dva = {r["disease_id"]: int(r["n"]) for r in cur.fetchall()}

            # Direct drug evidence
            cur.execute("""
                SELECT disease_id, COUNT(*) AS n
                FROM disease_drug_association
                GROUP BY disease_id
            """)
            dda = {r["disease_id"]: int(r["n"]) for r in cur.fetchall()}

            # Clinical trials
            cur.execute("""
                SELECT disease_id, COUNT(*) AS n
                FROM disease_clinical_trial_association
                GROUP BY disease_id
            """)
            trials = {r["disease_id"]: int(r["n"]) for r in cur.fetchall()}

            # Anatomy web categories
            cur.execute("""
                SELECT m.disease_id,
                       GROUP_CONCAT(DISTINCT c.category_name
                                    ORDER BY c.display_order SEPARATOR '|') AS anatomy_categories
                FROM disease_category_membership m
                JOIN disease_category c ON c.category_id = m.category_id
                WHERE c.category_system = 'anatomy'
                GROUP BY m.disease_id
            """)
            anatomy = {
                r["disease_id"]: r["anatomy_categories"] or ""
                for r in cur.fetchall()
            }

        records = []
        for did in sorted(missing_ids):
            d = disease_rows.get(did, {})
            gcount = dga.get(did, {}).get("count", 0)
            genes = dga.get(did, {}).get("genes", "")
            vcount = dva.get(did, 0)

            # Audit buckets only; these are NOT inheritance assignments.
            if gcount > 0 and vcount > 0:
                priority = "A_genetic_gene_and_variant"
            elif gcount > 0:
                priority = "B_genetic_gene_only"
            elif vcount > 0:
                priority = "C_variant_without_DGA"
            else:
                priority = "D_no_current_gene_or_variant"

            records.append({
                "DiseaseID": did,
                "Disease_Name": d.get("disease_name", ""),
                "Audit_Priority": priority,
                "DGA_Count": gcount,
                "Genes": genes,
                "DVA_Count": vcount,
                "Direct_Drug_Count": dda.get(did, 0),
                "Clinical_Trial_Count": trials.get(did, 0),
                "Anatomy_Categories": anatomy.get(did, ""),
                "MONDO_ID": d.get("mondo_id", ""),
                "OMIM_ID": d.get("omim_id", ""),
                "Orphanet_ID": d.get("orphanet_id", ""),
                "CUI": d.get("cui", ""),
            })

        bucket_counts = defaultdict(int)
        for r in records:
            bucket_counts[r["Audit_Priority"]] += 1

        print("ODDB v1 MISSING INHERITANCE AUDIT v0.4.5")
        print("=" * 82)
        print(f"Missing diseases supplied: {len(missing_ids):,}")
        print(f"Missing diseases found in current disease table: {len(records):,}")

        print("\nPriority groups:")
        for key in [
            "A_genetic_gene_and_variant",
            "B_genetic_gene_only",
            "C_variant_without_DGA",
            "D_no_current_gene_or_variant",
        ]:
            print(f"{key:32s} {bucket_counts[key]:4d}")

        print("\nHighest-priority diseases (gene + variant evidence):")
        shown = 0
        for r in records:
            if r["Audit_Priority"] == "A_genetic_gene_and_variant":
                print(
                    f"{r['DiseaseID']:10s}  {r['Disease_Name'][:45]:45s} "
                    f"DGA={r['DGA_Count']:3d}  DVA={r['DVA_Count']:6d}  "
                    f"Genes={r['Genes'][:65]}"
                )
                shown += 1
                if shown >= 30:
                    break

        fieldnames = [
            "DiseaseID", "Disease_Name", "Audit_Priority",
            "DGA_Count", "Genes", "DVA_Count",
            "Direct_Drug_Count", "Clinical_Trial_Count",
            "Anatomy_Categories",
            "MONDO_ID", "OMIM_ID", "Orphanet_ID", "CUI",
        ]

        with (report_dir / "missing_inheritance_profile.tsv").open(
            "w", encoding="utf-8", newline=""
        ) as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(records)

        for bucket in [
            "A_genetic_gene_and_variant",
            "B_genetic_gene_only",
            "C_variant_without_DGA",
            "D_no_current_gene_or_variant",
        ]:
            with (report_dir / f"{bucket}.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
                w.writeheader()
                w.writerows(r for r in records if r["Audit_Priority"] == bucket)

        print("\nReports:")
        print(report_dir / "missing_inheritance_profile.tsv")
        print(report_dir / "A_genetic_gene_and_variant.tsv")
        print(report_dir / "B_genetic_gene_only.tsv")
        print(report_dir / "C_variant_without_DGA.tsv")
        print(report_dir / "D_no_current_gene_or_variant.tsv")
        print("\nREAD-ONLY: MySQL was not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
