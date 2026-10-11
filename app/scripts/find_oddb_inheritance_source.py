#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path
from collections import Counter

TARGET_TERMS = [
    "Autosomal dominant",
    "Autosomal recessive",
    "Isolated cases",
    "Mitochondrial",
    "X-linked dominant",
    "X-linked recessive",
]

HEADER_PATTERNS = [
    re.compile(r"inherit", re.I),
    re.compile(r"mode.?of.?inherit", re.I),
    re.compile(r"inheritance.?pattern", re.I),
]

TEXT_EXTENSIONS = {".tsv", ".csv", ".txt"}
SKIP_PARTS = {
    ".git", ".venv", "node_modules", "vendor", "__pycache__"
}

def detect_delim(line: str) -> str:
    if "\t" in line:
        return "\t"
    if line.count(",") >= line.count(";"):
        return ","
    return ";"

def should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)

def scan_file(path: Path, max_lines: int):
    result = {
        "path": str(path),
        "header": "",
        "header_matches": [],
        "term_counts": Counter(),
        "sample_lines": [],
        "score": 0,
    }

    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as f:
            first = f.readline()
            if not first:
                return None
            result["header"] = first.rstrip("\r\n")[:1000]

            delim = detect_delim(first)
            header_fields = [x.strip() for x in first.rstrip("\r\n").split(delim)]

            for field in header_fields:
                if any(p.search(field) for p in HEADER_PATTERNS):
                    result["header_matches"].append(field)

            if result["header_matches"]:
                result["score"] += 100

            # Header may itself contain one of the controlled labels.
            for term in TARGET_TERMS:
                if term.lower() in first.lower():
                    result["term_counts"][term] += 1

            line_no = 1
            for line in f:
                line_no += 1
                low = line.lower()

                matched = False
                for term in TARGET_TERMS:
                    if term.lower() in low:
                        result["term_counts"][term] += 1
                        matched = True

                # Also detect likely legacy shorthand / relationship wording.
                if re.search(r"\bautosomal\b|\bx[- ]linked\b|\bmitochondrial\b|\bisolated\b", low, re.I):
                    matched = True

                if matched and len(result["sample_lines"]) < 5:
                    result["sample_lines"].append(
                        f"L{line_no}: {line.rstrip()[:500]}"
                    )

                if line_no >= max_lines:
                    break

            distinct_terms = sum(1 for n in result["term_counts"].values() if n > 0)
            total_terms = sum(result["term_counts"].values())
            result["score"] += distinct_terms * 20
            result["score"] += min(total_terms, 100)

            # Extra signal for disease/gene tables.
            hlow = result["header"].lower()
            if "disease" in hlow:
                result["score"] += 10
            if "gene" in hlow:
                result["score"] += 5

            if result["score"] == 0:
                return None
            return result

    except Exception as e:
        return {
            "path": str(path),
            "error": str(e),
            "score": -1,
        }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "root",
        nargs="?",
        default="..",
        help="Directory to scan. Default: parent directory.",
    )
    ap.add_argument(
        "--max-lines",
        type=int,
        default=200000,
        help="Maximum lines read per file (default 200000).",
    )
    ap.add_argument(
        "--max-size-mb",
        type=int,
        default=500,
        help="Skip text files larger than this size (default 500 MB).",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    candidates = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > args.max_size_mb * 1024 * 1024:
                continue
        except OSError:
            continue

        r = scan_file(path, args.max_lines)
        if r:
            candidates.append(r)

    candidates.sort(key=lambda x: x.get("score", -1), reverse=True)

    print("ODDB INHERITANCE SOURCE DISCOVERY")
    print("=" * 80)
    print(f"Scanned root: {root}")
    print(f"Candidate files: {len(candidates)}")

    for i, r in enumerate(candidates[:50], start=1):
        print("\n" + "=" * 80)
        print(f"#{i}  SCORE={r.get('score')}")
        print(r["path"])

        if "error" in r:
            print("ERROR:", r["error"])
            continue

        print("Header:")
        print("  " + r["header"])

        if r["header_matches"]:
            print("Inheritance-like header columns:")
            for x in r["header_matches"]:
                print("  -", x)

        if r["term_counts"]:
            print("Controlled inheritance terms found:")
            for term, n in r["term_counts"].most_common():
                print(f"  {term:24s} {n:8d}")

        if r["sample_lines"]:
            print("Example matching rows:")
            for line in r["sample_lines"]:
                print("  " + line)

    if not candidates:
        print("\nNo candidate inheritance source was found.")
        print("This means the inheritance categorization is probably stored in")
        print("an Excel/XLSX file, database dump, ZIP, or another location not")
        print("covered by the scanned text files.")

if __name__ == "__main__":
    main()
