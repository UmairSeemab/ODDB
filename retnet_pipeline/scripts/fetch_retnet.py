#!/usr/bin/env python3
from pathlib import Path
from datetime import date
import csv
import re
from playwright.sync_api import sync_playwright

URL = 'https://retnet.org/summaries'
OUT = Path(__file__).resolve().parents[1] / 'data' / 'raw'
OUT.mkdir(parents=True, exist_ok=True)


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def semantic_cell_text(cell):
    """Return cell text while preserving boundaries between adjacent links.

    RetNet renders lists of gene/locus symbols as adjacent anchor elements.
    A plain cell.inner_text() can concatenate those anchors (e.g. ABCA4ARMS2C2),
    which makes downstream parsing impossible. When a cell contains multiple
    anchors, use the anchor labels as explicit space-separated tokens.
    """
    try:
        anchors = [clean(x) for x in cell.locator('a').all_inner_texts()]
        anchors = [x for x in anchors if x]
    except Exception:
        anchors = []

    raw = clean(cell.inner_text())

    # RetNet gene/locus cells typically contain one link per symbol. Two or
    # more links is a strong signal that symbol boundaries must be restored.
    if len(anchors) >= 2:
        return ' '.join(anchors)

    # A single-link cell is safe as raw text and may contain surrounding text.
    return raw


def classify_table(rows):
    """Classify a RetNet summary table from its header text."""
    header = ' | '.join(' | '.join(r) for r in rows[:4]).lower()
    if 'mapped and identified genes' in header:
        return 'Mendelian'
    if 'mapped loci' in header and 'gene not identified' in header:
        return 'Unresolved locus'
    if 'mapped and named loci' in header:
        return 'Complex'
    return 'Other'


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1200})
        page.goto(URL, wait_until='networkidle', timeout=120000)
        page.wait_for_timeout(1500)

        body_text = page.locator('body').inner_text()
        if 'Total number of genes to date' not in body_text:
            browser.close()
            raise RuntimeError(
                'RetNet summary page did not render expected content; no file written.'
            )

        tables = []
        table_count = page.locator('table').count()
        for ti in range(table_count):
            table = page.locator('table').nth(ti)
            rows = []
            tr_count = table.locator('tr').count()
            for ri in range(tr_count):
                tr = table.locator('tr').nth(ri)
                cells_loc = tr.locator('th,td')
                cells = []
                for ci in range(cells_loc.count()):
                    cells.append(semantic_cell_text(cells_loc.nth(ci)))
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)

        browser.close()

    if len(tables) < 3:
        raise RuntimeError(
            f'Expected at least 3 RetNet summary tables, found {len(tables)}; no file written.'
        )

    stamp = date.today().isoformat()

    # Preserve auditable rendered tables. These are the files consumed by
    # harmonize_retnet.py.
    for i, rows in enumerate(tables, 1):
        width = max(len(r) for r in rows)
        path = OUT / f'retnet_rendered_table_{i}_{stamp}.tsv'
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, delimiter='\t')
            for r in rows:
                w.writerow(r + [''] * (width - len(r)))

    (OUT / f'retnet_rendered_text_{stamp}.txt').write_text(
        body_text, encoding='utf-8'
    )

    print(f'Saved {len(tables)} rendered tables to {OUT}')
    for i, rows in enumerate(tables, 1):
        kind = classify_table(rows)
        width = max(len(r) for r in rows)
        print(f'  table {i}: {kind}; {len(rows)} rows; max {width} columns')

    print('\nAudit preview:')
    for i, rows in enumerate(tables[:3], 1):
        print(f'  Table {i}:')
        for r in rows[:3]:
            print('    ' + ' | '.join(r)[:400])


if __name__ == '__main__':
    main()
