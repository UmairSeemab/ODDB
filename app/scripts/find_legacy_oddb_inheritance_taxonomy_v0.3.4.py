#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import zipfile
from collections import Counter
from pathlib import Path

TEXT_EXTS = {
    ".tsv", ".csv", ".txt", ".json", ".js", ".php", ".html", ".htm",
    ".sql", ".r", ".py", ".md", ".xml", ".yml", ".yaml"
}
XLSX_EXTS = {".xlsx", ".xlsm"}
SKIP_PARTS = {".git", ".venv", "node_modules", "vendor", "__pycache__", ".idea"}

TERMS = [
    ("Inheritance Based Categorization", 120),
    ("Inheritance Based", 80),
    ("Autosomal dominant", 40),
    ("Autosomal recessive", 40),
    ("Isolated cases", 80),
    ("Mitochondrial", 30),
    ("X-linked dominant", 80),
    ("X-linked recessive", 80),
]

# "Other" is intentionally not searched as a standalone term because it is too nonspecific.


def should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def score_text(text: str):
    low = text.lower()
    counts = Counter()
    score = 0

    for term, weight in TERMS:
        n = low.count(term.lower())
        if n:
            counts[term] = n
            score += weight + min(n, 100)

    # Strong structural signals for the original ODDB categorization.
    if "diseaseid" in low or "disease_id" in low:
        score += 15
    if "ocular.disease" in low or "ocular disease" in low:
        score += 15
    if "disease.category" in low or "disease category" in low:
        score += 10
    if "inheritance" in low:
        score += 20

    return score, counts


def text_snippets(text: str, max_snippets=8):
    lines = text.splitlines()
    out = []
    term_re = re.compile(
        r"Inheritance Based Categorization|Inheritance Based|"
        r"Autosomal dominant|Autosomal recessive|Isolated cases|"
        r"Mitochondrial|X-linked dominant|X-linked recessive",
        re.I,
    )
    for i, line in enumerate(lines, start=1):
        if term_re.search(line):
            out.append(f"L{i}: {line[:700]}")
            if len(out) >= max_snippets:
                break
    return out


def scan_text_file(path: Path, max_bytes: int):
    try:
        if path.stat().st_size > max_bytes:
            return None
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        score, counts = score_text(text)
        if score <= 0 or not counts:
            return None
        return {
            "path": str(path),
            "kind": "text",
            "score": score,
            "counts": counts,
            "snippets": text_snippets(text),
        }
    except Exception as e:
        return {"path": str(path), "kind": "text", "score": -1, "error": str(e)}


def scan_xlsx(path: Path, max_cells: int):
    try:
        import openpyxl
    except Exception:
        return None

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        all_text = []
        snippets = []
        cells = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                vals = []
                for cell in row:
                    if cell.value is None:
                        continue
                    s = str(cell.value)
                    vals.append(s)
                    all_text.append(s)
                    cells += 1
                    if cells >= max_cells:
                        break
                row_text = "\t".join(vals)
                if row_text and re.search(
                    r"Inheritance Based Categorization|Inheritance Based|"
                    r"Autosomal dominant|Autosomal recessive|Isolated cases|"
                    r"Mitochondrial|X-linked dominant|X-linked recessive",
                    row_text, re.I
                ):
                    if len(snippets) < 8:
                        snippets.append(f"{ws.title}: {row_text[:700]}")
                if cells >= max_cells:
                    break
            if cells >= max_cells:
                break

        text = "\n".join(all_text)
        score, counts = score_text(text)
        if score <= 0 or not counts:
            return None
        return {
            "path": str(path),
            "kind": "xlsx",
            "score": score + 25,
            "counts": counts,
            "snippets": snippets,
        }
    except Exception as e:
        return {"path": str(path), "kind": "xlsx", "score": -1, "error": str(e)}


def scan_zip(path: Path, max_member_bytes: int):
    results = []
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size > max_member_bytes:
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix not in TEXT_EXTS:
                    continue
                try:
                    raw = z.read(info)
                    text = raw.decode("utf-8-sig", errors="replace")
                except Exception:
                    continue
                score, counts = score_text(text)
                if score > 0 and counts:
                    results.append({
                        "path": f"{path} :: {info.filename}",
                        "kind": "zip-member",
                        "score": score + 10,
                        "counts": counts,
                        "snippets": text_snippets(text),
                    })
    except Exception as e:
        results.append({
            "path": str(path), "kind": "zip", "score": -1, "error": str(e)
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="..")
    ap.add_argument("--max-file-mb", type=int, default=80)
    ap.add_argument("--max-xlsx-cells", type=int, default=300000)
    ap.add_argument("--top", type=int, default=60)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    max_bytes = args.max_file_mb * 1024 * 1024
    results = []

    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue

        suffix = path.suffix.lower()
        if suffix in TEXT_EXTS:
            r = scan_text_file(path, max_bytes)
            if r:
                results.append(r)
        elif suffix in XLSX_EXTS:
            r = scan_xlsx(path, args.max_xlsx_cells)
            if r:
                results.append(r)
        elif suffix == ".zip":
            results.extend(scan_zip(path, max_bytes))

    results.sort(key=lambda x: x.get("score", -1), reverse=True)

    print("ODDB LEGACY INHERITANCE TAXONOMY DISCOVERY v0.3.4")
    print("=" * 88)
    print(f"Root: {root}")
    print(f"Candidates: {len(results)}")

    for i, r in enumerate(results[:args.top], start=1):
        print("\n" + "=" * 88)
        print(f"#{i} SCORE={r.get('score')} TYPE={r.get('kind')}")
        print(r["path"])
        if "error" in r:
            print("ERROR:", r["error"])
            continue

        print("Matched controlled labels:")
        for term, n in r["counts"].most_common():
            print(f"  {term:32s} {n:8d}")

        if r.get("snippets"):
            print("Examples:")
            for s in r["snippets"]:
                print("  " + s)

    print("\n" + "=" * 88)
    print("PRIORITY")
    print("Prefer a file containing the original ODDB disease membership together with")
    print("multiple labels among: Isolated cases, X-linked dominant, X-linked recessive,")
    print("Autosomal dominant/recessive, and Mitochondrial.")
    print("Do not use free-text Phenotypes rows merely because inheritance words occur there.")


if __name__ == "__main__":
    main()
