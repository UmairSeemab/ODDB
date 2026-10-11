#!/usr/bin/env python3
"""
Download the official ClinVar variant_summary.txt.gz release and create an
ODDB-gene-filtered GRCh38 staging table.

Design principles:
- Preserve the raw ClinVar file unchanged.
- Match against the canonical ODDB Gene master by HGNC ID when available,
  and by current gene symbol as fallback.
- Do not infer disease mappings at this stage.
- Do not treat ClinVar clinical significance as gene-disease validity.
- Stream the large ClinVar file rather than loading it entirely into memory.
"""

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

DEFAULT_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/"
    "tab_delimited/variant_summary.txt.gz"
)


def clean(x):
    return str(x or "").strip()


def normalized_hgnc(x):
    x = clean(x)
    if not x:
        return ""
    m = re.search(r"(\d+)", x)
    return f"HGNC:{m.group(1)}" if m else x.upper()


def sha256_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download(url, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    req = Request(
        url,
        headers={"User-Agent": "ODDB-v1-ClinVar-import/1.0"}
    )
    with urlopen(req, timeout=180) as response, open(destination, "wb") as out:
        shutil.copyfileobj(response, out)

    return destination


def split_gene_symbols(value):
    """
    Usually ClinVar GeneSymbol is a single symbol, but keep the matcher robust
    to compound values without treating free text as a symbol.
    """
    value = clean(value)
    if not value:
        return []
    return [
        x.strip().upper()
        for x in re.split(r"[;,|]+", value)
        if x.strip()
    ]


def detect_column(fieldnames, possibilities, required=False):
    lookup = {str(c).lower().lstrip("#"): c for c in fieldnames}
    for p in possibilities:
        key = p.lower().lstrip("#")
        if key in lookup:
            return lookup[key]
    if required:
        raise RuntimeError(
            f"Required ClinVar column not found. Tried: {possibilities}. "
            f"Available columns: {fieldnames}"
        )
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genes", required=True,
                    help="Canonical ODDB Gene_v1 TSV")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--staging-output", required=True)
    ap.add_argument("--report-output", required=True)
    ap.add_argument("--source-url", default=DEFAULT_URL)
    ap.add_argument("--assembly", default="GRCh38")
    ap.add_argument(
        "--force-download",
        action="store_true",
        help="Redownload even if the raw ClinVar file already exists."
    )
    args = ap.parse_args()

    genes = pd.read_csv(args.genes, sep="\t", dtype=str).fillna("")

    if "HGNC_ID" not in genes.columns or "GeneSymbol" not in genes.columns:
        raise SystemExit("Gene master must contain HGNC_ID and GeneSymbol.")

    oddb_hgnc = {
        normalized_hgnc(x)
        for x in genes["HGNC_ID"]
        if normalized_hgnc(x)
    }
    oddb_symbols = {
        clean(x).upper()
        for x in genes["GeneSymbol"]
        if clean(x)
    }

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "variant_summary.txt.gz"

    if args.force_download or not raw_path.exists():
        print(f"Downloading ClinVar variant summary from:\n  {args.source_url}")
        download(args.source_url, raw_path)
    else:
        print(f"Using existing raw ClinVar file:\n  {raw_path}")

    checksum = sha256_file(raw_path)
    retrieved_utc = datetime.now(timezone.utc).isoformat()

    # Inspect header.
    with gzip.open(raw_path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames or []

    gene_symbol_col = detect_column(
        fields, ["GeneSymbol", "Gene Symbol"], required=True
    )
    hgnc_col = detect_column(
        fields, ["HGNC_ID", "HGNC ID"], required=False
    )
    assembly_col = detect_column(
        fields, ["Assembly"], required=True
    )
    variation_id_col = detect_column(
        fields, ["VariationID", "Variation ID"], required=True
    )

    out_path = Path(args.staging_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Preserve all ClinVar columns, plus ODDB matching metadata.
    extra_fields = [
        "ODDB_Matched_HGNC_ID",
        "ODDB_Matched_GeneSymbol",
        "ODDB_Gene_Match_Method",
        "ClinVar_Source_URL",
        "ClinVar_Retrieved_UTC",
        "ClinVar_Raw_SHA256",
    ]
    output_fields = fields + [x for x in extra_fields if x not in fields]

    hgnc_to_symbol = dict(
        zip(
            genes["HGNC_ID"].map(normalized_hgnc),
            genes["GeneSymbol"].map(lambda x: clean(x).upper())
        )
    )
    symbol_to_hgnc = dict(
        zip(
            genes["GeneSymbol"].map(lambda x: clean(x).upper()),
            genes["HGNC_ID"].map(normalized_hgnc)
        )
    )

    total_rows = 0
    assembly_rows = 0
    matched_rows = 0
    matched_by_hgnc = 0
    matched_by_symbol = 0
    matched_variations = set()
    matched_genes = set()

    with gzip.open(
        raw_path, "rt", encoding="utf-8", errors="replace", newline=""
    ) as fh, open(
        out_path, "w", encoding="utf-8", newline=""
    ) as out:
        reader = csv.DictReader(fh, delimiter="\t")
        writer = csv.DictWriter(
            out,
            fieldnames=output_fields,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()

        for row in reader:
            total_rows += 1

            if clean(row.get(assembly_col, "")) != args.assembly:
                continue
            assembly_rows += 1

            cv_hgnc = normalized_hgnc(row.get(hgnc_col, "")) if hgnc_col else ""
            cv_symbols = split_gene_symbols(row.get(gene_symbol_col, ""))

            matched_hgnc = ""
            matched_symbol = ""
            method = ""

            if cv_hgnc and cv_hgnc in oddb_hgnc:
                matched_hgnc = cv_hgnc
                matched_symbol = hgnc_to_symbol.get(cv_hgnc, "")
                method = "HGNC_ID"
                matched_by_hgnc += 1
            else:
                symbol_hit = next(
                    (s for s in cv_symbols if s in oddb_symbols),
                    ""
                )
                if symbol_hit:
                    matched_symbol = symbol_hit
                    matched_hgnc = symbol_to_hgnc.get(symbol_hit, "")
                    method = "GeneSymbol"
                    matched_by_symbol += 1

            if not matched_hgnc and not matched_symbol:
                continue

            matched_rows += 1
            vid = clean(row.get(variation_id_col, ""))
            if vid:
                matched_variations.add(vid)
            if matched_hgnc:
                matched_genes.add(matched_hgnc)

            row["ODDB_Matched_HGNC_ID"] = matched_hgnc
            row["ODDB_Matched_GeneSymbol"] = matched_symbol
            row["ODDB_Gene_Match_Method"] = method
            row["ClinVar_Source_URL"] = args.source_url
            row["ClinVar_Retrieved_UTC"] = retrieved_utc
            row["ClinVar_Raw_SHA256"] = checksum
            writer.writerow(row)

    genes_without_clinvar = sorted(oddb_hgnc - matched_genes)

    report = {
        "Source": "NCBI ClinVar variant_summary",
        "Source_URL": args.source_url,
        "Retrieved_UTC": retrieved_utc,
        "Raw_File": str(raw_path),
        "Raw_SHA256": checksum,
        "Assembly_Filter": args.assembly,
        "ODDB_Genes_Input": len(oddb_hgnc),
        "ClinVar_Rows_Total_All_Assemblies": total_rows,
        "ClinVar_Rows_Selected_Assembly": assembly_rows,
        "Matched_ClinVar_Rows": matched_rows,
        "Unique_ClinVar_VariationIDs": len(matched_variations),
        "ODDB_Genes_With_ClinVar_Variants": len(matched_genes),
        "ODDB_Genes_Without_ClinVar_Variants": len(genes_without_clinvar),
        "Rows_Matched_By_HGNC_ID": matched_by_hgnc,
        "Rows_Matched_By_GeneSymbol_Fallback": matched_by_symbol,
        "Staging_Output": str(out_path),
    }

    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"Metric": k, "Value": v} for k, v in report.items()]
    ).to_csv(report_path, sep="\t", index=False)

    no_cv_path = report_path.with_name(
        report_path.stem + "_genes_without_clinvar.tsv"
    )
    genes[
        genes["HGNC_ID"].map(normalized_hgnc).isin(genes_without_clinvar)
    ].to_csv(no_cv_path, sep="\t", index=False)

    manifest_path = raw_dir / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nODDB CLINVAR STAGING BUILD")
    for k, v in report.items():
        print(f"{k}: {v}")

    print(f"\nGenes without matched ClinVar rows: {no_cv_path}")
    print(f"Source manifest: {manifest_path}")
    print("\nNo disease mapping or clinical-significance filtering was applied.")


if __name__ == "__main__":
    main()
