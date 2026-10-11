#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymysql


def norm(x):
    x = str(x or "").strip()
    x = x.replace("_", " ").replace("–", "-").replace("—", "-")
    x = re.sub(r"\s+", " ", x)
    return x.lower()


def find_col(fieldnames, candidates):
    lookup = {norm(x): x for x in fieldnames}
    for c in candidates:
        if norm(c) in lookup:
            return lookup[norm(c)]
    return None


def inheritance_categories(value):
    """
    Map only explicit inheritance wording into the ODDB web vocabulary.
    One disease may legitimately map to more than one inheritance class.
    """
    n = norm(value)
    cats = set()
    if not n:
        return cats

    if "autosomal dominant" in n or n in {"ad", "dominant"}:
        cats.add("INH-01")
    if "autosomal recessive" in n or n in {"ar", "recessive"}:
        cats.add("INH-02")
    if "isolated" in n or "sporadic" in n:
        cats.add("INH-03")
    if "mitochondrial" in n or "maternal inheritance" in n:
        cats.add("INH-04")
    if "x-linked dominant" in n or "x linked dominant" in n or n in {"xld", "xd"}:
        cats.add("INH-06")
    if "x-linked recessive" in n or "x linked recessive" in n or n in {"xlr", "xr"}:
        cats.add("INH-07")

    # Generic or non-Mendelian labels remain explicit "Other".
    if not cats and n in {
        "other", "unknown", "various", "mixed", "multifactorial",
        "complex", "digenic", "oligogenic", "x-linked", "x linked", "xl",
    }:
        cats.add("INH-05")

    return cats


def split_inheritance(value):
    # Legacy values are usually singular categories. Split only strong delimiters.
    return [x.strip() for x in re.split(r"\s*[|;/]\s*", str(value or "")) if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--legacy-merged",
        required=True,
        help="Legacy/cleaned ODDB TSV containing DiseaseID and Inheritance columns.",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    path = Path(args.legacy_merged)
    if not path.is_file():
        raise SystemExit(f"Legacy TSV not found: {path}")

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
            cur.execute("SELECT disease_id FROM disease")
            valid_ids = {r["disease_id"] for r in cur.fetchall()}

            # Historical/retired ODDB IDs may be preserved as Disease_Alias.source_id.
            cur.execute("""
                SELECT source_id, disease_id
                FROM disease_alias
                WHERE source_id IS NOT NULL
                  AND source_id LIKE 'ODDB-%'
            """)
            old_to_current = {
                r["source_id"]: r["disease_id"] for r in cur.fetchall()
            }

            # Known frozen retirement retained from ODDB curation.
            old_to_current.setdefault("ODDB-76", "ODDB-225")

            # Delete inheritance memberships only; keep anatomy memberships intact.
            cur.execute("""
                DELETE m
                FROM disease_category_membership m
                JOIN disease_category c ON c.category_id=m.category_id
                WHERE c.category_system='inheritance'
            """)
            conn.commit()

            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                if not reader.fieldnames:
                    raise SystemExit("Legacy TSV has no header.")

                disease_col = find_col(
                    reader.fieldnames,
                    ["DiseaseID", "Disease_ID", "Disease ID"],
                )
                inheritance_col = find_col(
                    reader.fieldnames,
                    ["Inheritance", "Mode_of_Inheritance", "Mode of Inheritance"],
                )
                disease_name_col = find_col(
                    reader.fieldnames,
                    ["DiseaseName", "Disease_Name", "Disease Name", "Disease"],
                )

                if not disease_col or not inheritance_col:
                    raise SystemExit(
                        "Required columns not found.\n"
                        f"Headers: {reader.fieldnames}\n"
                        f"Disease column: {disease_col}\n"
                        f"Inheritance column: {inheritance_col}"
                    )

                raw_values = Counter()
                unresolved_values = Counter()
                unresolved_diseases = Counter()
                evidence = defaultdict(lambda: defaultdict(set))

                for row in reader:
                    did = str(row.get(disease_col, "") or "").strip()
                    inh = str(row.get(inheritance_col, "") or "").strip()
                    dname = str(row.get(disease_name_col, "") or "").strip() if disease_name_col else ""

                    if not did or not inh:
                        continue

                    current_id = did if did in valid_ids else old_to_current.get(did)
                    if not current_id:
                        unresolved_diseases[(did, dname)] += 1
                        continue

                    for piece in split_inheritance(inh):
                        raw_values[piece] += 1
                        cats = inheritance_categories(piece)
                        if not cats:
                            unresolved_values[piece] += 1
                            continue
                        for cid in cats:
                            evidence[current_id][cid].add(piece)

            inserted = 0
            for did, categories in sorted(evidence.items()):
                for cid, values in sorted(categories.items()):
                    basis = "legacy Inheritance=" + " | ".join(sorted(values))
                    cur.execute(
                        """
                        INSERT INTO disease_category_membership
                          (disease_id, category_id, membership_basis,
                           source, curation_status)
                        VALUES (%s,%s,%s,'ODDB legacy merged table','mapped')
                        ON DUPLICATE KEY UPDATE
                          membership_basis=VALUES(membership_basis),
                          source=VALUES(source),
                          curation_status=VALUES(curation_status)
                        """,
                        (did, cid, basis),
                    )
                    inserted += 1

            conn.commit()

            print("ODDB v1 LEGACY INHERITANCE BACKFILL v0.3.2")
            print(f"Legacy source: {path}")
            print(f"Unique diseases with mapped inheritance: {len(evidence):,}")
            print(f"Inheritance memberships inserted: {inserted:,}")

            print("\nInheritance category counts:")
            cur.execute("""
                SELECT c.category_name,
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

            print("\nMost common raw legacy inheritance values:")
            for value, n in raw_values.most_common(30):
                print(f"{n:6d}  {value}")

            if unresolved_values:
                print("\nUNMAPPED inheritance values:")
                for value, n in unresolved_values.most_common(30):
                    print(f"{n:6d}  {value}")

            if unresolved_diseases:
                print("\nLegacy disease IDs not resolved to current disease table:")
                for (did, name), n in unresolved_diseases.most_common(30):
                    print(f"{n:6d}  {did}  {name}")

            print("\nDiseases appearing in more than one inheritance category:")
            cur.execute("""
                SELECT d.disease_id,d.disease_name,
                       COUNT(DISTINCT m.category_id) AS category_count,
                       GROUP_CONCAT(
                         DISTINCT c.category_name
                         ORDER BY c.display_order SEPARATOR ' | '
                       ) AS categories
                FROM disease d
                JOIN disease_category_membership m
                  ON m.disease_id=d.disease_id
                JOIN disease_category c
                  ON c.category_id=m.category_id
                WHERE c.category_system='inheritance'
                GROUP BY d.disease_id,d.disease_name
                HAVING COUNT(DISTINCT m.category_id)>1
                ORDER BY category_count DESC,d.disease_name
            """)
            rows = cur.fetchall()
            if not rows:
                print("None")
            else:
                for r in rows:
                    print(
                        f"{r['disease_id']:10s}  "
                        f"{r['disease_name'][:45]:45s}  "
                        f"{r['categories']}"
                    )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
