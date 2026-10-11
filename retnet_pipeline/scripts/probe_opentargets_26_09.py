#!/usr/bin/env python3
"""
Probe the pinned Open Targets release before full ODDB integration.

Purpose:
- discover the actual dataset directory names under the pinned release
- locate Clinical Target, Drug Mechanism of Action, Drug/Molecule, and Target
- download only ONE parquet part from each dataset
- print parquet schema + first few rows
- save a JSON discovery report

This avoids downloading large datasets before we know the exact 26.09 schema.

Requires:
    pip install pyarrow
"""

import argparse
import json
import re
import shutil
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

try:
    import pyarrow.parquet as pq
except ImportError:
    raise SystemExit(
        "pyarrow is required for parquet inspection.\n"
        "Install it inside the active venv with:\n"
        "  pip install pyarrow"
    )


UA = "ODDB-v1-OpenTargets-probe/1.0"


def fetch_text(url, timeout=120):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def download(url, path, timeout=300):
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r, open(path, "wb") as out:
        shutil.copyfileobj(r, out)


def hrefs_from_listing(url):
    html = fetch_text(url)
    hrefs = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
        href = unescape(m.group(1))
        if href in {"../", "./", "/"}:
            continue
        hrefs.append(href)
    return hrefs


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def discover_dataset_dir(base_url, logical_name, patterns):
    hrefs = hrefs_from_listing(base_url)

    dirs = []
    for href in hrefs:
        if href.endswith("/"):
            name = href.rstrip("/").split("/")[-1]
            dirs.append((name, urljoin(base_url, href)))

    # Exact normalized pattern first.
    for pat in patterns:
        npat = norm(pat)
        for name, url in dirs:
            if norm(name) == npat:
                return name, url

    # Then substring.
    for pat in patterns:
        npat = norm(pat)
        for name, url in dirs:
            if npat in norm(name) or norm(name) in npat:
                return name, url

    return None, None


def find_first_parquet(url, depth=0, max_depth=4):
    if depth > max_depth:
        return None

    hrefs = hrefs_from_listing(url)

    parquet = [
        h for h in hrefs
        if h.lower().endswith(".parquet")
    ]
    if parquet:
        return urljoin(url, sorted(parquet)[0])

    subdirs = [
        h for h in hrefs
        if h.endswith("/") and h not in {"../", "./"}
    ]

    for sub in sorted(subdirs):
        hit = find_first_parquet(
            urljoin(url, sub),
            depth=depth + 1,
            max_depth=max_depth
        )
        if hit:
            return hit

    return None


def preview_parquet(path, n=5):
    pf = pq.ParquetFile(path)
    schema = str(pf.schema_arrow)

    # Read only first row group to avoid loading too much.
    table = pf.read_row_group(0)
    if table.num_rows > n:
        table = table.slice(0, n)

    preview = table.to_pylist()
    return schema, preview


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="26.09")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    base = (
        f"https://ftp.ebi.ac.uk/pub/databases/opentargets/"
        f"platform/{args.release}/output/"
    )

    outdir = Path(args.output_dir)
    sample_dir = outdir / "sample_parquet"
    sample_dir.mkdir(parents=True, exist_ok=True)

    wanted = {
        "clinical_target": [
            "clinicalTarget",
            "clinical_target",
            "drugTargetClinical",
        ],
        "mechanism_of_action": [
            "mechanismOfAction",
            "mechanism_of_action",
            "drugMechanismOfAction",
        ],
        "drug_molecule": [
            "drug_molecule",
            "molecule",
            "drug",
        ],
        "target": [
            "target",
            "targets",
        ],
    }

    print("OPEN TARGETS RELEASE PROBE")
    print("Release:", args.release)
    print("Base:", base)

    # Capture root directory names too.
    root_hrefs = hrefs_from_listing(base)
    root_dirs = sorted(
        h.rstrip("/").split("/")[-1]
        for h in root_hrefs
        if h.endswith("/") and h not in {"../", "./"}
    )

    result = {
        "release": args.release,
        "base_url": base,
        "root_directories": root_dirs,
        "datasets": {},
    }

    for logical, patterns in wanted.items():
        print("\n" + "=" * 100)
        print(logical)
        print("=" * 100)

        name, url = discover_dataset_dir(base, logical, patterns)

        if not url:
            print("Dataset directory not discovered.")
            result["datasets"][logical] = {
                "status": "not_found",
                "patterns": patterns,
            }
            continue

        print("Directory:", name)
        print("URL:", url)

        first = find_first_parquet(url)

        if not first:
            print("No parquet file discovered beneath dataset directory.")
            result["datasets"][logical] = {
                "status": "directory_found_no_parquet",
                "directory_name": name,
                "url": url,
            }
            continue

        local = sample_dir / f"{logical}.parquet"
        print("Sample parquet:", first)
        download(first, local)

        schema, preview = preview_parquet(local)

        print("\nSCHEMA")
        print(schema)

        print("\nFIRST ROWS")
        for i, row in enumerate(preview, 1):
            print(f"\nRow {i}:")
            for k, v in row.items():
                text = repr(v)
                if len(text) > 500:
                    text = text[:497] + "..."
                print(f"  {k}: {text}")

        result["datasets"][logical] = {
            "status": "ok",
            "directory_name": name,
            "url": url,
            "sample_parquet_url": first,
            "sample_local_path": str(local),
            "schema": schema,
            "preview": preview,
        }

    report = outdir / "opentargets_26_09_schema_probe.json"
    report.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )

    print("\n" + "=" * 100)
    print("PROBE COMPLETE")
    print("=" * 100)
    print("Report:", report)

    missing = [
        k for k, v in result["datasets"].items()
        if v.get("status") != "ok"
    ]

    if missing:
        print("\nDatasets needing review:", ", ".join(missing))
        print("\nRoot directories discovered:")
        for d in root_dirs:
            print(" ", d)
    else:
        print("\nAll requested datasets were discovered and sampled.")


if __name__ == "__main__":
    main()
