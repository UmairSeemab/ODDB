#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from pathlib import Path

import pymysql


SOURCE = "ODDB legacy Variant_Disease_final_file.xlsx"

EXPECTED_MEMBERSHIPS = 1400
EXPECTED_LINKS = 4200
EXPECTED_DVA_ROWS = 106838

SOURCE_TO_CATEGORY = {
    "missense variant": ("VARC-01", "missense variant"),
    "inframe deletion": ("VARC-02", "inframe deletion"),
    "frameshift variant": ("VARC-03", "frameshift variant"),
    "intron variant": ("VARC-04", "intron variant"),
    "regulatory region variant": ("VARC-05", "regulatory region variant"),
    "intergenic variant": ("VARC-06", "intergenic variant"),
    "splice region variant": ("VARC-07", "splice region variant"),
    "splice donor variant": ("VARC-08", "splice donor variant"),
    "non coding transcript exon variant": (
        "VARC-09", "non coding transcript exon variant"
    ),
    "3 prime UTR variant": ("VARC-10", "3-prime UTR variant"),
    "5 prime UTR variant": ("VARC-11", "5-prime UTR variant"),
    "stop gained": ("VARC-12", "stop gained"),
    "synonymous variant": ("VARC-13", "synonymous variant"),
    "TF binding site variant": ("VARC-14", "TF binding site variant"),
    "splice acceptor variant": ("VARC-15", "splice acceptor variant"),
    "downstream gene variant": ("VARC-16", "downstream gene variant"),
    "stop lost": ("VARC-17", "stop lost"),
    "upstream gene variant": ("VARC-18", "upstream gene variant"),
    "inframe insertion": ("VARC-19", "inframe insertion"),
    "protein altering variant": ("VARC-20", "protein altering variant"),
    "Multiple": ("VARC-21", "Multiple reported"),
}


def read_tsv(path: Path):
    if not path.is_file():
        raise SystemExit(f"Required input report not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def stable_id(prefix: str, *parts: str, hex_len: int = 16) -> str:
    payload = "\x1f".join(str(x) for x in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:hex_len].upper()
    return f"{prefix}{digest}"


def extract_rsid(url: str):
    m = re.search(r"\brs\d+\b", str(url or ""), re.I)
    return m.group(0).lower() if m else None


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Preview/apply the validated ODDB v1 legacy variant consequence "
            "and external-link web-support layer."
        )
    )
    ap.add_argument(
        "--report-dir",
        default="reports/variant_consequence_layer_v0.5.7",
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    report_dir = Path(args.report_dir)
    membership_path = report_dir / "variant_consequence_memberships.tsv"
    link_path = report_dir / "variant_external_links.tsv"

    memberships = read_tsv(membership_path)
    links = read_tsv(link_path)

    print("ODDB v1 VARIANT CONSEQUENCE IMPORT v0.5.8")
    print("=" * 92)
    print(f"Membership input: {membership_path}")
    print(f"External-link input: {link_path}")
    print(f"Input variant/consequence memberships: {len(memberships):,}")
    print(f"Input external-link candidates: {len(links):,}")

    problems = []

    if len(memberships) != EXPECTED_MEMBERSHIPS:
        problems.append(
            f"Expected {EXPECTED_MEMBERSHIPS:,} memberships, found {len(memberships):,}"
        )
    if len(links) != EXPECTED_LINKS:
        problems.append(
            f"Expected {EXPECTED_LINKS:,} external-link rows, found {len(links):,}"
        )

    # Validate and normalize membership input.
    prepared_memberships = []
    seen_memberships = set()
    input_variant_ids = set()
    populated_source_types = set()

    for i, row in enumerate(memberships, start=2):
        vid = (row.get("Current_VariantID") or "").strip()
        source_type = (row.get("Variant_Type") or "").strip()

        if not vid or not source_type:
            problems.append(f"Blank variant/type in membership input line {i}")
            continue

        if source_type not in SOURCE_TO_CATEGORY:
            problems.append(
                f"Unexpected source consequence {source_type!r} at line {i}"
            )
            continue

        cid, display_term = SOURCE_TO_CATEGORY[source_type]
        key = (vid, cid)

        if key in seen_memberships:
            problems.append(
                f"Duplicate variant/consequence input membership {vid} {cid}"
            )
            continue

        seen_memberships.add(key)
        input_variant_ids.add(vid)
        populated_source_types.add(source_type)

        vc_id = stable_id("ODDB-VC-", vid, cid, SOURCE)

        prepared_memberships.append({
            "variant_consequence_id": vc_id,
            "variant_id": vid,
            "consequence_id": cid,
            "hgnc_id": None,
            "transcript_id": None,
            "source": SOURCE,
            "source_value": source_type,
            "display_term": display_term,
        })

    # Validate and normalize external links.
    prepared_links = []
    seen_link_semantics = set()
    link_variant_ids = set()
    resource_counts = {}

    allowed_resources = {"Ensembl", "dbSNP", "gnomAD"}

    for i, row in enumerate(links, start=2):
        vid = (row.get("Current_VariantID") or "").strip()
        resource = (row.get("Resource") or "").strip()
        url = (row.get("URL") or "").strip()

        if not vid or not resource or not url:
            problems.append(f"Blank variant/resource/url in link input line {i}")
            continue

        if resource not in allowed_resources:
            problems.append(
                f"Unexpected variant link resource {resource!r} at line {i}"
            )
            continue

        key = ("variant", vid, resource, url)
        if key in seen_link_semantics:
            problems.append(
                f"Duplicate external-link candidate {vid} {resource} {url}"
            )
            continue

        seen_link_semantics.add(key)
        link_variant_ids.add(vid)
        resource_counts[resource] = resource_counts.get(resource, 0) + 1

        rsid = extract_rsid(url)
        link_id = stable_id(
            "ODDB-LINK-",
            "variant",
            vid,
            resource,
            url,
        )

        prepared_links.append({
            "link_id": link_id,
            "entity_type": "variant",
            "entity_id": vid,
            "resource_name": resource,
            "external_id": rsid,
            "url": url,
            "display_label": resource,
            "display_order": 100,
            "source": SOURCE,
        })

    if problems:
        print("\nINPUT VALIDATION FAILED:")
        for p in problems[:50]:
            print(" -", p)
        if len(problems) > 50:
            print(f" ... plus {len(problems) - 50} more")
        raise SystemExit("No database changes were made.")

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
            # ----------------------------------------------------------
            # Validate the 21 category seed rows exactly.
            # ----------------------------------------------------------
            cur.execute("""
                SELECT consequence_id, consequence_term, display_order
                FROM variant_consequence_category
                ORDER BY display_order, consequence_id
            """)
            db_categories = cur.fetchall()
            db_cat = {
                r["consequence_id"]: (
                    r["consequence_term"],
                    int(r["display_order"]),
                )
                for r in db_categories
            }

            expected_category_ids = {
                cid for cid, _ in SOURCE_TO_CATEGORY.values()
            }

            if set(db_cat) != expected_category_ids:
                problems.append(
                    "variant_consequence_category IDs do not exactly match "
                    "the expected 21-category taxonomy"
                )

            expected_by_id = {}
            for source_type, (cid, display_term) in SOURCE_TO_CATEGORY.items():
                expected_by_id[cid] = display_term

            for cid, expected_term in expected_by_id.items():
                actual = db_cat.get(cid)
                if actual is None:
                    continue
                if actual[0] != expected_term:
                    problems.append(
                        f"{cid} term mismatch: DB={actual[0]!r}, "
                        f"expected={expected_term!r}"
                    )

            # ----------------------------------------------------------
            # Validate all canonical variants exist.
            # ----------------------------------------------------------
            all_variant_ids = sorted(input_variant_ids | link_variant_ids)
            existing_variant_ids = set()

            for i in range(0, len(all_variant_ids), 1000):
                chunk = all_variant_ids[i:i + 1000]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"SELECT variant_id FROM variant "
                    f"WHERE variant_id IN ({placeholders})",
                    chunk,
                )
                existing_variant_ids.update(
                    str(r["variant_id"]) for r in cur.fetchall()
                )

            missing_variants = sorted(set(all_variant_ids) - existing_variant_ids)
            if missing_variants:
                problems.append(
                    f"{len(missing_variants):,} input variant IDs are absent "
                    f"from canonical variant table; examples: "
                    + ", ".join(missing_variants[:10])
                )

            # ----------------------------------------------------------
            # Baseline canonical counts: must not change.
            # ----------------------------------------------------------
            cur.execute("SELECT COUNT(*) AS n FROM disease_variant_association")
            dva_before = int(cur.fetchone()["n"])

            cur.execute("SELECT COUNT(*) AS n FROM variant")
            variant_before = int(cur.fetchone()["n"])

            if dva_before != EXPECTED_DVA_ROWS:
                problems.append(
                    f"Canonical DVA count is {dva_before:,}, "
                    f"expected {EXPECTED_DVA_ROWS:,}"
                )

            # Existing web-support rows.
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM variant_consequence
                WHERE source=%s
            """, (SOURCE,))
            source_vc_before = int(cur.fetchone()["n"])

            cur.execute("""
                SELECT variant_consequence_id, variant_id,
                       consequence_id, hgnc_id, source, source_value
                FROM variant_consequence
            """)
            all_existing_vc = cur.fetchall()

            existing_other_vc_semantics = {
                (
                    str(r["variant_id"]),
                    str(r["consequence_id"]),
                    r["hgnc_id"],
                )
                for r in all_existing_vc
                if r["source"] != SOURCE
            }

            cross_source_vc_overlap = [
                (r["variant_id"], r["consequence_id"])
                for r in prepared_memberships
                if (
                    r["variant_id"],
                    r["consequence_id"],
                    None,
                ) in existing_other_vc_semantics
            ]

            # Existing exact external-link semantics.
            cur.execute("""
                SELECT link_id, entity_type, entity_id,
                       resource_name, url, source
                FROM entity_external_link
                WHERE entity_type='variant'
            """)
            existing_variant_links = cur.fetchall()

            existing_link_semantics = {
                (
                    str(r["entity_type"]),
                    str(r["entity_id"]),
                    str(r["resource_name"]),
                    str(r["url"]),
                )
                for r in existing_variant_links
            }

            source_link_ids = {
                str(r["link_id"])
                for r in existing_variant_links
                if r["source"] == SOURCE
            }

            exact_links_already_present = sum(
                1
                for r in prepared_links
                if (
                    r["entity_type"],
                    r["entity_id"],
                    r["resource_name"],
                    r["url"],
                ) in existing_link_semantics
            )

            new_links_if_applied = len(prepared_links) - exact_links_already_present

            # Check deterministic link_id collision with unrelated existing row.
            existing_by_link_id = {
                str(r["link_id"]): (
                    str(r["entity_type"]),
                    str(r["entity_id"]),
                    str(r["resource_name"]),
                    str(r["url"]),
                )
                for r in existing_variant_links
            }

            for r in prepared_links:
                if r["link_id"] in existing_by_link_id:
                    expected_semantics = (
                        r["entity_type"],
                        r["entity_id"],
                        r["resource_name"],
                        r["url"],
                    )
                    if existing_by_link_id[r["link_id"]] != expected_semantics:
                        problems.append(
                            f"Deterministic link_id collision: {r['link_id']}"
                        )

            if problems:
                print("\nDATABASE VALIDATION FAILED:")
                for p in problems[:50]:
                    print(" -", p)
                if len(problems) > 50:
                    print(f" ... plus {len(problems) - 50} more")
                raise SystemExit("No database changes were made.")

            print("\nValidated input:")
            print(f"Canonical variants referenced: {len(all_variant_ids):,}")
            print(f"Consequence memberships prepared: {len(prepared_memberships):,}")
            print(f"External-link rows prepared: {len(prepared_links):,}")
            print(
                "Populated source consequence categories: "
                f"{len(populated_source_types):,} / 21"
            )
            print(
                "Zero-membership categories retained: "
                + ", ".join(
                    sorted(set(SOURCE_TO_CATEGORY) - populated_source_types)
                )
            )

            print("\nExternal links by resource:")
            for resource in ["Ensembl", "dbSNP", "gnomAD"]:
                print(
                    f"{resource:10s} "
                    f"{resource_counts.get(resource, 0):5d}"
                )

            print("\nCurrent database state:")
            print(f"Canonical DVA rows: {dva_before:,}")
            print(f"Canonical variant rows: {variant_before:,}")
            print(
                f"Existing v0.5.8-source consequence rows: "
                f"{source_vc_before:,}"
            )
            print(
                f"Exact candidate external links already present: "
                f"{exact_links_already_present:,}"
            )
            print(
                f"New external links if applied: {new_links_if_applied:,}"
            )
            print(
                f"Cross-source NULL-gene consequence overlaps: "
                f"{len(cross_source_vc_overlap):,}"
            )

            if not args.apply:
                print("\nPREVIEW PASSED — MySQL was not modified.")
                print("Run again with --apply to write only the web-support layer.")
                return

            # ----------------------------------------------------------
            # APPLY
            # ----------------------------------------------------------
            try:
                # Replace only this importer's own consequence rows.
                cur.execute(
                    "DELETE FROM variant_consequence WHERE source=%s",
                    (SOURCE,),
                )

                # Insert exact 1,400 source-specific memberships.
                vc_sql = """
                    INSERT INTO variant_consequence (
                        variant_consequence_id,
                        variant_id,
                        consequence_id,
                        hgnc_id,
                        transcript_id,
                        source,
                        source_value
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """

                for r in prepared_memberships:
                    cur.execute(
                        vc_sql,
                        (
                            r["variant_consequence_id"],
                            r["variant_id"],
                            r["consequence_id"],
                            r["hgnc_id"],
                            r["transcript_id"],
                            r["source"],
                            r["source_value"],
                        ),
                    )

                # Remove only variant external links previously created by
                # this exact source. Other link sources are preserved.
                cur.execute("""
                    DELETE FROM entity_external_link
                    WHERE entity_type='variant'
                      AND source=%s
                """, (SOURCE,))

                # Refresh current exact-link set after source-specific deletion.
                cur.execute("""
                    SELECT entity_type, entity_id, resource_name, url
                    FROM entity_external_link
                    WHERE entity_type='variant'
                """)
                remaining_link_semantics = {
                    (
                        str(r["entity_type"]),
                        str(r["entity_id"]),
                        str(r["resource_name"]),
                        str(r["url"]),
                    )
                    for r in cur.fetchall()
                }

                link_sql = """
                    INSERT INTO entity_external_link (
                        link_id,
                        entity_type,
                        entity_id,
                        resource_name,
                        external_id,
                        url,
                        display_label,
                        display_order,
                        source
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """

                inserted_links = 0
                skipped_existing_links = 0

                for r in prepared_links:
                    semantic_key = (
                        r["entity_type"],
                        r["entity_id"],
                        r["resource_name"],
                        r["url"],
                    )

                    if semantic_key in remaining_link_semantics:
                        skipped_existing_links += 1
                        continue

                    cur.execute(
                        link_sql,
                        (
                            r["link_id"],
                            r["entity_type"],
                            r["entity_id"],
                            r["resource_name"],
                            r["external_id"],
                            r["url"],
                            r["display_label"],
                            r["display_order"],
                            r["source"],
                        ),
                    )
                    inserted_links += 1
                    remaining_link_semantics.add(semantic_key)

                # ------------------------------------------------------
                # Post-write validation before commit.
                # ------------------------------------------------------
                cur.execute("""
                    SELECT COUNT(*) AS n
                    FROM variant_consequence
                    WHERE source=%s
                """, (SOURCE,))
                source_vc_after = int(cur.fetchone()["n"])

                cur.execute("""
                    SELECT COUNT(*) AS n
                    FROM entity_external_link
                    WHERE entity_type='variant'
                      AND source=%s
                """, (SOURCE,))
                source_links_after = int(cur.fetchone()["n"])

                cur.execute("""
                    SELECT COUNT(DISTINCT variant_id) AS n
                    FROM variant_consequence
                    WHERE source=%s
                """, (SOURCE,))
                source_vc_variants = int(cur.fetchone()["n"])

                cur.execute("""
                    SELECT COUNT(DISTINCT consequence_id) AS n
                    FROM variant_consequence
                    WHERE source=%s
                """, (SOURCE,))
                populated_category_count = int(cur.fetchone()["n"])

                cur.execute(
                    "SELECT COUNT(*) AS n FROM disease_variant_association"
                )
                dva_after = int(cur.fetchone()["n"])

                cur.execute("SELECT COUNT(*) AS n FROM variant")
                variant_after = int(cur.fetchone()["n"])

                post_problems = []

                if source_vc_after != EXPECTED_MEMBERSHIPS:
                    post_problems.append(
                        f"source consequence rows {source_vc_after:,} != "
                        f"{EXPECTED_MEMBERSHIPS:,}"
                    )

                if source_vc_variants != EXPECTED_MEMBERSHIPS:
                    post_problems.append(
                        f"unique variants with consequence "
                        f"{source_vc_variants:,} != {EXPECTED_MEMBERSHIPS:,}"
                    )

                if populated_category_count != 19:
                    post_problems.append(
                        f"populated consequence categories "
                        f"{populated_category_count} != 19"
                    )

                # Since currently there are no existing Ensembl/dbSNP/gnomAD
                # variant links, this should normally be 4200. If exact links
                # from another source existed, the source-specific count can
                # be smaller, but total semantic coverage must still be 4200.
                cur.execute("""
                    SELECT entity_id, resource_name, url
                    FROM entity_external_link
                    WHERE entity_type='variant'
                      AND resource_name IN ('Ensembl','dbSNP','gnomAD')
                """)
                actual_semantics = {
                    (
                        str(r["entity_id"]),
                        str(r["resource_name"]),
                        str(r["url"]),
                    )
                    for r in cur.fetchall()
                }

                expected_semantics = {
                    (
                        r["entity_id"],
                        r["resource_name"],
                        r["url"],
                    )
                    for r in prepared_links
                }

                missing_semantics = expected_semantics - actual_semantics
                if missing_semantics:
                    post_problems.append(
                        f"{len(missing_semantics):,} expected external links "
                        f"are missing after apply"
                    )

                if dva_after != dva_before:
                    post_problems.append(
                        f"DVA count changed: {dva_before:,} -> {dva_after:,}"
                    )

                if variant_after != variant_before:
                    post_problems.append(
                        f"variant count changed: "
                        f"{variant_before:,} -> {variant_after:,}"
                    )

                if post_problems:
                    conn.rollback()
                    print("\nPOST-WRITE VALIDATION FAILED — transaction rolled back:")
                    for p in post_problems:
                        print(" -", p)
                    raise SystemExit(1)

                conn.commit()

                print("\nAPPLY PASSED")
                print(
                    f"Variant consequence memberships written: "
                    f"{source_vc_after:,}"
                )
                print(
                    f"Unique canonical variants annotated: "
                    f"{source_vc_variants:,}"
                )
                print(
                    f"Populated consequence categories: "
                    f"{populated_category_count} / 21"
                )
                print(
                    f"Source-specific variant external links written: "
                    f"{source_links_after:,}"
                )
                print(
                    f"External links skipped because an identical link "
                    f"already existed from another source: "
                    f"{skipped_existing_links:,}"
                )
                print(f"Canonical DVA rows unchanged: {dva_after:,}")
                print(f"Canonical variant rows unchanged: {variant_after:,}")
                print(
                    "Zero-membership categories retained: "
                    "regulatory region variant; TF binding site variant"
                )

            except Exception:
                conn.rollback()
                raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
