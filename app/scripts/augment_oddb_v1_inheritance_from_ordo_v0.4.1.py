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
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL


CATEGORY_NAMES = {
    "INH-01": "Autosomal dominant",
    "INH-02": "Autosomal recessive",
    "INH-03": "Isolated cases",
    "INH-04": "Mitochondrial",
    "INH-05": "Other",
    "INH-06": "X-linked dominant",
    "INH-07": "X-linked recessive",
}


def norm_header(x):
    return re.sub(r"[^a-z0-9]+", "", str(x or "").strip().lower())


def extract_orpha_values(x):
    s = str(x or "")
    vals = set()
    for m in re.finditer(r"(?:ORPHA(?:NET)?)[\s:_-]*0*(\d+)", s, re.I):
        vals.add(str(int(m.group(1))))
    if not vals and re.fullmatch(r"[\d\s,;|/.()-]+", s.strip()):
        for m in re.finditer(r"\d+", s):
            vals.add(str(int(m.group(0))))
    return vals


def extract_mondo_values(x):
    s = str(x or "").upper()
    vals = set()
    for m in re.finditer(r"MONDO[:_ ]*0*(\d+)", s):
        vals.add(f"MONDO:{int(m.group(1)):07d}")
    return vals


def map_ordo_inheritance(raw):
    s = str(raw or "").strip().lower()
    s = s.replace("_", " ").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)

    if "autosomal dominant" in s:
        return "INH-01"
    if "autosomal recessive" in s:
        return "INH-02"
    if "mitochondrial" in s or "maternal inheritance" in s:
        return "INH-04"
    if "x-linked dominant" in s or "x linked dominant" in s:
        return "INH-06"
    if "x-linked recessive" in s or "x linked recessive" in s:
        return "INH-07"

    # Preserve non-Mendelian / unresolved modes as Other.
    if any(x in s for x in (
        "unknown",
        "multigenic",
        "multifactorial",
        "not applicable",
        "oligogenic",
        "digenic",
        "other",
    )):
        return "INH-05"

    return None


def label_for(g, node):
    labels = [str(o) for o in g.objects(node, RDFS.label)]
    if labels:
        # Prefer English labels where present.
        for o in g.objects(node, RDFS.label):
            if isinstance(o, Literal) and (o.language in (None, "en")):
                return str(o)
        return labels[0]
    return str(node)


def discover_inheritance_properties(g):
    props = set()

    # Most robust: property labels containing inheritance.
    for s, _, o in g.triples((None, RDFS.label, None)):
        if isinstance(o, Literal) and "inheritance" in str(o).lower():
            props.add(s)

    # Also catch URI local names directly.
    for _, p, _ in g:
        if "inheritance" in str(p).lower():
            props.add(p)

    return props


def build_ordo_index(g):
    inheritance_props = discover_inheritance_properties(g)
    if not inheritance_props:
        raise RuntimeError("Could not discover an ORDO inheritance property.")

    direct_inheritance = defaultdict(set)

    # Direct relation form: disease --has_inheritance--> mode.
    for p in inheritance_props:
        for s, _, o in g.triples((None, p, None)):
            if isinstance(s, URIRef):
                direct_inheritance[s].add(label_for(g, o))

    # OWL restriction form:
    # disease rdfs:subClassOf restriction;
    # restriction owl:onProperty has_inheritance;
    # restriction owl:someValuesFrom mode.
    restriction_nodes = set()
    for p in inheritance_props:
        for r in g.subjects(OWL.onProperty, p):
            restriction_nodes.add(r)

    for r in restriction_nodes:
        modes = set(g.objects(r, OWL.someValuesFrom))
        modes.update(g.objects(r, OWL.allValuesFrom))
        if not modes:
            continue
        diseases = set(g.subjects(RDFS.subClassOf, r))
        for disease in diseases:
            if not isinstance(disease, URIRef):
                continue
            for mode in modes:
                direct_inheritance[disease].add(label_for(g, mode))

    # Index ORDO disease classes by ORPHA code and MONDO xrefs.
    by_orpha = defaultdict(set)
    by_mondo = defaultdict(set)
    disease_label = {}

    disease_uri_re = re.compile(r"/Orphanet_(\d+)$")

    for disease in direct_inheritance:
        uri = str(disease)
        m = disease_uri_re.search(uri)
        if m:
            by_orpha[str(int(m.group(1)))].add(disease)

        disease_label[disease] = label_for(g, disease)

        # ORDO xrefs may be represented through different predicates,
        # so inspect all outgoing literal/URI values for exact MONDO tokens.
        for _, _, obj in g.triples((disease, None, None)):
            for mondo in extract_mondo_values(obj):
                by_mondo[mondo].add(disease)

    return direct_inheritance, by_orpha, by_mondo, disease_label, inheritance_props


def load_baseline(path):
    memberships = defaultdict(lambda: defaultdict(list))
    if not path or not Path(path).is_file():
        return memberships

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            did = row.get("DiseaseID", "").strip()
            cid = row.get("Category_ID", "").strip()
            if not did or not cid:
                continue

            ev_json = row.get("Evidence_JSON", "").strip()
            if ev_json:
                try:
                    ev = json.loads(ev_json)
                    if isinstance(ev, list):
                        memberships[did][cid].extend(ev)
                        continue
                except Exception:
                    pass

            memberships[did][cid].append({
                "source": "ODDB v1 inheritance harmonization v0.4.0",
                "raw_value": row.get("Raw_Values", ""),
                "basis": "baseline report",
            })
    return memberships


def main():
    ap = argparse.ArgumentParser(
        description="Add exact disease-level ORDO inheritance evidence to current ODDB v1 taxonomy."
    )
    ap.add_argument("--ordo", required=True, help="Pinned ORDO OWL file, e.g. ORDO_en_4.9.owl")
    ap.add_argument(
        "--baseline",
        default="reports/web_taxonomy_inheritance_current_v0.4.0/current_inheritance_memberships.tsv",
        help="Preview membership report produced by v0.4.0",
    )
    ap.add_argument(
        "--report-dir",
        default="reports/web_taxonomy_inheritance_ordo_v0.4.1",
    )
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    ordo_path = Path(args.ordo)
    if not ordo_path.is_file():
        raise SystemExit(f"ORDO OWL file not found: {ordo_path}")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    baseline = load_baseline(args.baseline)

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
            for c in ["orphanet_id", "mondo_id"]:
                if c in cols:
                    select_cols.append(c)

            cur.execute(
                "SELECT " + ",".join(f"`{c}`" for c in select_cols) + " FROM disease"
            )
            diseases = cur.fetchall()

        print("Parsing ORDO ontology (this can take a little while)...")
        g = Graph()
        g.parse(str(ordo_path))

        (
            ordo_inheritance,
            by_orpha,
            by_mondo,
            ordo_labels,
            inheritance_props,
        ) = build_ordo_index(g)

        print("ODDB v1 ORDO INHERITANCE AUGMENTATION v0.4.1")
        print("=" * 84)
        print(f"ORDO file: {ordo_path}")
        print(f"RDF triples: {len(g):,}")
        print(f"Inheritance properties discovered: {len(inheritance_props):,}")
        print(f"ORDO entities with inheritance annotations: {len(ordo_inheritance):,}")
        print(f"Current ODDB diseases: {len(diseases):,}")

        combined = defaultdict(lambda: defaultdict(list))
        for did, cats in baseline.items():
            for cid, ev in cats.items():
                combined[did][cid].extend(ev)

        baseline_covered = {did for did, cats in combined.items() if cats}

        exact_ordo_matches = []
        ambiguous = []
        no_ordo_match = []
        unsupported_modes = Counter()

        for d in diseases:
            did = d["disease_id"]
            dname = d["disease_name"]
            hits_by_method = defaultdict(set)

            for o in extract_orpha_values(d.get("orphanet_id")):
                hits_by_method["Orphanet"].update(by_orpha.get(o, set()))

            for m in extract_mondo_values(d.get("mondo_id")):
                hits_by_method["MONDO"].update(by_mondo.get(m, set()))

            all_hits = set()
            for vals in hits_by_method.values():
                all_hits.update(vals)

            if len(all_hits) == 0:
                no_ordo_match.append((did, dname, d.get("orphanet_id", ""), d.get("mondo_id", "")))
                continue

            if len(all_hits) > 1:
                ambiguous.append((
                    did,
                    dname,
                    d.get("orphanet_id", ""),
                    d.get("mondo_id", ""),
                    "|".join(sorted(str(x) for x in all_hits)),
                ))
                continue

            entity = next(iter(all_hits))
            methods = [k for k, vals in hits_by_method.items() if entity in vals]
            raw_modes = sorted(ordo_inheritance.get(entity, set()))

            mapped_modes = []
            for raw in raw_modes:
                cid = map_ordo_inheritance(raw)
                if cid:
                    mapped_modes.append((cid, raw))
                    combined[did][cid].append({
                        "source": "Orphanet ORDO 4.9 (2026-07-01)",
                        "raw_value": raw,
                        "basis": "exact " + "+".join(sorted(methods)),
                        "ordo_uri": str(entity),
                        "ordo_label": ordo_labels.get(entity, ""),
                    })
                else:
                    unsupported_modes[raw] += 1

            exact_ordo_matches.append((
                did,
                dname,
                "|".join(sorted(methods)),
                str(entity),
                ordo_labels.get(entity, ""),
                " | ".join(raw_modes),
                " | ".join(sorted({CATEGORY_NAMES[c] for c, _ in mapped_modes})),
                "yes" if did not in baseline_covered and mapped_modes else "no",
            ))

        covered = {did for did, cats in combined.items() if cats}
        current_ids = {d["disease_id"] for d in diseases}
        added_diseases = covered - baseline_covered
        still_missing = current_ids - covered

        category_counts = Counter()
        multi = {}
        for did, cats in combined.items():
            for cid in cats:
                category_counts[cid] += 1
            if len(cats) > 1:
                multi[did] = sorted(cats)

        print(f"\nBaseline diseases classified: {len(baseline_covered):,}")
        print(f"New diseases classified by ORDO: {len(added_diseases):,}")
        print(f"Combined diseases classified: {len(covered):,} / {len(current_ids):,}")
        print(f"Still without inheritance classification: {len(still_missing):,}")
        print(f"Diseases with >1 category: {len(multi):,}")
        print(f"Ambiguous ORDO mappings: {len(ambiguous):,}")

        print("\nCombined category counts:")
        for cid in CATEGORY_NAMES:
            print(f"{CATEGORY_NAMES[cid]:28s} {category_counts[cid]:4d}")

        if unsupported_modes:
            print("\nORDO inheritance labels not mapped to the seven UI categories:")
            for raw, n in unsupported_modes.most_common():
                print(f"{n:6d}  {raw}")

        name_by_id = {d["disease_id"]: d["disease_name"] for d in diseases}

        with (report_dir / "ordo_exact_matches.tsv").open("w", encoding="utf-8") as f:
            f.write(
                "DiseaseID\tDisease_Name\tMatch_Method\tORDO_URI\tORDO_Label\t"
                "ORDO_Inheritance_Raw\tMapped_UI_Categories\tNewly_Classified\n"
            )
            for row in exact_ordo_matches:
                f.write("\t".join(map(str, row)) + "\n")

        with (report_dir / "combined_inheritance_memberships.tsv").open("w", encoding="utf-8") as f:
            f.write(
                "DiseaseID\tCategory_ID\tCategory_Name\tEvidence_Count\tSources\tRaw_Values\tEvidence_JSON\n"
            )
            for did in sorted(combined):
                for cid in sorted(combined[did]):
                    ev = combined[did][cid]
                    sources = sorted({str(x.get("source", "")) for x in ev if x.get("source")})
                    raws = sorted({str(x.get("raw_value", "")) for x in ev if str(x.get("raw_value", "")).strip()})
                    f.write(
                        f"{did}\t{cid}\t{CATEGORY_NAMES[cid]}\t{len(ev)}\t"
                        f"{' | '.join(sources)}\t{' | '.join(raws)}\t"
                        f"{json.dumps(ev, ensure_ascii=False)}\n"
                    )

        with (report_dir / "still_missing_after_ordo.tsv").open("w", encoding="utf-8") as f:
            f.write("DiseaseID\tDisease_Name\n")
            for did in sorted(still_missing):
                f.write(f"{did}\t{name_by_id.get(did, '')}\n")

        with (report_dir / "multi_category_after_ordo.tsv").open("w", encoding="utf-8") as f:
            f.write("DiseaseID\tDisease_Name\tCategories\n")
            for did, cats in sorted(multi.items()):
                f.write(
                    f"{did}\t{name_by_id.get(did, '')}\t"
                    + " | ".join(CATEGORY_NAMES[c] for c in cats)
                    + "\n"
                )

        with (report_dir / "ordo_ambiguous_matches.tsv").open("w", encoding="utf-8") as f:
            f.write("DiseaseID\tDisease_Name\tOrphanet_ID\tMONDO_ID\tCandidate_ORDO_URIs\n")
            for row in ambiguous:
                f.write("\t".join(map(str, row)) + "\n")

        with (report_dir / "no_ordo_match.tsv").open("w", encoding="utf-8") as f:
            f.write("DiseaseID\tDisease_Name\tOrphanet_ID\tMONDO_ID\n")
            for row in no_ordo_match:
                f.write("\t".join(map(str, row)) + "\n")

        print("\nReports:")
        for name in [
            "ordo_exact_matches.tsv",
            "combined_inheritance_memberships.tsv",
            "still_missing_after_ordo.tsv",
            "multi_category_after_ordo.tsv",
            "ordo_ambiguous_matches.tsv",
            "no_ordo_match.tsv",
        ]:
            print(report_dir / name)

        print("\nREAD-ONLY: MySQL was not modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
