#!/usr/bin/env python3
import csv, io, urllib.request, argparse
from pathlib import Path

HGNC_URL='https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt'
ROOT=Path(__file__).resolve().parents[1]

def split_multi(v):
    if not v: return []
    vals=[]
    for part in v.replace('"','').replace("'",'').split('|'):
        for x in part.split(','):
            x=x.strip()
            if x: vals.append(x)
    return vals

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default=str(ROOT/'data/processed/oddb_retnet_candidates.tsv'))
    ap.add_argument('--output',default=str(ROOT/'data/processed/oddb_retnet_candidates_hgnc.tsv'))
    args=ap.parse_args()
    print('Downloading current HGNC complete set...')
    with urllib.request.urlopen(HGNC_URL, timeout=120) as r:
        text=r.read().decode('utf-8-sig')
    records=list(csv.DictReader(io.StringIO(text), delimiter='\t'))
    approved={}; aliases={}; previous={}
    for r in records:
        sym=(r.get('symbol') or '').strip()
        if sym: approved[sym.upper()]=r
        for a in split_multi(r.get('alias_symbol','')): aliases.setdefault(a.upper(),r)
        for a in split_multi(r.get('prev_symbol','')): previous.setdefault(a.upper(),r)
    rows=[]
    with open(args.input,encoding='utf-8') as f:
        rd=csv.DictReader(f,delimiter='\t')
        fields=rd.fieldnames
        for x in rd:
            raw=(x.get('RetNet_Symbol') or '').strip(); key=raw.upper(); rec=None; status='not_found'
            if key in approved: rec=approved[key]; status='approved'
            elif key in aliases: rec=aliases[key]; status='alias'
            elif key in previous: rec=previous[key]; status='previous_symbol'
            x['HGNC_Match_Status']=status
            x['Approved_GeneSymbol']=(rec or {}).get('symbol','')
            x['HGNC_ID']=(rec or {}).get('hgnc_id','')
            rows.append(x)
    with open(args.output,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t'); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print('HGNC normalization:', dict(Counter(r['HGNC_Match_Status'] for r in rows)))

if __name__=='__main__': main()
