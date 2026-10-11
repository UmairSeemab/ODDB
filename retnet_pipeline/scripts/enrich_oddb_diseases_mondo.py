#!/usr/bin/env python3
"""
Enrich the canonical ODDB Disease master with exact MONDO mappings and
authoritative external cross-references from the pinned MONDO release.

Automatic mappings are deliberately conservative:
  1) preserve an existing MONDO ID if present;
  2) otherwise accept a unique exact preferred-label match;
  3) otherwise accept a unique EXACT-synonym match;
  4) ambiguous or unmatched diseases remain unresolved.

Cross-references are taken only from exact/equivalent mappings in
mondo.sssom.tsv. Broad/close/narrow mappings are not promoted.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

GITHUB_API = "https://api.github.com/repos/monarch-initiative/mondo/releases/tags/{tag}"


def clean(x):
    return str(x or "").strip()


def norm_text(s):
    s = unicodedata.normalize("NFKD", clean(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_mondo(x):
    m = re.search(r"MONDO:(?:MONDO:)?(\d+)", clean(x), flags=re.I)
    if not m:
        m = re.search(r"\b(\d{7})\b", clean(x))
    return f"MONDO:{m.group(1).zfill(7)}" if m else ""


def split_values(x):
    return [v.strip() for v in re.split(r"\s*\|\s*", clean(x)) if v.strip()]


def join_unique(values):
    seen, out = set(), []
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return " | ".join(out)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_json(url):
    req = Request(
        url,
        headers={
            "User-Agent": "ODDB-v1-MONDO-enrichment/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "ODDB-v1-MONDO-enrichment/1.0"})
    with urlopen(req, timeout=180) as r, open(path, "wb") as out:
        shutil.copyfileobj(r, out)


def ensure_assets(tag, raw_dir):
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    wanted = {
        "mondo-base.obo": raw_dir / "mondo-base.obo",
        "mondo.sssom.tsv": raw_dir / "mondo.sssom.tsv",
    }

    missing = [name for name, path in wanted.items() if not path.exists()]
    release = None

    if missing:
        api = GITHUB_API.format(tag=tag)
        release = fetch_json(api)
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}

        for name in missing:
            if name not in assets:
                available = ", ".join(sorted(assets))
                raise SystemExit(
                    f"Required MONDO asset {name!r} not found in {tag}. "
                    f"Available assets: {available}"
                )
            print(f"Downloading {name} from MONDO {tag}...")
            download(assets[name], wanted[name])

    if release is None:
        try:
            release = fetch_json(GITHUB_API.format(tag=tag))
        except Exception:
            release = {}

    manifest = {
        "release_tag": tag,
        "release_name": release.get("name", ""),
        "published_at": release.get("published_at", ""),
        "html_url": release.get("html_url", ""),
        "assets": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for name, path in wanted.items()
        },
    }
    (raw_dir / "mondo_source_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return wanted, manifest


def parse_obo(path):
    terms = {}
    current = None

    def finish(term):
        if not term:
            return
        mid = norm_mondo(term.get("id", ""))
        if not mid or term.get("obsolete"):
            return
        terms[mid] = term

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")

            if line == "[Term]":
                finish(current)
                current = {
                    "id": "",
                    "name": "",
                    "exact_synonyms": [],
                    "obsolete": False,
                }
                continue

            if line.startswith("[") and line.endswith("]"):
                finish(current)
                current = None
                continue

            if current is None:
                continue

            if line.startswith("id: "):
                current["id"] = line[4:].strip()
            elif line.startswith("name: "):
                current["name"] = line[6:].strip()
            elif line == "is_obsolete: true":
                current["obsolete"] = True
            elif line.startswith("synonym: "):
                m = re.match(r'^synonym:\s+"(.*)"\s+(EXACT|BROAD|NARROW|RELATED)\s+', line)
                if m and m.group(2) == "EXACT":
                    current["exact_synonyms"].append(m.group(1))

    finish(current)
    return terms


def parse_sssom(path):
    # Skip SSSOM YAML/comment metadata and locate the TSV header.
    header = None
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            header = line.rstrip("\n").split("\t")
            break

        if not header:
            raise SystemExit("Could not find header in mondo.sssom.tsv")

        reader = csv.DictReader(fh, fieldnames=header, delimiter="\t")
        for row in reader:
            rows.append(row)

    return rows


def external_id(curie):
    curie = clean(curie)
    if ":" not in curie:
        return None, None
    prefix, value = curie.split(":", 1)
    p = prefix.lower()

    if p == "omim":
        return "OMIM", value
    if p in {"orphanet", "orpha", "ordo"}:
        return "ORPHA", re.sub(r"\D", "", value)
    if p in {"umls", "medgen"}:
        m = re.search(r"(CN?\d+|C\d+)", value.upper())
        return ("CUI", m.group(1)) if m else (None, None)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--review-output", required=True)
    ap.add_argument("--report-output", required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--mondo-tag", default="v2026-09-01")
    args = ap.parse_args()

    disease = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")

    for c in [
        "DiseaseID", "Disease_Name", "MONDO_ID", "OMIM_ID",
        "Orphanet_ID", "MedGen_UMLS_CUI"
    ]:
        if c not in disease.columns:
            disease[c] = ""

    assets, manifest = ensure_assets(args.mondo_tag, args.raw_dir)
    terms = parse_obo(assets["mondo-base.obo"])

    preferred = defaultdict(set)
    exact_syn = defaultdict(set)

    for mid, term in terms.items():
        n = norm_text(term["name"])
        if n:
            preferred[n].add(mid)
        for syn in term["exact_synonyms"]:
            n = norm_text(syn)
            if n:
                exact_syn[n].add(mid)

    # Canonical exact external mappings from SSSOM.
    xrefs = defaultdict(lambda: defaultdict(set))
    exact_predicates = {
        "skos:exactmatch",
        "owl:equivalentclass",
        "semapv:crossspeciesexactmatch",
    }

    for row in parse_sssom(assets["mondo.sssom.tsv"]):
        subj = clean(row.get("subject_id"))
        obj = clean(row.get("object_id"))
        pred = clean(row.get("predicate_id")).lower()

        # The canonical file is mapping-oriented, but still reject non-exact
        # predicates if present.
        if pred and pred not in exact_predicates and "exact" not in pred and "equivalent" not in pred:
            continue

        sm = norm_mondo(subj)
        om = norm_mondo(obj)

        if sm and not om:
            kind, value = external_id(obj)
            if kind and value:
                xrefs[sm][kind].add(value)
        elif om and not sm:
            kind, value = external_id(subj)
            if kind and value:
                xrefs[om][kind].add(value)

    review_rows = []
    status_counts = defaultdict(int)

    mapped_ids = []
    methods = []
    labels = []
    ambiguity = []

    for _, row in disease.iterrows():
        existing = norm_mondo(row.get("MONDO_ID", ""))
        dname = clean(row.get("Disease_Name", ""))
        dn = norm_text(dname)

        chosen = ""
        method = ""
        candidates = set()

        if existing:
            chosen = existing
            method = "existing_mondo_id"
        else:
            p = preferred.get(dn, set())
            if len(p) == 1:
                chosen = next(iter(p))
                method = "exact_preferred_label"
            elif len(p) > 1:
                candidates = set(p)
                method = "ambiguous_preferred_label"
            else:
                s = exact_syn.get(dn, set())
                if len(s) == 1:
                    chosen = next(iter(s))
                    method = "exact_synonym"
                elif len(s) > 1:
                    candidates = set(s)
                    method = "ambiguous_exact_synonym"
                else:
                    # Only use ODDB synonyms if the primary disease name failed.
                    syn_candidates = set()
                    for source_col in [
                        "Synonyms",
                        "Alternative_Disease_Names_From_Legacy",
                    ]:
                        for term in split_values(row.get(source_col, "")):
                            nt = norm_text(term)
                            syn_candidates |= preferred.get(nt, set())
                            syn_candidates |= exact_syn.get(nt, set())

                    if len(syn_candidates) == 1:
                        chosen = next(iter(syn_candidates))
                        method = "exact_oddb_synonym"
                    elif len(syn_candidates) > 1:
                        candidates = syn_candidates
                        method = "ambiguous_oddb_synonym"
                    else:
                        method = "unmapped"

        status_counts[method] += 1
        mapped_ids.append(chosen)
        methods.append(method)
        labels.append(terms.get(chosen, {}).get("name", "") if chosen else "")
        ambiguity.append(" | ".join(sorted(candidates)))

        if not chosen:
            review_rows.append({
                "DiseaseID": clean(row.get("DiseaseID")),
                "Disease_Name": dname,
                "MONDO_Match_Status": method,
                "Candidate_MONDO_IDs": " | ".join(sorted(candidates)),
                "Candidate_MONDO_Labels": " | ".join(
                    terms.get(x, {}).get("name", "") for x in sorted(candidates)
                ),
            })

    disease["MONDO_ID"] = mapped_ids
    disease["MONDO_Preferred_Label"] = labels
    disease["MONDO_Match_Method"] = methods
    disease["MONDO_Ambiguous_Candidates"] = ambiguity
    disease["MONDO_Release"] = args.mondo_tag

    # Enrich xrefs without destroying legacy values.
    new_omim, new_orpha, new_cui = [], [], []

    for _, row in disease.iterrows():
        mid = norm_mondo(row.get("MONDO_ID", ""))
        refs = xrefs.get(mid, {})

        omim = split_values(row.get("OMIM_ID", ""))
        orpha = split_values(row.get("Orphanet_ID", ""))
        cui = split_values(row.get("MedGen_UMLS_CUI", ""))

        omim += sorted(refs.get("OMIM", set()))
        orpha += [f"ORPHA:{x}" for x in sorted(refs.get("ORPHA", set()))]
        cui += sorted(refs.get("CUI", set()))

        new_omim.append(join_unique(omim))
        new_orpha.append(join_unique(orpha))
        new_cui.append(join_unique(cui))

    disease["OMIM_ID"] = new_omim
    disease["Orphanet_ID"] = new_orpha
    disease["MedGen_UMLS_CUI"] = new_cui

    disease["Disease_Identifier_Curation_Status"] = [
        (
            "mapped_exact"
            if clean(mid)
            else "needs_manual_review"
        )
        for mid in disease["MONDO_ID"]
    ]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.review_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_output).parent.mkdir(parents=True, exist_ok=True)

    disease.to_csv(args.output, sep="\t", index=False)
    pd.DataFrame(review_rows).to_csv(args.review_output, sep="\t", index=False)

    report = [
        ("Disease_rows", len(disease)),
        ("Diseases_with_MONDO_ID", int(disease["MONDO_ID"].astype(str).str.strip().ne("").sum())),
        ("Diseases_without_MONDO_ID", int(disease["MONDO_ID"].astype(str).str.strip().eq("").sum())),
        ("Diseases_with_OMIM_ID", int(disease["OMIM_ID"].astype(str).str.strip().ne("").sum())),
        ("Diseases_with_Orphanet_ID", int(disease["Orphanet_ID"].astype(str).str.strip().ne("").sum())),
        ("Diseases_with_MedGen_UMLS_CUI", int(disease["MedGen_UMLS_CUI"].astype(str).str.strip().ne("").sum())),
    ]
    for k in sorted(status_counts):
        report.append((f"MONDO_match_{k}", status_counts[k]))

    pd.DataFrame(report, columns=["Metric", "Value"]).to_csv(
        args.report_output, sep="\t", index=False
    )

    print("ODDB MONDO DISEASE ENRICHMENT")
    for k, v in report:
        print(f"{k}: {v}")
    print(f"\nEnriched disease master: {args.output}")
    print(f"Manual review queue: {args.review_output}")
    print(f"Report: {args.report_output}")
    print(f"Raw MONDO release: {args.raw_dir}")
    print("\nOnly exact/equivalent ontology mappings were promoted.")


if __name__ == "__main__":
    main()
