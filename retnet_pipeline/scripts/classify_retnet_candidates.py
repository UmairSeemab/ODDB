#!/usr/bin/env python3
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

ACCEPTED_DISEASE_MATCHES = {'exact', 'synonym_rule', 'high_confidence'}
SPECIAL_NON_GENE = {'OPSIN-LCR', 'KSS'}
SPECIAL_MANUAL = {'LHON', 'RP17'}


def main():
    ap = argparse.ArgumentParser(description='Classify HGNC-normalized RetNet candidates against HGNC-normalized ODDB records.')
    ap.add_argument('--candidates', required=True)
    ap.add_argument('--oddb-hgnc', required=True)
    ap.add_argument('--output', default='data/processed/oddb_retnet_candidates_classified_hgnc.tsv')
    args = ap.parse_args()

    with open(args.candidates, encoding='utf-8-sig', errors='replace') as f:
        cand = list(csv.DictReader(f, delimiter='\t'))
    with open(args.oddb_hgnc, encoding='utf-8-sig', errors='replace') as f:
        oddb = list(csv.DictReader(f, delimiter='\t'))

    oddb_hgnc_ids = {(r.get('HGNC_ID') or '').strip() for r in oddb if (r.get('HGNC_ID') or '').strip()}
    oddb_symbols = {(r.get('Approved_GeneSymbol') or r.get('GeneSymbol') or '').strip().upper() for r in oddb if (r.get('Approved_GeneSymbol') or r.get('GeneSymbol') or '').strip()}

    # Association keys by DiseaseID + HGNC_ID. Fall back to current symbol only when HGNC is unavailable.
    oddb_assoc_hgnc = set()
    oddb_assoc_symbol = set()
    for r in oddb:
        did = (r.get('DiseaseID') or '').strip()
        hid = (r.get('HGNC_ID') or '').strip()
        sym = (r.get('Approved_GeneSymbol') or r.get('GeneSymbol') or '').strip().upper()
        if did and hid:
            oddb_assoc_hgnc.add((did, hid))
        if did and sym:
            oddb_assoc_symbol.add((did, sym))

    counts = Counter()
    genes_by_class = defaultdict(set)
    out = []

    for row in cand:
        x = dict(row)
        original = (x.get('RetNet_Symbol') or '').strip().upper()
        approved = (x.get('Approved_GeneSymbol') or '').strip().upper()
        hid = (x.get('HGNC_ID') or '').strip()
        hstatus = (x.get('HGNC_Match_Status') or '').strip().lower()
        dstatus = (x.get('Disease_Match_Status') or '').strip().lower()
        did = (x.get('ODDB_DiseaseID') or '').strip()

        if original in SPECIAL_NON_GENE:
            cls = 'E_non_gene_entity'
        elif original in SPECIAL_MANUAL:
            cls = 'D_manual_review'
        elif hstatus in {'not_found', 'ambiguous_alias', 'ambiguous_previous_symbol', 'blank'} or not hid:
            cls = 'D_gene_identity_review'
        elif dstatus not in ACCEPTED_DISEASE_MATCHES:
            cls = 'D_disease_mapping_review'
        else:
            existing_assoc = (did, hid) in oddb_assoc_hgnc if did and hid else ((did, approved) in oddb_assoc_symbol if did and approved else False)
            if existing_assoc:
                cls = 'A_existing_association'
            elif hid in oddb_hgnc_ids or approved in oddb_symbols:
                cls = 'B_new_association_existing_gene'
            else:
                cls = 'C_new_gene_for_ODDB'

        x['Integration_Class_HGNC'] = cls
        counts[cls] += 1
        if hid:
            genes_by_class[cls].add(hid)
        out.append(x)

    fields = list(out[0].keys()) if out else []
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader(); w.writerows(out)

    print('\nROW COUNTS')
    for k, v in counts.most_common():
        print(f'{k}\t{v}')

    print('\nUNIQUE HGNC GENES BY CLASS')
    for k, ids in sorted(genes_by_class.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f'{k}\t{len(ids)}')

    print('\nPOTENTIAL NEW GENES FOR ODDB')
    seen = set()
    for r in out:
        if r['Integration_Class_HGNC'] != 'C_new_gene_for_ODDB':
            continue
        key = ((r.get('HGNC_ID') or '').strip(), (r.get('ODDB_DiseaseID') or '').strip(), (r.get('Inheritance') or '').strip())
        if key in seen:
            continue
        seen.add(key)
        print('\t'.join([
            (r.get('RetNet_Symbol') or '').strip(),
            (r.get('Approved_GeneSymbol') or '').strip(),
            (r.get('HGNC_ID') or '').strip(),
            (r.get('ODDB_Disease') or '').strip(),
            (r.get('Normalized_Disease') or '').strip(),
            (r.get('Inheritance') or '').strip(),
            (r.get('Association_Type') or '').strip(),
        ]))

    print(f'\nWritten: {out_path}')
    print('Accepted disease-match statuses:', ', '.join(sorted(ACCEPTED_DISEASE_MATCHES)))


if __name__ == '__main__':
    main()
