#!/usr/bin/env python3
"""
Probe Open Targets Platform 26.09 clinical_report schema.

Downloads only ONE parquet part from:
https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.09/output/clinical_report/

and prints the schema + first rows.

Requires pyarrow (already installed for the ODDB pipeline).
"""

import argparse
import json
import re
import shutil
import time
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pyarrow.parquet as pq


UA = "ODDB-v1-OpenTargets-clinical-report-probe/1.0"


def fetch_text(url, timeout=120, retries=6):
    last = None

    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            if attempt == retries:
                break
            wait = min(5 * attempt, 30)
            print(
                f"Temporary network error: {exc}\n"
                f"Retrying in {wait}s..."
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Could not read {url} after {retries} attempts: {last}"
    )


def parquet_urls(dataset_url):
    html = fetch_text(dataset_url)

    hrefs = re.findall(
        r'href=["\']([^"\']+)["\']',
        html,
        flags=re.I
    )

    urls = []

    for href in hrefs:
        href = unescape(href).strip()
        clean_href = href.split("?", 1)[0]

        if clean_href.lower().endswith(".parquet"):
            urls.append(urljoin(dataset_url, clean_href))

    return sorted(set(urls))


def download(url, path, timeout=900, retries=6):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and path.stat().st_size > 0:
        return

    last = None

    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=timeout) as r, open(path, "wb") as out:
                shutil.copyfileobj(r, out, length=1024 * 1024)
            return
        except Exception as exc:
            last = exc
            if path.exists():
                path.unlink()
            if attempt == retries:
                break
            wait = min(10 * attempt, 60)
            print(
                f"Download error: {exc}\n"
                f"Retrying in {wait}s..."
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Could not download {url} after {retries} attempts: {last}"
    )


def json_safe(v):
    if v is None:
        return None

    if hasattr(v, "tolist"):
        try:
            return json_safe(v.tolist())
        except Exception:
            pass

    if hasattr(v, "item"):
        try:
            return json_safe(v.item())
        except Exception:
            pass

    if isinstance(v, dict):
        return {str(k): json_safe(x) for k, x in v.items()}

    if isinstance(v, (list, tuple)):
        return [json_safe(x) for x in v]

    if isinstance(v, (str, int, float, bool)):
        return v

    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="26.09")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    dataset_url = (
        "https://ftp.ebi.ac.uk/pub/databases/opentargets/"
        f"platform/{args.release}/output/clinical_report/"
    )

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    print("OPEN TARGETS CLINICAL_REPORT SCHEMA PROBE")
    print("Release:", args.release)
    print("URL:", dataset_url)

    urls = parquet_urls(dataset_url)

    if not urls:
        raise SystemExit(
            "No parquet files found in clinical_report directory."
        )

    print("Parquet parts discovered:", len(urls))

    sample_url = urls[0]
    sample_path = outdir / "clinical_report_sample.parquet"

    print("Sample:", sample_url)
    download(sample_url, sample_path)

    pf = pq.ParquetFile(sample_path)

    print("\nSCHEMA")
    print(pf.schema_arrow)

    table = pf.read_row_group(0)

    if table.num_rows > 5:
        table = table.slice(0, 5)

    rows = [json_safe(x) for x in table.to_pylist()]

    print("\nFIRST ROWS")

    for i, row in enumerate(rows, 1):
        print(f"\nRow {i}:")
        for k, v in row.items():
            text = repr(v)
            if len(text) > 1000:
                text = text[:997] + "..."
            print(f"  {k}: {text}")

    report = {
        "release": args.release,
        "dataset_url": dataset_url,
        "parquet_part_count": len(urls),
        "sample_url": sample_url,
        "sample_path": str(sample_path),
        "schema": str(pf.schema_arrow),
        "first_rows": rows,
    }

    report_path = outdir / "clinical_report_schema_probe.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nPROBE COMPLETE")
    print("Report:", report_path)


if __name__ == "__main__":
    main()
