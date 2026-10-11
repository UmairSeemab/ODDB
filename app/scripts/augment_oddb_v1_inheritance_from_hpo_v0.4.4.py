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

# HPO inheritance terms.
# Specific Mendelian modes map directly; modes not represented separately in
# the six ODDB public categories are conservatively grouped under Other.
HPO_TO_CATEGORY = {
    # Autosomal dominant and explicit descendants
    "HP:0000006": "INH-01",  # Autosomal dominant inheritance
    "HP:0001470": "INH-01",  # Sex-limited autosomal dominant
    "HP:0001475": "INH-01",  # Male-limited autosomal dominant
    "HP:0001452": "INH-01",  # Autosomal dominant contiguous gene syndrome
    "HP:0012274": "INH-01",  # AD with paternal imprinting
    "HP:0012275": "INH-01",  # AD with maternal imprinting

    # Autosomal recessive
    "HP:0000007": "INH-02",

    # Mitochondrial
    "HP:0001427": "INH-04",

    # X-linked
    "HP:0001419": "INH-07",  # X-linked recessive inheritance
    "HP:0001423": "INH-06",  # X-linked dominant inheritance

    # Other / non-specific / non-Mendelian / modes outside public six
    "HP:0001444": "INH-05",  # AD somatic cell mutation
    "HP:0001472": "INH-05",  # Familial predisposition
    "HP:0001426": "INH-05",  # Multifactorial inheritance
    "HP:0010984": "INH-05",  # Digenic inheritance
    "HP:0010983": "INH-05",  # Oligogenic inheritance
    "HP:0010982": "INH-05",  # Polygenic inheritance
    "HP:0001425": "INH-05",  # Heterogeneous
    "HP:0001428": "INH-05",  # Somatic mutation
    "HP:0001442": "INH-05",  # Somatic mosaicism
    "HP:0001466": "INH-05",  # Contiguous gene syndrome
    "HP:0003745": "INH-05",  # Sporadic
    "HP:0003743": "INH-05",  # Genetic anticipation
    "HP:0003744": "INH-05",  # Genetic anticipation with paternal bias
    "HP:0010985": "INH-05",  # Gonosomal inheritance
    "HP:0001417": "INH-05",  # Generic X-linked inheritance
    "HP:0001450": "INH-05",  # Y-linked inheritance
}

HPO_LABELS = {
    "HP:0000006": "Autosomal dominant inheritance",
    "HP:0001470": "Sex-limited autosomal dominant",
    "HP:0001475": "Male-limited autosomal dominant",
    "HP:0001452": "Autosomal dominant contiguous gene syndrome",
    "HP:0012274": "Autosomal dominant inheritance with paternal imprinting",
    "HP:0012275": "Autosomal dominant inheritance with maternal imprinting",
    "HP:0000007": "Autosomal recessive inheritance",
    "HP:0001427": "Mitochondrial inheritance",
    "HP:0001419": "X-linked recessive inheritance",
    "HP:0001423": "X-linked dominant inheritance",
    "HP:0001444": "Autosomal dominant somatic cell mutation",
    "HP:0001472": "Familial predisposition",
    "HP:0001426": "Multifactorial inheritance",
    "HP:0010984": "Digenic inheritance",
    "HP:0010983": "Oligogenic inheritance",
    "HP:0010982": "Polygenic inheritance",
    "HP:0001425": "Heterogeneous",
    "HP:0001428": "Somatic mutation",
    "HP:0001442": "Somatic mosaicism",
    "HP:0001466": "Contiguous gene syndrome",
    "HP:0003745": "Sporadic",
    "HP:0003743": "Genetic anticipation",
    "HP:0003744": "Genetic anticipation with paternal anticipation bias",
    "HP:0010985": "Gonosomal inheritance",
    "HP:0001417": "X-linked inheritance",
    "HP:0001450": "Y-linked inheritance",
}


def extract_ids(value, prefix):
    s = str(value or "")
    out = set()
    if prefix == "OMIM":
        pats = [
            r"(?:OMIM|MIM)[\s:_-]*0*(\d+)",
        ]
    elif prefix == "ORPHA":
        pats = [
            r"(?:ORPHA(?:NET)?)[\s:_-]*0*(\d+)",
        ]
    else:
        return out

    for pat in pats:
        for m in re.finditer(pat, s, re.I):
            out.add(str(int(m.group(1))))

    # Bare numeric IDs are allowed in database fields that are already known
    # to be OMIM or Orphanet columns.
    if not out and re.fullmatch(r"[\d\s,;|/.()-]+", s.strip()):
        for m in re.finditer(r"\d+", s):
            out.add(str(int(m.group(0))))
    return out


def load_baseline(path):
    memberships = defaultdict(lambda: defaultdict(list))
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"Baseline file not found: {p}")

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


def read_hpoa(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"HPOA file not found: {p}")

    rows = []
    with p.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        data_lines = []
        for line in f:
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            data_lines.append(line)

    reader = csv.DictReader(data_lines, delimiter="\t")
    rows = list(reader)
    return rows, reader.fieldnames or []


def col(fieldnames, candidates):
    lookup = {re.sub(r"[^a-z0-9]+", "", x.lower()): x for x in fieldnames}
    for c in candidates:
        k = re.sub(r"[^a-z0-9]+", "", c.lower())
        if k in lookup:
            return lookup[k]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hpoa", required=True)
    ap.add_argument(
        "--baseline",
        default="reports/web_taxonomy_inheritance_clingen_v0.4.2/"
                "combined_inheritance_memberships.tsv",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_hpo_v0.4.4",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    baseline = load_baseline(args.baseline)
    hpo_rows, fields = read_hpoa(args.hpoa)

    dbid_col = col(fields, ["database_id", "DatabaseID", "Database ID"])
    disease_name_col = col(fields, ["disease_name", "DiseaseName", "Disease Name"])
    hpo_col = col(fields, ["hpo_id", "HPO_ID", "HPO ID"])
    aspect_col = col(fields, ["aspect", "Aspect"])
    reference_col = col(fields, ["reference", "Reference"])
    evidence_col = col(fields, ["evidence", "Evidence"])
    biocuration_col = col(fields, ["biocuration", "Biocuration"])

    if not dbid_col or not hpo_col or not aspect_col:
        raise SystemExit(
            "Could not detect required phenotype.hpoa columns "
            "(database_id, hpo_id, aspect)."
        )

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
            dcols = {r["Field"] for r in cur.fetchall()}

            select_cols = ["disease_id", "disease_name"]
            for c in ["omim_id", "orphanet_id"]:
                if c in dcols:
                    select_cols.append(c)

            cur.execute(
                "SELECT " + ",".join(f"`{c}`" for c in select_cols) + " FROM disease"
            )
            diseases = cur.fetchall()

        by_omim = defaultdict(set)
        by_orpha = defaultdict(set)
        names = {}

        for d in diseases:
            did = d["disease_id"]
            names[did] = d["disease_name"]
            for x in extract_ids(d.get("omim_id"), "OMIM"):
                by_omim[x].add(did)
            for x in extract_ids(d.get("orphanet_id"), "ORPHA"):
                by_orpha[x].add(did)

        combined = defaultdict(lambda: defaultdict(list))
        for did, cats in baseline.items():
            for cid, ev in cats.items():
                combined[did][cid].extend(ev)

        baseline_covered = {did for did, cats in combined.items() if cats}
        current_ids = {d["disease_id"] for d in diseases}

        stats = Counter()
        exact_matches = []
        ambiguous = []
        unsupported_inheritance_terms = Counter()
        seen = set()

        for row_no, r in enumerate(hpo_rows, start=1):
            aspect = str(r.get(aspect_col, "") or "").strip().upper()
            if aspect != "I":
                continue

            stats["inheritance_rows"] += 1

            hp = str(r.get(hpo_col, "") or "").strip()
            cid = HPO_TO_CATEGORY.get(hp)
            if not cid:
                unsupported_inheritance_terms[hp] += 1
                stats["unsupported_inheritance_term"] += 1
                continue

            dbid = str(r.get(dbid_col, "") or "").strip()
            hits = set()
            method = None

            m = re.fullmatch(r"(?:OMIM|MIM):?(\d+)", dbid, re.I)
            if m:
                oid = str(int(m.group(1)))
                hits.update(by_omim.get(oid, set()))
                method = "exact OMIM"

            m = re.fullmatch(r"(?:ORPHA|ORPHANET):?(\d+)", dbid, re.I)
            if m:
                oid = str(int(m.group(1)))
                hits.update(by_orpha.get(oid, set()))
                method = "exact Orphanet"

            if not hits:
                stats["no_current_identifier_match"] += 1
                continue

            if len(hits) > 1:
                stats["ambiguous_identifier_match"] += 1
                ambiguous.append((
                    row_no, dbid, r.get(disease_name_col, "") if disease_name_col else "",
                    hp, "|".join(sorted(hits))
                ))
                continue

            did = next(iter(hits))
            ref = str(r.get(reference_col, "") or "").strip() if reference_col else ""
            evid = str(r.get(evidence_col, "") or "").strip() if evidence_col else ""
            bioc = str(r.get(biocuration_col, "") or "").strip() if biocuration_col else ""
            hpo_disease_name = (
                str(r.get(disease_name_col, "") or "").strip()
                if disease_name_col else ""
            )

            key = (did, cid, hp, dbid, ref, evid, bioc)
            if key in seen:
                stats["duplicate_assertion"] += 1
                continue
            seen.add(key)

            ev = {
                "source": "Human Phenotype Ontology phenotype.hpoa",
                "raw_value": hp,
                "raw_label": HPO_LABELS.get(hp, hp),
                "basis": method,
                "hpo_disease_id": dbid,
                "hpo_disease_name": hpo_disease_name,
                "reference": ref,
                "evidence": evid,
                "biocuration": bioc,
            }
            combined[did][cid].append(ev)
            stats["mapped_inheritance_rows"] += 1

            exact_matches.append((
                did,
                names.get(did, ""),
                dbid,
                hpo_disease_name,
                hp,
                HPO_LABELS.get(hp, hp),
                CATEGORY_NAMES[cid],
                method,
                ref,
                evid,
                bioc,
                "yes" if did not in baseline_covered else "no",
            ))

        covered = {did for did, cats in combined.items() if cats}
        added = covered - baseline_covered
        missing = current_ids - covered

        category_counts = Counter()
        multi = {}
        for did, cats in combined.items():
            for cid in cats:
                category_counts[cid] += 1
            if len(cats) > 1:
                multi[did] = sorted(cats)

        print("ODDB v1 HPO INHERITANCE AUGMENTATION v0.4.4")
        print("=" * 84)
        print(f"HPOA file: {args.hpoa}")
        print(f"HPOA rows parsed: {len(hpo_rows):,}")
        print(f"Current ODDB diseases: {len(current_ids):,}")
        print(f"Baseline diseases classified: {len(baseline_covered):,}")
        print(f"New diseases classified by HPO: {len(added):,}")
        print(f"Combined diseases classified: {len(covered):,} / {len(current_ids):,}")
        print(f"Still without inheritance classification: {len(missing):,}")
        print(f"Diseases with >1 category: {len(multi):,}")

        print("\nCombined category counts:")
        for cid in CATEGORY_NAMES:
            print(f"{CATEGORY_NAMES[cid]:28s} {category_counts[cid]:4d}")

        print("\nHPO diagnostics:")
        for k, v in stats.most_common():
            print(f"{k:36s} {v:6d}")

        if unsupported_inheritance_terms:
            print("\nInheritance HPO terms not mapped:")
            for hp, n in unsupported_inheritance_terms.most_common():
                print(f"{n:6d}  {hp or '<blank>'}")

        report_dir = Path(args.report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)

        with (report_dir / "hpo_exact_identifier_matches.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "DiseaseID\tDisease_Name\tHPO_Disease_ID\tHPO_Disease_Name\t"
                "HPO_Inheritance_ID\tHPO_Inheritance_Label\tMapped_Category\t"
                "Match_Method\tReference\tEvidence\tBiocuration\t"
                "Newly_Classified_vs_Baseline\n"
            )
            for row in exact_matches:
                f.write("\t".join(map(str, row)) + "\n")

        with (report_dir / "combined_inheritance_memberships.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "DiseaseID\tCategory_ID\tCategory_Name\tEvidence_Count\t"
                "Sources\tRaw_Values\tEvidence_JSON\n"
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

        with (report_dir / "still_missing_after_hpo.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write("DiseaseID\tDisease_Name\tOMIM_ID\tOrphanet_ID\n")
            disease_by_id = {d["disease_id"]: d for d in diseases}
            for did in sorted(missing):
                d = disease_by_id[did]
                f.write(
                    f"{did}\t{d['disease_name']}\t"
                    f"{d.get('omim_id','')}\t{d.get('orphanet_id','')}\n"
                )

        with (report_dir / "multi_category_after_hpo.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write("DiseaseID\tDisease_Name\tCategories\n")
            for did, cats in sorted(multi.items()):
                f.write(
                    f"{did}\t{names.get(did,'')}\t"
                    + " | ".join(CATEGORY_NAMES[c] for c in cats)
                    + "\n"
                )

        with (report_dir / "hpo_ambiguous_identifier_matches.tsv").open(
            "w", encoding="utf-8"
        ) as f:
            f.write(
                "Row\tHPO_Disease_ID\tHPO_Disease_Name\tInheritance_HPO_ID\t"
                "Candidate_ODDB_DiseaseIDs\n"
            )
            for row in ambiguous:
                f.write("\t".join(map(str, row)) + "\n")

        print("\nReports:")
        for name in [
            "hpo_exact_identifier_matches.tsv",
            "combined_inheritance_memberships.tsv",
            "still_missing_after_hpo.tsv",
            "multi_category_after_hpo.tsv",
            "hpo_ambiguous_identifier_matches.tsv",
        ]:
            print(report_dir / name)

        print("\nREAD-ONLY: MySQL was not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
