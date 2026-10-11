#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pymysql


CATEGORY_NAMES = {
    "INH-01": "Autosomal dominant",
    "INH-02": "Autosomal recessive",
    "INH-04": "Mitochondrial",
    "INH-05": "Other",
    "INH-06": "X-linked dominant",
    "INH-07": "X-linked recessive",
}

STRICT_CLASSIFICATIONS = {"definitive", "strong", "moderate"}
LIMITED_CLASSIFICATIONS = {"limited"}


def extract_mondo_values(x):
    s = str(x or "").upper()
    vals = set()
    for m in re.finditer(r"MONDO[:_ ]*0*(\d+)", s):
        vals.add(f"MONDO:{int(m.group(1)):07d}")
    return vals


def map_moi(raw):
    s = str(raw or "").strip().upper()
    s = re.sub(r"\s+", "", s)

    # ClinGen standard abbreviations.
    if s == "AD":
        return "INH-01"
    if s == "AR":
        return "INH-02"
    if s in {"MT", "MITO", "MITOCHONDRIAL"}:
        return "INH-04"
    if s in {"XLD", "XL-D"}:
        return "INH-06"
    if s in {"XLR", "XL-R"}:
        return "INH-07"

    # Do not guess direction for generic X-linked; SD=semidominant,
    # UD=undetermined. These are represented conservatively as Other.
    if s in {"XL", "SD", "UD", "OTHER", "UNKNOWN"}:
        return "INH-05"

    return None


def load_baseline(path):
    memberships = defaultdict(lambda: defaultdict(list))
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"Baseline membership file not found: {p}")

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            did = (row.get("DiseaseID") or "").strip()
            cid = (row.get("Category_ID") or "").strip()
            if not did or cid not in CATEGORY_NAMES:
                continue

            ev_json = (row.get("Evidence_JSON") or "").strip()
            if ev_json:
                try:
                    ev = json.loads(ev_json)
                    if isinstance(ev, list):
                        memberships[did][cid].extend(ev)
                        continue
                except Exception:
                    pass

            memberships[did][cid].append({
                "source": "ODDB inheritance baseline",
                "raw_value": row.get("Raw_Values", ""),
                "basis": "baseline membership report",
            })
    return memberships


def read_clingen_csv(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ClinGen CSV not found: {p}")

    lines = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        if "GENE SYMBOL" in line and "DISEASE ID (MONDO)" in line and "MOI" in line:
            header_idx = i
            break

    if header_idx is None:
        raise SystemExit(
            "Could not locate ClinGen Gene-Disease Validity header row. "
            "Expected columns including GENE SYMBOL, DISEASE ID (MONDO), and MOI."
        )

    reader = csv.DictReader(lines[header_idx:])
    rows = list(reader)
    return rows, header_idx + 1


def main():
    ap = argparse.ArgumentParser(
        description="Augment current ODDB v1 inheritance taxonomy from ClinGen GDV."
    )
    ap.add_argument("--clingen", required=True)
    ap.add_argument(
        "--baseline",
        default="reports/web_taxonomy_inheritance_ordo_v0.4.1/combined_inheritance_memberships.tsv",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_clingen_v0.4.2",
    )
    ap.add_argument(
        "--include-limited",
        action="store_true",
        help="Also promote exact-MONDO ClinGen Limited curations into the combined taxonomy.",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    baseline = load_baseline(args.baseline)
    clingen_rows, header_line = read_clingen_csv(args.clingen)

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
            cols = {r["Field"] for r in cur.fetchall()}
            select_cols = ["disease_id", "disease_name"]
            if "mondo_id" in cols:
                select_cols.append("mondo_id")

            cur.execute(
                "SELECT " + ",".join(f"`{c}`" for c in select_cols) + " FROM disease"
            )
            diseases = cur.fetchall()

        disease_by_mondo = defaultdict(set)
        name_by_id = {}

        for d in diseases:
            did = d["disease_id"]
            name_by_id[did] = d["disease_name"]
            for mondo in extract_mondo_values(d.get("mondo_id")):
                disease_by_mondo[mondo].add(did)

        combined = defaultdict(lambda: defaultdict(list))
        for did, cats in baseline.items():
            for cid, ev in cats.items():
                combined[did][cid].extend(ev)

        baseline_covered = {did for did, cats in combined.items() if cats}
        current_ids = {d["disease_id"] for d in diseases}

        stats = Counter()
        strict_matches = []
        limited_candidates = []
        excluded_rows = []
        unsupported_moi = Counter()
        ambiguous_mondo = []

        # Avoid duplicate identical ClinGen assertions in evidence.
        seen_assertions = set()

        for row_no, r in enumerate(clingen_rows, start=header_line + 1):
            gene = (r.get("GENE SYMBOL") or "").strip()
            hgnc = (r.get("GENE ID (HGNC)") or "").strip()
            disease_label = (r.get("DISEASE LABEL") or "").strip()
            mondo_raw = (r.get("DISEASE ID (MONDO)") or "").strip()
            moi = (r.get("MOI") or "").strip()
            classification = (r.get("CLASSIFICATION") or "").strip()
            report_url = (r.get("ONLINE REPORT") or "").strip()
            classification_date = (r.get("CLASSIFICATION DATE") or "").strip()
            gcep = (r.get("GCEP") or "").strip()

            classification_norm = classification.lower()
            mondos = extract_mondo_values(mondo_raw)

            if not mondos:
                stats["rows_without_mondo"] += 1
                continue

            if classification_norm in {
                "disputed",
                "disputed evidence",
                "refuted",
                "refuted evidence",
                "no known disease relationship",
                "no reported evidence",
            }:
                stats["excluded_non_supportive"] += 1
                excluded_rows.append((
                    row_no, gene, hgnc, disease_label, mondo_raw,
                    moi, classification, report_url
                ))
                continue

            is_strict = classification_norm in STRICT_CLASSIFICATIONS
            is_limited = classification_norm in LIMITED_CLASSIFICATIONS

            if not is_strict and not is_limited:
                stats["unrecognized_classification"] += 1
                excluded_rows.append((
                    row_no, gene, hgnc, disease_label, mondo_raw,
                    moi, classification, report_url
                ))
                continue

            cid = map_moi(moi)
            if not cid:
                unsupported_moi[moi] += 1
                stats["unsupported_moi"] += 1
                continue

            candidate_ids = set()
            matched_mondos = []
            for mondo in mondos:
                ids = disease_by_mondo.get(mondo, set())
                if ids:
                    candidate_ids.update(ids)
                    matched_mondos.append(mondo)

            if not candidate_ids:
                stats["no_current_mondo_match"] += 1
                continue

            if len(candidate_ids) > 1:
                stats["ambiguous_current_mondo"] += 1
                ambiguous_mondo.append((
                    row_no, gene, hgnc, disease_label, mondo_raw,
                    moi, classification, "|".join(sorted(candidate_ids))
                ))
                continue

            did = next(iter(candidate_ids))
            assertion_key = (
                did, cid, gene, hgnc, mondo_raw, moi, classification, report_url
            )
            if assertion_key in seen_assertions:
                stats["duplicate_assertion"] += 1
                continue
            seen_assertions.add(assertion_key)

            evidence = {
                "source": "ClinGen Gene-Disease Validity",
                "raw_value": moi,
                "basis": "exact MONDO; supportive GDV classification",
                "gene_symbol": gene,
                "hgnc_id": hgnc,
                "clingen_disease_label": disease_label,
                "clingen_mondo": mondo_raw,
                "classification": classification,
                "classification_date": classification_date,
                "gcep": gcep,
                "online_report": report_url,
            }

            match_row = (
                did,
                name_by_id.get(did, ""),
                gene,
                hgnc,
                disease_label,
                mondo_raw,
                moi,
                CATEGORY_NAMES[cid],
                classification,
                classification_date,
                gcep,
                report_url,
                "yes" if did not in baseline_covered else "no",
            )

            if is_strict:
                combined[did][cid].append(evidence)
                strict_matches.append(match_row)
                stats["strict_supportive_matches"] += 1
            else:
                limited_candidates.append(match_row)
                stats["limited_exact_mondo_candidates"] += 1
                if args.include_limited:
                    evidence = dict(evidence)
                    evidence["basis"] = "exact MONDO; Limited GDV classification"
                    combined[did][cid].append(evidence)
                    stats["limited_promoted"] += 1

        covered = {did for did, cats in combined.items() if cats}
        newly_classified = covered - baseline_covered
        still_missing = current_ids - covered

        category_counts = Counter()
        multi = {}
        for did, cats in combined.items():
            for cid in cats:
                category_counts[cid] += 1
            if len(cats) > 1:
                multi[did] = sorted(cats)

        print("ODDB v1 CLINGEN INHERITANCE AUGMENTATION v0.4.2")
        print("=" * 84)
        print(f"ClinGen file: {args.clingen}")
        print(f"ClinGen data rows parsed: {len(clingen_rows):,}")
        print(f"Current ODDB diseases: {len(current_ids):,}")
        print(f"Baseline diseases classified: {len(baseline_covered):,}")
        print(f"New diseases classified by strict ClinGen evidence: {len(newly_classified):,}")
        print(f"Combined diseases classified: {len(covered):,} / {len(current_ids):,}")
        print(f"Still without inheritance classification: {len(still_missing):,}")
        print(f"Diseases with >1 category: {len(multi):,}")
        print(f"Limited exact-MONDO candidate rows: {len(limited_candidates):,}")
        print(f"Limited promoted: {'yes' if args.include_limited else 'no'}")

        print("\nCombined category counts:")
        for cid in CATEGORY_NAMES:
            print(f"{CATEGORY_NAMES[cid]:28s} {category_counts[cid]:4d}")

        print("\nClinGen diagnostics:")
        for k, v in stats.most_common():
            print(f"{k:36s} {v:6d}")

        if unsupported_moi:
            print("\nClinGen MOI values not mapped:")
            for k, v in unsupported_moi.most_common():
                print(f"{v:6d}  {k or '<blank>'}")

        with (report_dir / "clingen_strict_exact_mondo_matches.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "DiseaseID\tDisease_Name\tGene\tHGNC\tClinGen_Disease\tMONDO\tMOI\t"
                "Mapped_Category\tClassification\tClassification_Date\tGCEP\t"
                "Online_Report\tNewly_Classified_vs_Baseline\n"
            )
            for r in strict_matches:
                f.write("\t".join(map(str, r)) + "\n")

        with (report_dir / "clingen_limited_exact_mondo_candidates.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "DiseaseID\tDisease_Name\tGene\tHGNC\tClinGen_Disease\tMONDO\tMOI\t"
                "Mapped_Category\tClassification\tClassification_Date\tGCEP\t"
                "Online_Report\tNewly_Classified_vs_Baseline\n"
            )
            for r in limited_candidates:
                f.write("\t".join(map(str, r)) + "\n")

        with (report_dir / "combined_inheritance_memberships.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "DiseaseID\tCategory_ID\tCategory_Name\tEvidence_Count\tSources\t"
                "Raw_Values\tEvidence_JSON\n"
            )
            for did in sorted(combined):
                for cid in sorted(combined[did]):
                    ev = combined[did][cid]
                    sources = sorted({
                        str(x.get("source", "")) for x in ev if x.get("source")
                    })
                    raws = sorted({
                        str(x.get("raw_value", ""))
                        for x in ev
                        if str(x.get("raw_value", "")).strip()
                    })
                    f.write(
                        f"{did}\t{cid}\t{CATEGORY_NAMES[cid]}\t{len(ev)}\t"
                        f"{' | '.join(sources)}\t{' | '.join(raws)}\t"
                        f"{json.dumps(ev, ensure_ascii=False)}\n"
                    )

        with (report_dir / "still_missing_after_clingen.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write("DiseaseID\tDisease_Name\n")
            for did in sorted(still_missing):
                f.write(f"{did}\t{name_by_id.get(did, '')}\n")

        with (report_dir / "multi_category_after_clingen.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write("DiseaseID\tDisease_Name\tCategories\n")
            for did, cats in sorted(multi.items()):
                f.write(
                    f"{did}\t{name_by_id.get(did, '')}\t"
                    + " | ".join(CATEGORY_NAMES[c] for c in cats)
                    + "\n"
                )

        with (report_dir / "clingen_excluded_non_supportive.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "Row\tGene\tHGNC\tDisease\tMONDO\tMOI\tClassification\tOnline_Report\n"
            )
            for r in excluded_rows:
                f.write("\t".join(map(str, r)) + "\n")

        with (report_dir / "clingen_ambiguous_mondo.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "Row\tGene\tHGNC\tDisease\tMONDO\tMOI\tClassification\t"
                "Candidate_ODDB_DiseaseIDs\n"
            )
            for r in ambiguous_mondo:
                f.write("\t".join(map(str, r)) + "\n")

        print("\nReports:")
        for name in [
            "clingen_strict_exact_mondo_matches.tsv",
            "clingen_limited_exact_mondo_candidates.tsv",
            "combined_inheritance_memberships.tsv",
            "still_missing_after_clingen.tsv",
            "multi_category_after_clingen.tsv",
            "clingen_excluded_non_supportive.tsv",
            "clingen_ambiguous_mondo.tsv",
        ]:
            print(report_dir / name)

        print("\nREAD-ONLY: MySQL was not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
