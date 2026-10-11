#!/usr/bin/env python3
"""
ODDB v1 MySQL post-import validator.

Checks:
  * current frozen-release counts
  * PK/natural-key duplication
  * FK orphans
  * DDA/DDE consistency
  * refined RETINOL correction
  * drug identity review flags
  * target-overlap semantics
  * expected refined release metrics

Dependency:
  pip install pymysql
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
import pymysql


EXPECTED = {
    "disease": 162,
    "gene": 1249,
    "disease_gene_association": 1631,
    "disease_gene_association_reclassified": 1,
    "locus": 2,
    "disease_locus_association": 2,
    "variant": 707315,
    "gene_variant_association": 707315,
    "disease_variant_association": 106838,
    "drug": 805,
    "drug_form_relationship": 99,
    "drug_target_association": 1009,
    "disease_drug_association": 344,
    "disease_drug_evidence": 1142,
    "clinical_report": 1291,
    "disease_clinical_report_association": 1370,
    "drug_clinical_report_association": 1575,
    "clinical_trial": 1164,
    "disease_clinical_trial_association": 1235,
    "drug_clinical_trial_association": 1448,
    "disease_drug_aggregate_context": 157,
    "disease_drug_aggregate_context_demoted": 22,
    "disease_drug_target_overlap": 1322,
    "disease_drug_target_overlap_summary": 1203,
    "disease_drug_direct_without_target_overlap": 317,
}

CHECKS = [
    (
        "gene-variant orphan genes",
        """
        SELECT COUNT(*)
        FROM gene_variant_association x
        LEFT JOIN gene g ON g.hgnc_id=x.hgnc_id
        WHERE g.hgnc_id IS NULL
        """
    ),
    (
        "gene-variant orphan variants",
        """
        SELECT COUNT(*)
        FROM gene_variant_association x
        LEFT JOIN variant v ON v.variant_id=x.variant_id
        WHERE v.variant_id IS NULL
        """
    ),
    (
        "disease-variant orphan diseases",
        """
        SELECT COUNT(*)
        FROM disease_variant_association x
        LEFT JOIN disease d ON d.disease_id=x.disease_id
        WHERE d.disease_id IS NULL
        """
    ),
    (
        "disease-variant orphan variants",
        """
        SELECT COUNT(*)
        FROM disease_variant_association x
        LEFT JOIN variant v ON v.variant_id=x.variant_id
        WHERE v.variant_id IS NULL
        """
    ),
    (
        "disease-locus orphan loci",
        """
        SELECT COUNT(*)
        FROM disease_locus_association x
        LEFT JOIN locus l ON l.locus_id=x.locus_id
        WHERE l.locus_id IS NULL
        """
    ),
    (
        "duplicate DDA disease-drug pairs",
        """
        SELECT COUNT(*) FROM (
          SELECT disease_id, drug_id, COUNT(*) n
          FROM disease_drug_association
          GROUP BY disease_id, drug_id
          HAVING COUNT(*) > 1
        ) x
        """
    ),
    (
        "DDE rows without matching DDA pair",
        """
        SELECT COUNT(*)
        FROM disease_drug_evidence e
        LEFT JOIN disease_drug_association a
          ON a.disease_drug_association_id=e.disease_drug_association_id
         AND a.disease_id=e.disease_id
         AND a.drug_id=e.drug_id
        WHERE a.disease_drug_association_id IS NULL
        """
    ),
    (
        "DDA pairs without evidence",
        """
        SELECT COUNT(*)
        FROM disease_drug_association a
        LEFT JOIN disease_drug_evidence e
          ON e.disease_drug_association_id=a.disease_drug_association_id
        WHERE e.disease_drug_evidence_id IS NULL
        """
    ),
    (
        "drug form self relationships",
        """
        SELECT COUNT(*)
        FROM drug_form_relationship
        WHERE child_drug_id=parent_drug_id
        """
    ),
    (
        "drug form orphan child",
        """
        SELECT COUNT(*)
        FROM drug_form_relationship r
        LEFT JOIN drug d ON d.drug_id=r.child_drug_id
        WHERE d.drug_id IS NULL
        """
    ),
    (
        "drug form orphan parent",
        """
        SELECT COUNT(*)
        FROM drug_form_relationship r
        LEFT JOIN drug d ON d.drug_id=r.parent_drug_id
        WHERE d.drug_id IS NULL
        """
    ),
    (
        "trial-drug links inconsistent with parent report",
        """
        SELECT COUNT(*)
        FROM drug_clinical_trial_association dt
        JOIN clinical_trial ct
          ON ct.clinical_trial_id=dt.clinical_trial_id
        LEFT JOIN drug_clinical_report_association dr
          ON dr.clinical_report_id=ct.clinical_report_id
         AND dr.drug_id=dt.drug_id
        WHERE dr.association_id IS NULL
        """
    ),
    (
        "overlap direct=yes absent from DDA",
        """
        SELECT COUNT(*)
        FROM disease_drug_target_overlap_summary s
        LEFT JOIN disease_drug_association a
          ON a.disease_id=s.disease_id AND a.drug_id=s.drug_id
        WHERE s.direct_disease_drug_evidence=1
          AND a.disease_drug_association_id IS NULL
        """
    ),
    (
        "overlap direct=no present in DDA",
        """
        SELECT COUNT(*)
        FROM disease_drug_target_overlap_summary s
        JOIN disease_drug_association a
          ON a.disease_id=s.disease_id AND a.drug_id=s.drug_id
        WHERE s.direct_disease_drug_evidence=0
        """
    ),
    (
        "direct-without-overlap pair actually overlaps",
        """
        SELECT COUNT(*)
        FROM disease_drug_direct_without_target_overlap x
        JOIN disease_drug_target_overlap_summary s
          ON s.disease_id=x.disease_id AND s.drug_id=x.drug_id
        """
    ),
    (
        "incorrect Night Blindness-TRETINOIN pair retained",
        """
        SELECT COUNT(*)
        FROM disease_drug_association
        WHERE disease_id='ODDB-131'
          AND drug_id='ODDB-DRUG-6B3235E14695'
        """
    ),
    (
        "incorrect ROP-TRETINOIN pair retained",
        """
        SELECT COUNT(*)
        FROM disease_drug_association
        WHERE disease_id='ODDB-195'
          AND drug_id='ODDB-DRUG-6B3235E14695'
        """
    ),
]


def scalar(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    ap.add_argument("--write-db-results", action="store_true")
    args = ap.parse_args()

    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.database, charset="utf8mb4", autocommit=False
    )

    failures = []
    results = []

    try:
        with conn.cursor() as cur:
            print("ODDB v1 MYSQL VALIDATION")
            print("=" * 72)

            print("\nROW COUNTS")
            for table, expected in EXPECTED.items():
                actual = int(scalar(cur, f"SELECT COUNT(*) FROM `{table}`"))
                ok = actual == expected
                print(
                    f"{table:48s} {actual:>9,} "
                    f"{'OK' if ok else f'EXPECTED {expected:,}'}"
                )
                problem = 0 if ok else abs(actual - expected) or 1
                results.append(
                    (f"row_count::{table}", "ERROR", problem,
                     f"expected={expected}; actual={actual}")
                )
                if not ok:
                    failures.append(f"{table} row count")

            print("\nSTRUCTURAL / SEMANTIC CHECKS")
            for name, sql in CHECKS:
                n = int(scalar(cur, sql))
                print(f"{name:60s} {n:>8,} {'OK' if n == 0 else 'FAIL'}")
                results.append((name, "ERROR", n, None))
                if n:
                    failures.append(name)

            # Positive expected refinements
            positives = [
                (
                    "RETINOL entity",
                    """
                    SELECT COUNT(*) FROM drug
                    WHERE UPPER(preferred_name)='RETINOL'
                      AND chembl_id='CHEMBL986'
                    """,
                    1,
                ),
                (
                    "Night Blindness-RETINOL pair",
                    """
                    SELECT COUNT(*)
                    FROM disease_drug_association a
                    JOIN drug d ON d.drug_id=a.drug_id
                    WHERE a.disease_id='ODDB-131'
                      AND UPPER(d.preferred_name)='RETINOL'
                    """,
                    1,
                ),
                (
                    "ROP-RETINOL pair",
                    """
                    SELECT COUNT(*)
                    FROM disease_drug_association a
                    JOIN drug d ON d.drug_id=a.drug_id
                    WHERE a.disease_id='ODDB-195'
                      AND UPPER(d.preferred_name)='RETINOL'
                    """,
                    1,
                ),
                (
                    "RETINOL report remaps",
                    """
                    SELECT COUNT(*)
                    FROM drug_clinical_report_association
                    WHERE identity_resolution_status='resolved_remap_to_retinol'
                    """,
                    6,
                ),
                (
                    "RETINOL trial remaps",
                    """
                    SELECT COUNT(*)
                    FROM drug_clinical_trial_association
                    WHERE identity_resolution_status='resolved_remap_to_retinol'
                    """,
                    5,
                ),
                (
                    "Pegaptanib source-ID conflict flags",
                    """
                    SELECT COUNT(*)
                    FROM drug_clinical_report_association
                    WHERE identity_resolution_status=
                          'retained_source_identifier_conflict'
                    """,
                    5,
                ),
                (
                    "Levothyroxine pending review",
                    """
                    SELECT COUNT(*)
                    FROM drug_clinical_report_association
                    WHERE identity_resolution_status=
                          'manual_review_pending_stereochemistry'
                    """,
                    1,
                ),
                (
                    "X-82 pending review",
                    """
                    SELECT COUNT(*)
                    FROM drug_clinical_report_association
                    WHERE identity_resolution_status=
                          'manual_review_pending_alias_identity'
                    """,
                    1,
                ),
                (
                    "target overlap + direct",
                    """
                    SELECT COUNT(*)
                    FROM disease_drug_target_overlap_summary
                    WHERE direct_disease_drug_evidence=1
                    """,
                    27,
                ),
                (
                    "target overlap only",
                    """
                    SELECT COUNT(*)
                    FROM disease_drug_target_overlap_summary
                    WHERE direct_disease_drug_evidence=0
                    """,
                    1176,
                ),
            ]

            print("\nREFINEMENT CHECKS")
            for name, sql, expected in positives:
                actual = int(scalar(cur, sql))
                ok = actual == expected
                print(
                    f"{name:60s} {actual:>8,} "
                    f"{'OK' if ok else f'EXPECTED {expected}'}"
                )
                problem = 0 if ok else abs(actual - expected) or 1
                results.append(
                    (name, "ERROR", problem,
                     f"expected={expected}; actual={actual}")
                )
                if not ok:
                    failures.append(name)

            # Report key high-level values
            print("\nKEY DATABASE METRICS")
            metrics = [
                ("DDA unique diseases",
                 "SELECT COUNT(DISTINCT disease_id) FROM disease_drug_association"),
                ("DDA unique drugs",
                 "SELECT COUNT(DISTINCT drug_id) FROM disease_drug_association"),
                ("overlap unique diseases",
                 "SELECT COUNT(DISTINCT disease_id) FROM disease_drug_target_overlap_summary"),
                ("overlap unique drugs",
                 "SELECT COUNT(DISTINCT drug_id) FROM disease_drug_target_overlap_summary"),
                ("overlap unique target genes",
                 "SELECT COUNT(DISTINCT hgnc_id) FROM disease_drug_target_overlap"),
            ]
            for name, sql in metrics:
                print(f"{name:60s} {int(scalar(cur, sql)):>8,}")

            if args.write_db_results:
                cur.execute("TRUNCATE TABLE oddb_validation_result")
                cur.executemany(
                    """
                    INSERT INTO oddb_validation_result
                      (check_name, severity, problem_count, details)
                    VALUES (%s,%s,%s,%s)
                    """,
                    results,
                )
                conn.commit()

        print("\n" + "=" * 72)
        if failures:
            print(f"VALIDATION FAILED: {len(failures)} check(s) failed.")
            for x in failures:
                print(" -", x)
            raise SystemExit(1)

        print("VALIDATION PASSED: zero problems.")
        print("The MySQL database matches the frozen refined ODDB v1 release.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
