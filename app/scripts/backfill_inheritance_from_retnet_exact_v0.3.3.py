#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymysql


CATEGORY_NAMES = {
    "INH-01": "Autosomal dominant",
    "INH-02": "Autosomal recessive",
    "INH-03": "Isolated cases",
    "INH-04": "Mitochondrial",
    "INH-05": "Other",
    "INH-06": "X-linked dominant",
    "INH-07": "X-linked recessive",
}


def norm(x):
    x = str(x or "").strip()
    x = x.replace("_", " ").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", x).lower()


def map_inheritance(value):
    """
    Conservative mapping. Generic X-linked is not assumed dominant/recessive.
    Unknown/unmapped is not forced into Other.
    """
    n = norm(value)
    out = set()
    if not n:
        return out

    if "autosomal dominant" in n or n in {"ad", "dominant"}:
        out.add("INH-01")
    if "autosomal recessive" in n or n in {"ar", "recessive"}:
        out.add("INH-02")
    if "isolated" in n or "sporadic" in n:
        out.add("INH-03")
    if "mitochondrial" in n or "maternal inheritance" in n:
        out.add("INH-04")
    if "x-linked dominant" in n or "x linked dominant" in n or n in {"xld", "xd"}:
        out.add("INH-06")
    if "x-linked recessive" in n or "x linked recessive" in n or n in {"xlr", "xr"}:
        out.add("INH-07")

    if not out and n in {
        "other", "complex", "multifactorial", "digenic", "oligogenic",
        "various", "mixed", "non-mendelian", "x-linked", "x linked", "xl",
    }:
        out.add("INH-05")

    return out


def split_values(value):
    return [x.strip() for x in re.split(r"\s*[|;/]\s*", str(value or "")) if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retnet", required=True,
                    help="RetNet-to-ODDB candidate TSV with ODDB_DiseaseID, Inheritance and Disease_Match_Status.")
    ap.add_argument("--report-dir", default="reports/web_taxonomy_inheritance_v0.3.3")
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    retnet_path = Path(args.retnet)
    if not retnet_path.is_file():
        raise SystemExit(f"RetNet TSV not found: {retnet_path}")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.database, charset="utf8mb4", autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

    evidence = defaultdict(lambda: defaultdict(list))
    raw_counts = Counter()
    unmapped_raw = Counter()
    skipped_status = Counter()
    unknown_disease_ids = Counter()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT disease_id,disease_name,inheritance FROM disease")
            disease_rows = cur.fetchall()
            disease_by_id = {r["disease_id"]: r for r in disease_rows}
            valid_ids = set(disease_by_id)

            # 1) Rebuild inheritance memberships only.
            cur.execute("""
                DELETE m
                FROM disease_category_membership m
                JOIN disease_category c ON c.category_id=m.category_id
                WHERE c.category_system='inheritance'
            """)
            conn.commit()

            # 2) Preserve any explicit inheritance already present in frozen Disease.
            for d in disease_rows:
                for raw in split_values(d.get("inheritance")):
                    cats = map_inheritance(raw)
                    raw_counts[raw] += 1
                    if not cats:
                        unmapped_raw[raw] += 1
                    for cid in cats:
                        evidence[d["disease_id"]][cid].append(
                            ("ODDB frozen disease.inheritance", raw)
                        )

            # 3) Preserve explicit inheritance in frozen DGA.
            cur.execute("""
                SELECT disease_id,inheritance
                FROM disease_gene_association
                WHERE inheritance IS NOT NULL AND inheritance <> ''
            """)
            for r in cur.fetchall():
                for raw in split_values(r["inheritance"]):
                    cats = map_inheritance(raw)
                    raw_counts[raw] += 1
                    if not cats:
                        unmapped_raw[raw] += 1
                    for cid in cats:
                        evidence[r["disease_id"]][cid].append(
                            ("ODDB frozen DGA.inheritance", raw)
                        )

            # 4) RetNet exact disease mappings only.
            with retnet_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                required = {"ODDB_DiseaseID", "Inheritance", "Disease_Match_Status"}
                missing = required.difference(reader.fieldnames or [])
                if missing:
                    raise SystemExit(
                        f"RetNet source is missing required columns: {sorted(missing)}\n"
                        f"Headers: {reader.fieldnames}"
                    )

                for row in reader:
                    did = str(row.get("ODDB_DiseaseID") or "").strip()
                    raw = str(row.get("Inheritance") or "").strip()
                    status = norm(row.get("Disease_Match_Status"))

                    if not did or not raw:
                        continue

                    # Critical safety rule: only exact mappings to a current ODDB disease.
                    if status != "exact":
                        skipped_status[status or "<blank>"] += 1
                        continue

                    if did not in valid_ids:
                        unknown_disease_ids[did] += 1
                        continue

                    for piece in split_values(raw):
                        raw_counts[piece] += 1
                        cats = map_inheritance(piece)
                        if not cats:
                            unmapped_raw[piece] += 1
                            continue

                        for cid in cats:
                            evidence[did][cid].append(
                                ("RetNet exact disease mapping", piece)
                            )

            # 5) Insert one disease/category membership with provenance.
            inserted = 0
            for did, cats in sorted(evidence.items()):
                for cid, evs in sorted(cats.items()):
                    # Deduplicate evidence labels.
                    seen = []
                    for src, raw in evs:
                        item = f"{src}: {raw}"
                        if item not in seen:
                            seen.append(item)
                    basis = " || ".join(seen)[:255]

                    source_types = {src for src, _ in evs}
                    if source_types == {"RetNet exact disease mapping"}:
                        source = "RetNet exact disease mapping"
                    elif "RetNet exact disease mapping" in source_types:
                        source = "ODDB frozen + RetNet exact mapping"
                    else:
                        source = "ODDB frozen inheritance"

                    cur.execute("""
                        INSERT INTO disease_category_membership
                          (disease_id,category_id,membership_basis,source,curation_status)
                        VALUES (%s,%s,%s,%s,'mapped')
                        ON DUPLICATE KEY UPDATE
                          membership_basis=VALUES(membership_basis),
                          source=VALUES(source),
                          curation_status=VALUES(curation_status)
                    """, (did, cid, basis, source))
                    inserted += 1

            conn.commit()

            # 6) Reports.
            cur.execute("""
                SELECT d.disease_id,d.disease_name,
                       COUNT(DISTINCT m.category_id) AS category_count,
                       GROUP_CONCAT(DISTINCT c.category_name
                         ORDER BY c.display_order SEPARATOR ' | ') AS categories
                FROM disease d
                LEFT JOIN disease_category_membership m ON m.disease_id=d.disease_id
                LEFT JOIN disease_category c
                  ON c.category_id=m.category_id
                 AND c.category_system='inheritance'
                GROUP BY d.disease_id,d.disease_name
                ORDER BY d.disease_name
            """)
            coverage_rows = cur.fetchall()

            missing_rows = [r for r in coverage_rows if int(r["category_count"] or 0) == 0]
            multi_rows = [r for r in coverage_rows if int(r["category_count"] or 0) > 1]

            with (report_dir / "inheritance_missing_diseases.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.writer(f, delimiter="\t")
                w.writerow(["DiseaseID", "Disease_Name"])
                for r in missing_rows:
                    w.writerow([r["disease_id"], r["disease_name"]])

            with (report_dir / "inheritance_multi_category_diseases.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.writer(f, delimiter="\t")
                w.writerow(["DiseaseID", "Disease_Name", "Category_Count", "Categories"])
                for r in multi_rows:
                    w.writerow([
                        r["disease_id"], r["disease_name"],
                        r["category_count"], r["categories"],
                    ])

            print("ODDB v1 INHERITANCE BACKFILL v0.3.3")
            print("=" * 72)
            print(f"RetNet source: {retnet_path}")
            print("Safety rule: RetNet rows used only when Disease_Match_Status = exact")
            print(f"Inheritance memberships inserted: {inserted:,}")

            print("\nInheritance category counts:")
            cur.execute("""
                SELECT c.category_id,c.category_name,
                       COUNT(DISTINCT m.disease_id) AS n
                FROM disease_category c
                LEFT JOIN disease_category_membership m
                  ON m.category_id=c.category_id
                WHERE c.category_system='inheritance'
                GROUP BY c.category_id,c.category_name,c.display_order
                ORDER BY c.display_order
            """)
            for r in cur.fetchall():
                print(f"{r['category_name']:28s} {r['n']:4d}")

            covered = len(coverage_rows) - len(missing_rows)
            print(f"\nDiseases with >=1 inheritance category: {covered:,} / {len(coverage_rows):,}")
            print(f"Diseases without inheritance category: {len(missing_rows):,}")
            print(f"Diseases in >1 inheritance category: {len(multi_rows):,}")

            print("\nRaw inheritance values seen:")
            for raw, n in raw_counts.most_common():
                print(f"{n:6d}  {raw}")

            if unmapped_raw:
                print("\nUNMAPPED raw inheritance values (not forced into Other):")
                for raw, n in unmapped_raw.most_common():
                    print(f"{n:6d}  {raw}")

            if skipped_status:
                print("\nRetNet rows skipped because disease mapping was not exact:")
                for status, n in skipped_status.most_common():
                    print(f"{n:6d}  {status}")

            if unknown_disease_ids:
                print("\nExact-mapped RetNet ODDB IDs absent from current disease table:")
                for did, n in unknown_disease_ids.most_common():
                    print(f"{n:6d}  {did}")

            print("\nReports:")
            print(report_dir / "inheritance_missing_diseases.tsv")
            print(report_dir / "inheritance_multi_category_diseases.tsv")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
