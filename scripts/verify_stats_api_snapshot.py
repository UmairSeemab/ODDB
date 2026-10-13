#!/usr/bin/env python3
"""Validate pinned immutable JSON Stats API snapshot and response schema."""
from pathlib import Path
import hashlib
import json
import sys

RELEASE='2026-09-30'
MAP_IDS={
    'anatomy_gene','inheritance_gene','anatomy_drug_stage',
    'inheritance_drug_stage','anatomy_variant','inheritance_variant'
}
EXPECTED={
    'diseases':162,'genes':1249,'disease_genes':1631,'variants':707315,
    'disease_variants':106838,'drugs':805,'drug_targets':1009,
    'disease_drugs':344,'trials':1164,'clinical_reports':1291
}

def verify(root):
    base=root/'app/config'
    doc_path=base/f'stats_api_{RELEASE}.json'
    manifest_path=base/f'stats_api_{RELEASE}.manifest.json'
    data=doc_path.read_bytes()
    meta=json.loads(manifest_path.read_text())
    parsed=json.loads(data)
    assert meta['data_release']==RELEASE and parsed['release']['data_release']==RELEASE
    assert meta['sha256']==hashlib.sha256(data).hexdigest(), 'Data checksum mismatch'
    assert meta['size_bytes']==len(data), 'Data size mismatch'
    assert parsed['ok'] is True
    assert all(k in parsed for k in ('release','overview','disease','genetics','therapeutics','clinical','relationship_maps'))
    for k,v in EXPECTED.items():assert parsed['overview'].get(k)==v, f'{k} mismatch'
    assert len(parsed['relationship_maps'])==6
    assert {x['id'] for x in parsed['relationship_maps']}==MAP_IDS
    assert parsed['therapeutics']['direct_disease_drug']==344
    assert parsed['clinical']['trials']==1164
    php=(root/'app/public/api/stats.php').read_text()
    assert php.count('/* ODDB_STATS_API_SNAPSHOT_FASTPATH_V1 */')==1
    assert "require_once __DIR__.'/db.php';" in php
    print(f'PASS ODDB v1 {RELEASE} Stats API snapshot: {len(data)} bytes')
    print(f'PASS sha256={meta["sha256"]}')
    print(f'PASS 10 canonical counts and six relationship maps')
    print('PASS original SQL fallback retained')

if __name__ == '__main__':
    try:verify(Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve())
    except (Exception,AssertionError) as e:
        print(f'FAIL: {e}',file=sys.stderr)
        sys.exit(1)
