#!/usr/bin/env python3
"""Fetch RetNet's detailed disease table for evidence-method/reference staging.

This preserves raw rendered rows for audit. It does not try to infer an approved gene
from RetNet aliases; HGNC normalization remains a separate required step.
"""
from pathlib import Path
from datetime import date
import csv, re
from playwright.sync_api import sync_playwright
URL='https://retnet.org/disease'
OUT=Path(__file__).resolve().parents[1]/'data'/'raw'; OUT.mkdir(parents=True,exist_ok=True)
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def main():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1800,'height':1200})
        page.goto(URL,wait_until='networkidle',timeout=120000); page.wait_for_timeout(1500)
        body=page.locator('body').inner_text()
        if 'Total entries' not in body or 'How Identified' not in body:
            raise RuntimeError('Detailed RetNet page did not render expected content; no file written.')
        rows=[]
        for table in page.locator('table').all():
            for tr in table.locator('tr').all():
                cells=[clean(x.inner_text()) for x in tr.locator('th,td').all()]
                if len(cells)>=4: rows.append(cells)
        b.close()
    if len(rows)<300: raise RuntimeError(f'Only {len(rows)} detail rows extracted; source structure may have changed.')
    stamp=date.today().isoformat(); path=OUT/f'retnet_disease_details_rendered_{stamp}.tsv'
    width=max(len(r) for r in rows)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f,delimiter='\t'); [w.writerow(r+['']*(width-len(r))) for r in rows]
    (OUT/f'retnet_disease_details_text_{stamp}.txt').write_text(body,encoding='utf-8')
    print(f'Saved {len(rows)} rendered detail rows to {path}')
if __name__=='__main__': main()
