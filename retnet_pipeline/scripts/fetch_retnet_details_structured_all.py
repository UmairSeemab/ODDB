#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://retnet.org/disease"

CELL_JS = r"""
(el) => {
  function norm(s) {
    return (s || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }
  const segments = [];
  for (const node of el.childNodes) {
    const t = norm(node.textContent);
    if (t) segments.push(t);
  }
  const links = Array.from(el.querySelectorAll("a")).map(a => ({
    text: norm(a.textContent),
    href: a.href || ""
  })).filter(x => x.text || x.href);
  return {
    text: norm(el.innerText || el.textContent),
    segments,
    links,
    html: el.innerHTML || ""
  };
}
"""

HEADING_JS = r"""
(el) => {
  let n = el.previousElementSibling;
  while (n) {
    if (/^H[1-6]$/.test(n.tagName)) {
      return (n.innerText || n.textContent || "").replace(/\s+/g, " ").trim();
    }
    n = n.previousElementSibling;
  }
  const p = el.parentElement;
  if (p) {
    let s = p.previousElementSibling;
    while (s) {
      if (/^H[1-6]$/.test(s.tagName)) {
        return (s.innerText || s.textContent || "").replace(/\s+/g, " ").trim();
      }
      s = s.previousElementSibling;
    }
  }
  return "";
}
"""

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def is_detail_header(vals):
    low = [normalize(v).lower() for v in vals]
    joined = " | ".join(low)
    return (
        "symbols" in joined
        and "omim" in joined
        and "location" in joined
        and "diseases" in joined
        and "protein" in joined
        and "references" in joined
    )

def primary_symbol_from_links(links):
    for item in links:
        href = item.get("href", "")
        text = normalize(item.get("text", ""))
        if not text:
            continue
        try:
            path = urlparse(href).path.rstrip("/")
        except Exception:
            path = ""
        if "/disease/" in path:
            return text
    return ""

def fallback_primary_symbol(text, segments):
    if segments:
        first = normalize(segments[0])
    else:
        first = normalize(text)
    # First token before obvious OMIM digits / spaces. Handles symbols like KSS, LHON, 14q11.2.
    m = re.match(r"^([^\s]+)", first)
    return m.group(1) if m else ""

def disease_and_protein_segments(segments, links):
    """
    RetNet usually renders:
      disease 1
      disease 2
      ...
      protein description
      [Gene]
      [ClinGen]

    We conservatively treat the final non-link segment before the first Gene/ClinGen
    link marker as Protein_Text, and earlier segments as disease/phenotype segments.
    We also retain the original segments/HTML for audit.
    """
    segs = [normalize(x) for x in segments if normalize(x)]
    marker_texts = {
        normalize(x.get("text", "")).lower()
        for x in links
        if ("ncbi.nlm.nih.gov" in x.get("href", "") or
            "clinicalgenome.org" in x.get("href", ""))
    }

    clean = []
    for s in segs:
        sl = s.lower()
        if sl in marker_texts:
            continue
        if sl.startswith("[gene]") or sl.startswith("[clingen]"):
            continue
        clean.append(s)

    if not clean:
        return [], ""

    if len(clean) == 1:
        # Could be a phenotype-only/locus entry without protein.
        return clean, ""

    protein = clean[-1]
    diseases = clean[:-1]
    return diseases, protein

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--output-dir", default="data/raw")
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    records = []
    matched_tables = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1800, "height": 1400})
        page.goto(args.url, wait_until="networkidle", timeout=120000)

        tables = page.locator("table")

        for ti in range(tables.count()):
            table = tables.nth(ti)
            rows = table.locator("tr")

            header_row = None
            for ri in range(min(rows.count(), 8)):
                cells = rows.nth(ri).locator("th,td")
                vals = [
                    normalize(cells.nth(ci).inner_text())
                    for ci in range(cells.count())
                ]
                if is_detail_header(vals):
                    header_row = ri
                    break

            if header_row is None:
                continue

            matched_tables += 1
            section_heading = normalize(table.evaluate(HEADING_JS))

            for ri in range(header_row + 1, rows.count()):
                cells = rows.nth(ri).locator("td")
                if cells.count() < 5:
                    continue

                parsed = [cells.nth(ci).evaluate(CELL_JS) for ci in range(5)]
                if not any(x["text"] for x in parsed):
                    continue

                symbol = primary_symbol_from_links(parsed[0]["links"])
                if not symbol:
                    symbol = fallback_primary_symbol(
                        parsed[0]["text"], parsed[0]["segments"]
                    )

                disease_segments, protein_text = disease_and_protein_segments(
                    parsed[2]["segments"], parsed[2]["links"]
                )

                records.append({
                    "RetNet_Primary_Symbol": symbol,
                    "Section_Heading": section_heading,
                    "Table_Index": str(ti),
                    "Row_Index": str(ri),
                    "Symbols_OMIM_Text": parsed[0]["text"],
                    "Symbols_OMIM_Segments": json.dumps(parsed[0]["segments"], ensure_ascii=False),
                    "Symbols_OMIM_Links": json.dumps(parsed[0]["links"], ensure_ascii=False),
                    "Location": parsed[1]["text"],
                    "Disease_Phenotype_Segments": json.dumps(disease_segments, ensure_ascii=False),
                    "Protein_Text": protein_text,
                    "Diseases_Protein_Text": parsed[2]["text"],
                    "Diseases_Protein_Segments": json.dumps(parsed[2]["segments"], ensure_ascii=False),
                    "Diseases_Protein_Links": json.dumps(parsed[2]["links"], ensure_ascii=False),
                    "Diseases_Protein_HTML": parsed[2]["html"],
                    "How_Identified_Comments_Text": parsed[3]["text"],
                    "How_Identified_Comments_Segments": json.dumps(parsed[3]["segments"], ensure_ascii=False),
                    "References_Text": parsed[4]["text"],
                    "References_Segments": json.dumps(parsed[4]["segments"], ensure_ascii=False),
                    "References_Links": json.dumps(parsed[4]["links"], ensure_ascii=False)
                })

        browser.close()

    if not records:
        raise SystemExit("No RetNet detailed disease records were extracted.")

    outfile = outdir / f"retnet_disease_details_structured_all_{args.date}.tsv"
    fields = list(records[0].keys())
    with outfile.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(records)

    primary = [r["RetNet_Primary_Symbol"] for r in records if r["RetNet_Primary_Symbol"]]
    unique_primary = sorted(set(primary))

    print(f"Matched detailed RetNet tables: {matched_tables}")
    print(f"Extracted detailed records: {len(records)}")
    print(f"Unique primary RetNet symbols/loci: {len(unique_primary)}")
    print(f"Output: {outfile}")

    if len(unique_primary) < 350:
        print("\nWARNING: fewer than 350 unique primary entries were extracted.")
        print("Do not use this file for harmonization until the extraction is checked.")
    else:
        print("\nCoverage looks plausible for the current RetNet disease table.")

    print("\nFirst 3 parsed records:")
    for r in records[:3]:
        print(
            f"  {r['RetNet_Primary_Symbol']} | {r['Location']} | "
            f"{r['Disease_Phenotype_Segments']} | protein={r['Protein_Text']}"
        )

if __name__ == "__main__":
    main()
