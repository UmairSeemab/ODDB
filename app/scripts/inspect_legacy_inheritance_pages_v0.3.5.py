#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

TERMS = re.compile(
    r"inheritance|autosomal|x[- ]linked|mitochondrial|isolated|sporadic",
    re.I,
)

REF_PATTERNS = [
    re.compile(r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.I),
    re.compile(r"fetch\s*\(\s*[\"']([^\"']+)[\"']", re.I),
    re.compile(r"d3\.(?:csv|tsv|json)\s*\(\s*[\"']([^\"']+)[\"']", re.I),
    re.compile(r"[\"']([^\"']+\.(?:csv|tsv|json|js|txt|php))[\"']", re.I),
]

TEXT_EXTS = {".html", ".htm", ".js", ".json", ".csv", ".tsv", ".txt", ".php"}


def local_ref(base: Path, ref: str):
    ref = ref.strip()
    if not ref or ref.startswith("#") or ref.startswith("data:"):
        return None
    p = urlparse(ref)
    if p.scheme in {"http", "https", "mailto", "javascript"}:
        return None
    if not p.path:
        return None
    return (base / p.path).resolve()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def extract_refs(text: str):
    refs = []
    for pat in REF_PATTERNS:
        for m in pat.finditer(text):
            v = m.group(1).strip()
            if v not in refs:
                refs.append(v)
    return refs


def matching_lines(text: str, max_lines=80):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if TERMS.search(line):
            out.append((i, line[:1200]))
            if len(out) >= max_lines:
                break
    return out


def inspect(path: Path):
    text = read_text(path)
    print("\n" + "=" * 100)
    print(path)
    print("-" * 100)

    refs = extract_refs(text)
    if refs:
        print("REFERENCES:")
        for r in refs:
            print("  ", r)

    lines = matching_lines(text)
    if lines:
        print("\nINHERITANCE-RELATED LINES:")
        for n, line in lines:
            print(f"  L{n}: {line}")

    return refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "oddb_main",
        nargs="?",
        default="../ODDB-main",
        help="Path to legacy ODDB-main directory",
    )
    args = ap.parse_args()

    root = Path(args.oddb_main).resolve()
    if not root.is_dir():
        raise SystemExit(f"ODDB-main directory not found: {root}")

    seeds = [
        root / "index.html",
        root / "Inheritance.html",
        root / "MOI-stat.html",
    ]

    queue = []
    seen = set()
    depth = {}

    for p in seeds:
        if p.is_file():
            queue.append(p)
            depth[p] = 0
        else:
            print(f"[MISSING] {p}")

    while queue:
        path = queue.pop(0)
        if path in seen or not path.is_file():
            continue
        seen.add(path)

        try:
            refs = inspect(path)
        except Exception as e:
            print(f"[ERROR] {path}: {e}")
            continue

        if depth.get(path, 0) >= 2:
            continue

        for ref in refs:
            p = local_ref(path.parent, ref)
            if not p or not p.is_file():
                continue
            if p.suffix.lower() not in TEXT_EXTS:
                continue
            if p not in seen:
                depth[p] = depth.get(path, 0) + 1
                queue.append(p)

    print("\n" + "=" * 100)
    print("FILES IN ODDB-main WITH STRONG INHERITANCE SIGNAL")
    print("=" * 100)

    ranked = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = read_text(p)
        except Exception:
            continue

        low = text.lower()
        score = 0
        for term, weight in [
            ("autosomal dominant", 10),
            ("autosomal recessive", 10),
            ("x-linked dominant", 20),
            ("x-linked recessive", 20),
            ("isolated cases", 30),
            ("mitochondrial", 5),
            ("inheritance based", 30),
        ]:
            score += min(low.count(term), 50) * weight

        if score:
            ranked.append((score, p))

    ranked.sort(reverse=True, key=lambda x: x[0])

    for score, p in ranked[:40]:
        print(f"{score:6d}  {p.relative_to(root)}")

    print("\nNext target:")
    print("Look for a referenced CSV/TSV/JSON/JS file where disease names/IDs are")
    print("paired directly with the inheritance categories. That file is safer than")
    print("deriving inheritance from phenotype-description text.")


if __name__ == "__main__":
    main()
