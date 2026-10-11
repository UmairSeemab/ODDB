#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import pymysql


EXPECTED_CURRENT_DISEASES = 162
EXPECTED_CLASSIFIED_DISEASES = 73
EXPECTED_TOTAL_MEMBERSHIPS = 115
EXPECTED_MULTI_CATEGORY_DISEASES = 25

CATEGORY_NAMES = {
    "INH-01": "Autosomal dominant",
    "INH-02": "Autosomal recessive",
    "INH-04": "Mitochondrial",
    "INH-05": "Other",
    "INH-06": "X-linked dominant",
    "INH-07": "X-linked recessive",
}

EXPECTED_CATEGORY_COUNTS = {
    "INH-01": 24,
    "INH-02": 50,
    "INH-04": 4,
    "INH-05": 23,
    "INH-06": 2,
    "INH-07": 12,
}


def load_memberships(path: Path):
    if not path.is_file():
        raise SystemExit(f"Membership file not found: {path}")

    memberships = defaultdict(dict)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {
            "DiseaseID", "Category_ID", "Category_Name",
            "Evidence_Count", "Sources", "Raw_Values", "Evidence_JSON"
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                "Membership file is missing required columns: "
                + ", ".join(sorted(missing))
            )

        for row_no, row in enumerate(reader, start=2):
            did = (row.get("DiseaseID") or "").strip()
            cid = (row.get("Category_ID") or "").strip()

            if not did or not cid:
                raise SystemExit(f"Blank DiseaseID/Category_ID at line {row_no}")

            if cid == "INH-03":
                raise SystemExit(
                    f"Unexpected deprecated Isolated cases category INH-03 at line {row_no}"
                )

            if cid not in CATEGORY_NAMES:
                raise SystemExit(
                    f"Unexpected inheritance category {cid!r} at line {row_no}"
                )

            if (row.get("Category_Name") or "").strip() != CATEGORY_NAMES[cid]:
                raise SystemExit(
                    f"Category name mismatch at line {row_no}: "
                    f"{cid} != {row.get('Category_Name')!r}"
                )

            key = (did, cid)
            if cid in memberships[did]:
                raise SystemExit(
                    f"Duplicate disease/category membership in input: {did} {cid}"
                )

            ev_json = (row.get("Evidence_JSON") or "").strip()
            try:
                evidence = json.loads(ev_json)
            except Exception as e:
                raise SystemExit(
                    f"Invalid Evidence_JSON for {did} {cid}: {e}"
                )

            if not isinstance(evidence, list) or not evidence:
                raise SystemExit(
                    f"Evidence_JSON must be a non-empty list for {did} {cid}"
                )

            memberships[did][cid] = {
                "category_name": CATEGORY_NAMES[cid],
                "evidence_count": int(row.get("Evidence_Count") or len(evidence)),
                "sources": (row.get("Sources") or "").strip(),
                "raw_values": (row.get("Raw_Values") or "").strip(),
                "evidence": evidence,
            }

    return memberships


def main():
    ap = argparse.ArgumentParser(
        description="Finalize the validated ODDB v1 current-disease inheritance taxonomy."
    )
    ap.add_argument(
        "--memberships",
        default="reports/web_taxonomy_inheritance_hpo_v0.4.4/"
                "combined_inheritance_memberships.tsv",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_final_v0.4.7",
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    membership_path = Path(args.memberships)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    memberships = load_memberships(membership_path)

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
            # Current disease universe.
            cur.execute("SELECT disease_id, disease_name FROM disease")
            disease_rows = cur.fetchall()
            current_ids = {r["disease_id"] for r in disease_rows}
            name_by_id = {r["disease_id"]: r["disease_name"] for r in disease_rows}

            unknown_ids = sorted(set(memberships) - current_ids)
            if unknown_ids:
                raise SystemExit(
                    "Input contains DiseaseIDs not present in current ODDB v1: "
                    + ", ".join(unknown_ids[:20])
                )

            # Validate category seed rows.
            cur.execute("""
                SELECT category_id, category_name, category_system, display_order
                FROM disease_category
                WHERE category_system='inheritance'
                ORDER BY display_order, category_id
            """)
            db_categories = cur.fetchall()
            db_by_id = {r["category_id"]: r for r in db_categories}

            missing_categories = sorted(set(CATEGORY_NAMES) - set(db_by_id))
            if missing_categories:
                raise SystemExit(
                    "Required inheritance categories missing from disease_category: "
                    + ", ".join(missing_categories)
                )

            wrong_names = []
            for cid, expected_name in CATEGORY_NAMES.items():
                actual = db_by_id[cid]["category_name"]
                if actual != expected_name:
                    wrong_names.append(f"{cid}: {actual!r} != {expected_name!r}")
            if wrong_names:
                raise SystemExit(
                    "Inheritance category names do not match expected values:\n"
                    + "\n".join(wrong_names)
                )

            # The old unused category may still exist; it must have zero memberships.
            if "INH-03" in db_by_id:
                cur.execute("""
                    SELECT COUNT(*) AS n
                    FROM disease_category_membership
                    WHERE category_id='INH-03'
                """)
                n_inh03 = int(cur.fetchone()["n"])
                if n_inh03 != 0:
                    raise SystemExit(
                        f"INH-03 Isolated cases still has {n_inh03} membership(s); "
                        "refusing to finalize."
                    )

            classified_ids = set(memberships)
            total_memberships = sum(len(cats) for cats in memberships.values())
            multi_ids = {
                did for did, cats in memberships.items()
                if len(cats) > 1
            }
            unclassified_ids = current_ids - classified_ids

            category_counts = Counter()
            for did, cats in memberships.items():
                for cid in cats:
                    category_counts[cid] += 1

            problems = []

            if len(current_ids) != EXPECTED_CURRENT_DISEASES:
                problems.append(
                    f"Current disease count {len(current_ids)} != "
                    f"{EXPECTED_CURRENT_DISEASES}"
                )

            if len(classified_ids) != EXPECTED_CLASSIFIED_DISEASES:
                problems.append(
                    f"Classified disease count {len(classified_ids)} != "
                    f"{EXPECTED_CLASSIFIED_DISEASES}"
                )

            if total_memberships != EXPECTED_TOTAL_MEMBERSHIPS:
                problems.append(
                    f"Total membership count {total_memberships} != "
                    f"{EXPECTED_TOTAL_MEMBERSHIPS}"
                )

            if len(multi_ids) != EXPECTED_MULTI_CATEGORY_DISEASES:
                problems.append(
                    f"Multi-category disease count {len(multi_ids)} != "
                    f"{EXPECTED_MULTI_CATEGORY_DISEASES}"
                )

            for cid, expected in EXPECTED_CATEGORY_COUNTS.items():
                if category_counts[cid] != expected:
                    problems.append(
                        f"{cid} {CATEGORY_NAMES[cid]} count "
                        f"{category_counts[cid]} != {expected}"
                    )

            print("ODDB v1 FINAL INHERITANCE TAXONOMY v0.4.7")
            print("=" * 84)
            print(f"Membership source: {membership_path}")
            print(f"Current canonical diseases: {len(current_ids):,}")
            print(f"Classified diseases: {len(classified_ids):,}")
            print(f"Unclassified diseases: {len(unclassified_ids):,}")
            print(f"Total disease/category memberships: {total_memberships:,}")
            print(f"Diseases with >1 inheritance category: {len(multi_ids):,}")

            print("\nFinal category counts:")
            for cid in CATEGORY_NAMES:
                print(
                    f"{cid:6s}  {CATEGORY_NAMES[cid]:28s} "
                    f"{category_counts[cid]:4d}"
                )

            if problems:
                print("\nVALIDATION FAILED:")
                for p in problems:
                    print(" -", p)
                raise SystemExit(
                    "\nNo database changes were made because the final validated "
                    "inheritance state did not match expectations."
                )

            print("\nValidation against expected final state: PASSED")

            # Final reports.
            with (report_dir / "final_inheritance_memberships.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow([
                    "DiseaseID", "Disease_Name", "Category_ID", "Category_Name",
                    "Evidence_Count", "Sources", "Raw_Values", "Evidence_JSON"
                ])
                for did in sorted(memberships):
                    for cid in sorted(memberships[did]):
                        m = memberships[did][cid]
                        writer.writerow([
                            did,
                            name_by_id.get(did, ""),
                            cid,
                            m["category_name"],
                            m["evidence_count"],
                            m["sources"],
                            m["raw_values"],
                            json.dumps(m["evidence"], ensure_ascii=False),
                        ])

            with (report_dir / "final_unclassified_diseases.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow([
                    "DiseaseID", "Disease_Name",
                    "Inheritance_Status"
                ])
                for did in sorted(unclassified_ids):
                    writer.writerow([
                        did,
                        name_by_id.get(did, ""),
                        "not_classified",
                    ])

            with (report_dir / "final_multi_category_diseases.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow([
                    "DiseaseID", "Disease_Name", "Categories"
                ])
                for did in sorted(multi_ids):
                    writer.writerow([
                        did,
                        name_by_id.get(did, ""),
                        " | ".join(
                            CATEGORY_NAMES[cid]
                            for cid in sorted(memberships[did])
                        ),
                    ])

            summary = {
                "release": "ODDB v1",
                "taxonomy_version": "v0.4.7",
                "current_diseases": len(current_ids),
                "classified_diseases": len(classified_ids),
                "unclassified_diseases": len(unclassified_ids),
                "memberships": total_memberships,
                "multi_category_diseases": len(multi_ids),
                "category_counts": {
                    CATEGORY_NAMES[cid]: category_counts[cid]
                    for cid in CATEGORY_NAMES
                },
                "source_membership_file": str(membership_path),
                "important_semantics": [
                    "Only direct supported disease-level inheritance memberships are included.",
                    "ClinGen Limited evidence did not add any new disease classifications.",
                    "MONDO subtype-supported inheritance was not promoted to direct disease-level inheritance.",
                    "Absence of a membership means not classified; it does not mean not applicable.",
                    "INH-03 Isolated cases is deprecated and excluded from the public taxonomy."
                ],
            }

            with (report_dir / "final_inheritance_summary.json").open(
                "w", encoding="utf-8"
            ) as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            print("\nFinal reports:")
            for fn in [
                "final_inheritance_memberships.tsv",
                "final_unclassified_diseases.tsv",
                "final_multi_category_diseases.tsv",
                "final_inheritance_summary.json",
            ]:
                print(report_dir / fn)

            if not args.apply:
                print("\nPREVIEW ONLY — MySQL was not modified.")
                print("Run again with --apply after reviewing this final validation.")
                return

            # Determine columns in web-support membership table.
            cur.execute("SHOW COLUMNS FROM disease_category_membership")
            membership_columns = {r["Field"] for r in cur.fetchall()}

            required_cols = {"disease_id", "category_id"}
            if not required_cols.issubset(membership_columns):
                raise SystemExit(
                    "disease_category_membership is missing disease_id/category_id."
                )

            # Replace inheritance memberships only; anatomy is untouched.
            cur.execute("""
                DELETE m
                FROM disease_category_membership m
                JOIN disease_category c
                  ON c.category_id = m.category_id
                WHERE c.category_system='inheritance'
            """)

            # Remove obsolete zero-membership category after deleting inheritance
            # memberships, if it still exists.
            cur.execute("""
                DELETE FROM disease_category
                WHERE category_id='INH-03'
                  AND category_system='inheritance'
            """)

            # Reorder the six final categories for public display.
            display_orders = {
                "INH-01": 1,
                "INH-02": 2,
                "INH-04": 3,
                "INH-05": 4,
                "INH-06": 5,
                "INH-07": 6,
            }

            cur.execute("SHOW COLUMNS FROM disease_category")
            category_columns = {r["Field"] for r in cur.fetchall()}
            if "display_order" in category_columns:
                for cid, order in display_orders.items():
                    cur.execute(
                        "UPDATE disease_category "
                        "SET display_order=%s WHERE category_id=%s",
                        (order, cid),
                    )

            inserted = 0
            for did in sorted(memberships):
                for cid in sorted(memberships[did]):
                    m = memberships[did][cid]

                    columns = ["disease_id", "category_id"]
                    values = [did, cid]

                    if "membership_basis" in membership_columns:
                        columns.append("membership_basis")
                        values.append(
                            (
                                "direct supported inheritance; sources="
                                + m["sources"]
                                + "; raw="
                                + m["raw_values"]
                            )[:255]
                        )

                    if "source" in membership_columns:
                        columns.append("source")
                        values.append(
                            "ODDB v1 inheritance finalization v0.4.7"
                        )

                    if "curation_status" in membership_columns:
                        columns.append("curation_status")
                        values.append("supported")

                    placeholders = ",".join(["%s"] * len(columns))
                    col_sql = ",".join(f"`{c}`" for c in columns)

                    cur.execute(
                        f"INSERT INTO disease_category_membership "
                        f"({col_sql}) VALUES ({placeholders})",
                        values,
                    )
                    inserted += 1

            conn.commit()

            # Post-write validation.
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM disease_category_membership m
                JOIN disease_category c
                  ON c.category_id=m.category_id
                WHERE c.category_system='inheritance'
            """)
            db_memberships = int(cur.fetchone()["n"])

            cur.execute("""
                SELECT COUNT(DISTINCT m.disease_id) AS n
                FROM disease_category_membership m
                JOIN disease_category c
                  ON c.category_id=m.category_id
                WHERE c.category_system='inheritance'
            """)
            db_diseases = int(cur.fetchone()["n"])

            cur.execute("""
                SELECT COUNT(*) AS n
                FROM disease_category
                WHERE category_id='INH-03'
            """)
            inh03_remaining = int(cur.fetchone()["n"])

            if (
                db_memberships != EXPECTED_TOTAL_MEMBERSHIPS
                or db_diseases != EXPECTED_CLASSIFIED_DISEASES
                or inh03_remaining != 0
            ):
                raise SystemExit(
                    "POST-WRITE VALIDATION FAILED: "
                    f"memberships={db_memberships}, "
                    f"classified_diseases={db_diseases}, "
                    f"INH-03 rows={inh03_remaining}"
                )

            print("\nAPPLY PASSED")
            print(f"Inserted inheritance memberships: {inserted:,}")
            print(f"Classified current diseases in MySQL: {db_diseases:,}")
            print(f"Unclassified current diseases: {len(unclassified_ids):,}")
            print("INH-03 Isolated cases removed: yes")
            print("Anatomy memberships and canonical ODDB tables were not changed.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
