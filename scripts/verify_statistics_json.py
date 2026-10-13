#!/usr/bin/env python3
"""Validate ODDB v1 enhanced statistics JSON before publication/deployment."""
import argparse
import hashlib
import json
from pathlib import Path

RANKINGS = {'diseases_genes','diseases_variants','genes_diseases','diseases_trial_drugs','drugs_trial_diseases'}
CHROM = {'genes_by_chromosome_category','variants_by_chromosome_category',
         'genes_by_category_chromosome','variants_by_category_chromosome'}
CLINICAL = {'trial_phases','disease_categories','evidence_classes','diseases_for_network'}


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def verify(root: Path, diseases=162, trials=1164):
    index = json.loads((root/'index.json').read_text())
    check(index['database_release'].startswith('ODDB v1 '), 'Unexpected release identity')
    expected_counts={'disease':diseases,'gene':1249,'variant':707315,'drug':805,
                     'disease_gene_association':1631,'drug_target_association':1009,
                     'disease_drug_association':344,'clinical_trial':trials,
                     'clinical_report':1291}
    for table,count in expected_counts.items():
        check(index['source_table_counts'][table]==count,
              f'Unexpected canonical count {table}: {index["source_table_counts"][table]} != {count}')
    for item in index['files']:
        b=(root/item['file']).read_bytes()
        check(hashlib.sha256(b).hexdigest()==item['sha256'], f"Hash mismatch {item['file']}")
        check(len(b)==item['bytes'], f"File size mismatch {item['file']}")
    data={f:json.loads((root/f).read_text()) for f in ['rankings.json','chromosomes.json','clinical.json']}
    check(RANKINGS==set(data['rankings.json']), 'Missing ranking dataset')
    check(CHROM==set(data['chromosomes.json']), 'Missing chromosome dataset')
    check(CLINICAL==set(data['clinical.json']), 'Missing clinical dataset')
    for kind in ('rankings.json','chromosomes.json'):
        for label, rows in data[kind].items():
            seen=set()
            previous=float('inf')
            for r in rows:
                check(isinstance(r['id'],str) and r['id'], f'{label}: invalid id')
                check(r['id'] not in seen, f'{label}: duplicate id')
                seen.add(r['id'])
                check(isinstance(r['name'],str) and r['name'], f'{label}: invalid name')
                check(isinstance(r['total'],int) and r['total']>=0, f'{label}: invalid total')
                check(r['total']==sum(r['parts'].values()),f'{label}: stack total mismatch for {r["id"]}')
                check(all(isinstance(n,int) and n>=0 for n in r['parts'].values()),f'{label}: noninteger part')
                check(r['total']<=previous, f'{label}: not sorted descending')
                previous=r['total']
            print(f'PASS {label}: {len(rows)} ranked entities')
    annotation=index.get('gene_chromosome_annotation')
    check(isinstance(annotation,dict), 'Missing gene chromosome provenance')
    gene_total=index['source_table_counts']['gene']
    check(annotation['total_genes']==gene_total,'Gene chromosome annotation total mismatch')
    check(annotation['annotated']+annotation['unmapped']==gene_total,
          'Gene chromosome mapped/unmapped counts do not reconcile')
    check(annotation['annotated']>0,'All genes Unmapped: external HGNC overlay missing')
    check(annotation.get('source_sha256') or annotation['canonical_annotated']>0,
          'No source checksum or canonical gene chromosome annotations')
    chrom_rows=data['chromosomes.json']['genes_by_chromosome_category']
    check(any(r['name']!='Unmapped' for r in chrom_rows),
          'Gene chromosome category chart still has no mapped chromosomes')
    for name in ('diseases_trial_drugs','drugs_trial_diseases'):
        check(sum(r['total'] for r in data['rankings.json'][name]) == index['trial_shared_disease_drug_pairs'],
              f'{name}: trial stacks are not globally unique disease-drug pairs')
    print('PASS HGNC annotation coverage: %d/%d genes (%d Unmapped)' %
          (annotation['annotated'],gene_total,annotation['unmapped']))
    print('PASS trial shared-pair uniqueness: %d distinct disease-drug pairs' %
          index['trial_shared_disease_drug_pairs'])
    c=data['clinical.json']
    check(len(c['disease_categories'])==12, 'Expected 12 anatomy categories')
    check(len(c['diseases_for_network'])==diseases, f'Expected {diseases} disease choices')
    check(sum(r['trials'] for r in c['trial_phases'])==trials,f'Expected {trials} unique trials')
    check({r['name'] for r in c['evidence_classes']}=={'Direct only','Direct + target overlap','Target overlap only'}, 'Unexpected evidence classes')
    print(f'PASS clinical: {trials} trials, {diseases} disease choices, 12 anatomy categories')
    print('PASS snapshot integrity and scientific consistency checks')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--expected-diseases',type=int,default=162)
    parser.add_argument('--expected-trials',type=int,default=1164)
    args=parser.parse_args()
    verify(args.directory,args.expected_diseases,args.expected_trials)
