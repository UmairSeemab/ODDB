#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://retnet.org/disease"

JS_CELL = r"""
(el) => {
  function norm(s) {
    return (s || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }

  const childSegments = [];
  for (const node of el.childNodes) {
    const t = norm(node.textContent);
    if (t) childSegments.push(t);
  }

  const links = Array.from(el.querySelectorAll("a")).map(a => ({
    text: norm(a.textContent),
    href: a.href || ""
  })).filter(x => x.text || x.href);

  return {
    text: norm(el.innerText || el.textContent),
    segments: childSegments,
    links: links,
    html: el.innerHTML || ""
  };
}
"""

def classify_table(headers):
    s = " | ".join(headers).lower()
    return (
        "symbols" in s and
        "omim" in s and
        "location" in s and
        "diseases" in s and
        "references" in s
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--output-dir", default="data/raw")
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.goto(args.url, wait_until="networkidle", timeout=120000)

        tables = page.locator("table")
        chosen = None
        header_row = None

        for ti in range(tables.count()):
            table = tables.nth(ti)
            rows = table.locator("tr")
            for ri in range(min(rows.count(), 8)):
                cells = rows.nth(ri).locator("th,td")
                vals = []
                for ci in range(cells.count()):
                    vals.append(re.sub(r"\s+", " ", cells.nth(ci).inner_text()).strip())
                if classify_table(vals):
                    chosen = table
                    header_row = ri
                    break
            if chosen is not None:
                break

        if chosen is None:
            browser.close()
            raise SystemExit("Could not locate the RetNet disease detail table.")

        rows = chosen.locator("tr")
        records = []

        for ri in range(header_row + 1, rows.count()):
            cells = rows.nth(ri).locator("td")
            if cells.count() < 5:
                continue

            parsed = [cells.nth(ci).evaluate(JS_CELL) for ci in range(5)]

            # Skip empty rows
            if not any(x["text"] for x in parsed):
                continue

            def links_json(x):
                return json.dumps(x["links"], ensure_ascii=False)

            def segments_json(x):
                return json.dumps(x["segments"], ensure_ascii=False)

            records.append({
                "Symbols_OMIM_Text": parsed[0]["text"],
                "Symbols_OMIM_Segments": segments_json(parsed[0]),
                "Symbols_OMIM_Links": links_json(parsed[0]),
                "Symbols_OMIM_HTML": parsed[0]["html"],
                "Location": parsed[1]["text"],
                "Diseases_Protein_Text": parsed[2]["text"],
                "Diseases_Protein_Segments": segments_json(parsed[2]),
                "Diseases_Protein_Links": links_json(parsed[2]),
                "Diseases_Protein_HTML": parsed[2]["html"],
                "How_Identified_Comments_Text": parsed[3]["text"],
                "How_Identified_Comments_Segments": segments_json(parsed[3]),
                "References_Text": parsed[4]["text"],
                "References_Segments": segments_json(parsed[4]),
                "References_Links": links_json(parsed[4])
            })

        browser.close()

    outfile = outdir / f"retnet_disease_details_structured_{args.date}.tsv"
    fields = list(records[0].keys()) if records else []
    with outfile.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(records)

    print(f"Saved {len(records)} structured RetNet disease records.")
    print(f"Output: {outfile}")
    if records:
        print("\nFirst record:")
        for k in [
            "Symbols_OMIM_Text",
            "Symbols_OMIM_Segments",
            "Symbols_OMIM_Links",
            "Diseases_Protein_Text",
            "Diseases_Protein_Segments",
            "Diseases_Protein_Links"
        ]:
            print(f"{k}: {records[0][k]}")

if __name__ == "__main__":
    main()
