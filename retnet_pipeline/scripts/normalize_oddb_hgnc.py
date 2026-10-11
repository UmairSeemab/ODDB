#!/usr/bin/env python3
import argparse
import csv
import io
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HGNC_URL = 'https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt'


def split_multi(value):
    if not value:
        return []
    value = value.replace('"', '').replace("'", '')
    out = []
    for part in value.split('|'):
        for item in part.split(','):
            item = item.strip()
            if item:
                out.append(item)
    return out


def build_index(records):
    approved = {}
    aliases = defaultdict(list)
    previous = defaultdict(list)
    for r in records:
        symbol = (r.get('symbol') or '').strip()
        if symbol:
            approved[symbol.upper()] = r
        for a in split_multi(r.get('alias_symbol', '')):
            aliases[a.upper()].append(r)
        for p in split_multi(r.get('prev_symbol', '')):
            previous[p.upper()].append(r)
    return approved, aliases, previous


def unique_record(records):
    seen = {}
    for r in records:
        hid = (r.get('hgnc_id') or '').strip()
        if hid:
            seen[hid] = r
    return list(seen.values())


def match_symbol(raw, approved, aliases, previous):
    key = (raw or '').strip().upper()
    if not key:
        return 'blank', None
    if key in approved:
        return 'approved', approved[key]
    a = unique_record(aliases.get(key, []))
    if len(a) == 1:
        return 'alias', a[0]
    if len(a) > 1:
        return 'ambiguous_alias', None
    p = unique_record(previous.get(key, []))
    if len(p) == 1:
        return 'previous_symbol', p[0]
    if len(p) > 1:
        return 'ambiguous_previous_symbol', None
    return 'not_found', None


def main():
    ap = argparse.ArgumentParser(description='Annotate ODDB GeneSymbol values with current HGNC identifiers without overwriting the original symbols.')
    ap.add_argument('--input', required=True, help='ODDB TSV, e.g. Gene_Disease_Drug_merged.tsv')
    ap.add_argument('--output', default='data/processed/oddb_gene_disease_drug_hgnc.tsv')
    ap.add_argument('--mapping-output', default='data/processed/oddb_gene_hgnc_mapping.tsv')
    args = ap.parse_args()

    print('Downloading current HGNC complete set...')
    with urllib.request.urlopen(HGNC_URL, timeout=120) as r:
        text = r.read().decode('utf-8-sig')
    records = list(csv.DictReader(io.StringIO(text), delimiter='\t'))
    approved, aliases, previous = build_index(records)

    in_path = Path(args.input)
    out_path = Path(args.output)
    map_path = Path(args.mapping_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.parent.mkdir(parents=True, exist_ok=True)

    with in_path.open(encoding='utf-8-sig', errors='replace') as f:
        rd = csv.DictReader(f, delimiter='\t')
        original_fields = rd.fieldnames or []
        rows = list(rd)

    symbols = sorted({(r.get('GeneSymbol') or '').strip() for r in rows if (r.get('GeneSymbol') or '').strip()}, key=str.upper)
    mapping = {}
    map_rows = []
    for raw in symbols:
        status, rec = match_symbol(raw, approved, aliases, previous)
        approved_symbol = (rec or {}).get('symbol', '')
        hgnc_id = (rec or {}).get('hgnc_id', '')
        mapping[raw.upper()] = (status, approved_symbol, hgnc_id)
        map_rows.append({
            'ODDB_Original_GeneSymbol': raw,
            'HGNC_Match_Status': status,
            'Approved_GeneSymbol': approved_symbol,
            'HGNC_ID': hgnc_id,
        })

    extra = ['ODDB_Original_GeneSymbol', 'HGNC_Match_Status', 'Approved_GeneSymbol', 'HGNC_ID']
    fields = original_fields + [x for x in extra if x not in original_fields]

    out_rows = []
    for r in rows:
        raw = (r.get('GeneSymbol') or '').strip()
        status, approved_symbol, hgnc_id = mapping.get(raw.upper(), ('blank', '', '')) if raw else ('blank', '', '')
        r = dict(r)
        r['ODDB_Original_GeneSymbol'] = raw
        r['HGNC_Match_Status'] = status
        r['Approved_GeneSymbol'] = approved_symbol
        r['HGNC_ID'] = hgnc_id
        out_rows.append(r)

    with out_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader(); w.writerows(out_rows)

    with map_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=extra, delimiter='\t')
        w.writeheader(); w.writerows(map_rows)

    counts = Counter(r['HGNC_Match_Status'] for r in map_rows)
    current_ids = {r['HGNC_ID'] for r in map_rows if r['HGNC_ID']}
    print('ODDB HGNC normalization complete.')
    print(f'  ODDB rows: {len(out_rows)}')
    print(f'  Unique original ODDB gene symbols: {len(map_rows)}')
    print(f'  Unique current HGNC IDs: {len(current_ids)}')
    print('  Match status:', dict(counts))
    print(f'  Annotated ODDB: {out_path}')
    print(f'  Unique-symbol mapping: {map_path}')


if __name__ == '__main__':
    main()
