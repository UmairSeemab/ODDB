#!/usr/bin/env python3
from pathlib import Path
import argparse, csv, re, unicodedata, difflib
from collections import defaultdict, Counter
from datetime import date

ROOT=Path(__file__).resolve().parents[1]
STOP={'disease','diseases','syndrome','syndromic','systemic','with','or','and','of','the','other','ocular','retinal','retinopathy'}
INH=[('autosomal dominant','Autosomal dominant'),('autosomal recessive','Autosomal recessive'),('x-linked','X-linked'),('mitochondrial','Mitochondrial')]
SYNONYM_RULES={
    ('Chorioretinal atrophy or degeneration','Mendelian'):'ODDB-34',
    ('Cone or cone-rod dystrophy','Mendelian'):'ODDB-47',
    ('Congenital stationary night blindness','Mendelian'):'ODDB-131',
    ('Macular degeneration','Mendelian'):'ODDB-107',
}

def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=re.sub(r'\([^)]*\)',' ',s); s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())

def core_tokens(s): return {t for t in norm(s).split() if t not in STOP and len(t)>2}
def jaccard(a,b): return len(a&b)/len(a|b) if a and b else 0.0

def parse_inheritance(cat):
    low=cat.lower()
    for phrase,canon in INH:
        if low.endswith(', '+phrase): return cat[:-(len(phrase)+2)].strip(),canon
    return cat.strip(),''

def latest_rendered_tables():
    files=sorted((ROOT/'data/raw').glob('retnet_rendered_table_*_*.tsv'))
    if not files: raise SystemExit('No rendered RetNet tables found. Run fetch_retnet.py first.')
    # file names end in ISO date, e.g. ..._2026-09-28.tsv
    dates=sorted({p.stem.rsplit('_',1)[-1] for p in files})
    latest=dates[-1]
    return latest, sorted(p for p in files if p.stem.endswith(latest))

def _find_header(rows):
    """Return (row_index, disease_col_index, entity_col_index, kind).

    RetNet's React table markup has changed over time, so the first parsed
    <tr> is not assumed to be the header. We scan all rows for the semantic
    column labels instead.
    """
    for i, row in enumerate(rows):
        cleaned=[(c or '').strip() for c in row]
        low=[c.lower() for c in cleaned]
        joined=' | '.join(low)
        disease_idx=next((j for j,c in enumerate(low) if 'disease category' in c), None)
        if disease_idx is None:
            continue

        entity_idx=None
        kind=None
        for j,c in enumerate(low):
            if 'mapped and identified genes' in c:
                entity_idx=j; kind='Mendelian'; break
            if 'mapped loci' in c:
                entity_idx=j; kind='Unresolved locus'; break
            if 'mapped and named loci' in c:
                entity_idx=j; kind='Complex'; break

        # A RetNet title row can contain both phrases in the same cell, e.g.
        # "Table B: Remaining Mapped Loci by Disease Category". That is not
        # the real two-column header. Only accept semantic labels that occur
        # in distinct columns.
        if entity_idx is not None and entity_idx != disease_idx:
            return i, disease_idx, entity_idx, kind
    return None


def _split_entities(text):
    """Split a RetNet symbol/locus cell without altering valid hyphenated symbols."""
    text=(text or '').replace('\xa0',' ').strip()
    # RetNet currently separates symbols with whitespace. Accept comma/semicolon
    # separators too, while retaining symbols such as OPSIN-LCR and MT-ATP6.
    toks=[x.strip() for x in re.split(r'[\s,;]+', text) if x.strip()]
    # Remove harmless punctuation occasionally introduced by rendered text.
    return [x.strip('[](){}') for x in toks if x.strip('[](){}')]


def _expected_totals_from_text():
    """Read RetNet's rendered page totals when available."""
    txts=sorted((ROOT/'data/raw').glob('retnet_rendered_text_*.txt'))
    if not txts:
        return None, None
    text=txts[-1].read_text(encoding='utf-8', errors='replace')
    m1=re.search(r'Total number of genes to date:\s*(\d+)', text, re.I)
    m2=re.search(r'Total number of genes\s*\+\s*remaining unidentified loci:\s*(\d+)', text, re.I)
    return (int(m1.group(1)) if m1 else None,
            int(m2.group(1)) if m2 else None)


def parse_retnet(files):
    groups={'Mendelian':[],'Complex':[],'Unresolved locus':[]}
    parsed_tables=[]

    for p in files:
        with p.open(encoding='utf-8') as f:
            rows=list(csv.reader(f, delimiter='\t'))
        if not rows:
            continue

        found=_find_header(rows)
        if not found:
            # Keep going because fetch_retnet.py may capture unrelated tables.
            continue
        hidx,disease_idx,entity_idx,kind=found
        parsed_tables.append((p.name, kind, hidx, disease_idx, entity_idx))

        for r in rows[hidx+1:]:
            # Pad short rows rather than silently shifting columns.
            needed=max(disease_idx, entity_idx)
            if len(r) <= needed:
                r=r+['']*(needed+1-len(r))
            cat=r[disease_idx].strip()
            entities=r[entity_idx].strip()
            if not cat or not entities:
                continue

            # Ignore repeated headers that can occur in responsive table markup.
            if 'disease category' in cat.lower():
                continue

            base,inh=parse_inheritance(cat)
            for ent in _split_entities(entities):
                groups[kind].append({
                    'retnet_category':cat,
                    'disease_base':base,
                    'inheritance':inh,
                    'RetNet_Symbol':ent,
                    'association_type':kind
                })

    # Remove exact duplicate rows while preserving RetNet ordering.
    for kind in groups:
        seen=set(); dedup=[]
        for r in groups[kind]:
            key=(r['retnet_category'],r['RetNet_Symbol'])
            if key in seen:
                continue
            seen.add(key); dedup.append(r)
        groups[kind]=dedup

    n_genes=len({r['RetNet_Symbol'] for r in groups['Mendelian']})
    n_loci=len({r['RetNet_Symbol'] for r in groups['Unresolved locus']})
    expected_genes, expected_total=_expected_totals_from_text()
    expected_loci=(expected_total-expected_genes) if expected_genes is not None and expected_total is not None else None

    print('RetNet table parser:')
    for name,kind,hidx,didx,eidx in parsed_tables:
        print(f'  {name}: {kind} (header row {hidx+1}, disease col {didx+1}, entity col {eidx+1})')
    print(f'  parsed unique Table-A symbols: {n_genes}')
    print(f'  parsed unique unresolved loci: {n_loci}')
    if expected_genes is not None:
        print(f'  RetNet page reports genes: {expected_genes}')
    if expected_loci is not None:
        print(f'  RetNet page implies unresolved loci: {expected_loci}')

    # Strong QC. Prefer exact comparison with RetNet's own visible counters.
    if expected_genes is not None and n_genes != expected_genes:
        raise SystemExit(
            f'QC failed: RetNet page reports {expected_genes} genes but parser found {n_genes}. '
            'No harmonized output written.'
        )
    if expected_loci is not None and n_loci != expected_loci:
        raise SystemExit(
            f'QC failed: RetNet page implies {expected_loci} unresolved loci but parser found {n_loci}. '
            'No harmonized output written.'
        )
    if n_genes < 300 or n_loci < 10:
        raise SystemExit(
            f'QC failed: only {n_genes} Table-A symbols and {n_loci} loci parsed. '
            'No harmonized output written.'
        )
    return groups

def disease_score(ret_base, oddb_name, ret_genes, oddb_genes):
    nr,no=norm(ret_base),norm(oddb_name)
    seq=difflib.SequenceMatcher(None,nr,no).ratio(); tok=jaccard(core_tokens(ret_base),core_tokens(oddb_name))
    gov=len(ret_genes & oddb_genes)/max(1,len(ret_genes)); contain=1.0 if nr and (nr in no or no in nr) else 0.0
    return 0.45*seq+0.25*tok+0.20*gov+0.10*contain,seq,tok,gov

def write_tsv(path, rows, fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t'); w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--oddb',required=True,help='ODDB Gene_Disease_Drug_merged.tsv'); args=ap.parse_args()
    stamp,files=latest_rendered_tables(); groups=parse_retnet(files)
    A=groups['Mendelian']; C=groups['Complex']; B=groups['Unresolved locus']
    processed=ROOT/'data/processed'; mapping_dir=ROOT/'data/mapping'; reports=ROOT/'reports'
    ret_fields=['retnet_category','disease_base','inheritance','RetNet_Symbol','association_type']
    write_tsv(processed/f'retnet_associations_{stamp}.tsv',A+C,ret_fields)
    write_tsv(processed/f'retnet_loci_{stamp}.tsv',B,ret_fields)

    oddb_disease_meta={}; oddb_disease_genes=defaultdict(set); oddb_assoc=set()
    with open(args.oddb,encoding='utf-8-sig',errors='replace') as f:
        rd=csv.DictReader(f,delimiter='\t')
        for r in rd:
            did=(r.get('DiseaseID') or '').strip(); dis=(r.get('Ocular.disease') or '').strip(); gene=(r.get('GeneSymbol') or '').strip(); cat=(r.get('Disease.category') or '').strip()
            if did and dis: oddb_disease_meta[did]=(dis,cat)
            if did and gene: oddb_disease_genes[did].add(gene); oddb_assoc.add((did,gene))

    ret_disease_genes=defaultdict(set)
    for r in A+C: ret_disease_genes[(r['disease_base'],r['association_type'])].add(r['RetNet_Symbol'])
    mappings=[]
    for (ret_base,atype),rgenes in sorted(ret_disease_genes.items()):
        cand=[]
        for did,(oname,ocat) in oddb_disease_meta.items():
            sc,seq,tok,gov=disease_score(ret_base,oname,rgenes,oddb_disease_genes.get(did,set()))
            cand.append((sc,seq,tok,gov,did,oname,ocat))
        cand.sort(reverse=True); top=cand[:3]; best=top[0]
        forced=SYNONYM_RULES.get((ret_base,atype))
        if forced and forced in oddb_disease_meta:
            oname,ocat=oddb_disease_meta[forced]; sc,seq,tok,gov=disease_score(ret_base,oname,rgenes,oddb_disease_genes.get(forced,set()))
            best=(sc,seq,tok,gov,forced,oname,ocat); status='synonym_rule'
        elif norm(ret_base)==norm(best[5]): status='exact'
        elif best[0]>=0.72: status='high_confidence'
        elif best[0]>=0.52: status='review'
        else: status='unmatched'
        mappings.append({'retnet_disease':ret_base,'association_type':atype,'suggested_oddb_id':best[4] if status!='unmatched' else '',
            'suggested_oddb_disease':best[5] if status!='unmatched' else '','oddb_category':best[6] if status!='unmatched' else '',
            'match_status':status,'match_score':round(best[0],4),'name_similarity':round(best[1],4),'token_similarity':round(best[2],4),
            'gene_overlap_fraction':round(best[3],4),'candidate_2':f'{top[1][4]} | {top[1][5]} | {top[1][0]:.4f}',
            'candidate_3':f'{top[2][4]} | {top[2][5]} | {top[2][0]:.4f}','manual_decision':'','curator_notes':''})
    write_tsv(mapping_dir/f'retnet_oddb_disease_mapping_{stamp}.tsv',mappings,list(mappings[0].keys()))
    ml={(r['retnet_disease'],r['association_type']):r for r in mappings}
    candidates=[]
    for r in A+C:
        m=ml[(r['disease_base'],r['association_type'])]; did=m['suggested_oddb_id']; oname=m['suggested_oddb_disease']
        existing=bool(did and (did,r['RetNet_Symbol']) in oddb_assoc)
        st='already_in_oddb' if existing else ('candidate_new_association' if did else 'candidate_unmapped_disease')
        candidates.append({'ODDB_DiseaseID':did,'ODDB_Disease':oname,'RetNet_Symbol':r['RetNet_Symbol'],'HGNC_Match_Status':'','Approved_GeneSymbol':'','HGNC_ID':'',
            'RetNet_Disease_Category':r['retnet_category'],'Normalized_Disease':r['disease_base'],'Inheritance':r['inheritance'],'Association_Type':r['association_type'],
            'ODDB_Overlap':'Yes' if existing else 'No','Candidate_Status':st,'Disease_Match_Status':m['match_status'],'Disease_Match_Score':m['match_score'],
            'Independent_Verification_Status':'Pending','Primary_Reference_PMID':'','ClinGen_Status':'','ClinVar_Support':'','Curator_Decision':'','Curator_Notes':'',
            'Discovery_Source':'RetNet','Discovery_URL':'https://retnet.org/summaries','Retrieved_Date':stamp})
    write_tsv(processed/f'oddb_retnet_candidates_{stamp}.tsv',candidates,list(candidates[0].keys()))
    # Convenience 'latest' copy names for downstream scripts.
    write_tsv(processed/'oddb_retnet_candidates_latest.tsv',candidates,list(candidates[0].keys()))

    oddb_genes=set().union(*oddb_disease_genes.values()) if oddb_disease_genes else set()
    ret_genes={r['RetNet_Symbol'] for r in A}; loci={r['RetNet_Symbol'] for r in B}; stat=Counter(r['Candidate_Status'] for r in candidates)
    summary=[['Metric','Value'],['RetNet Table-A unique symbols',len(ret_genes)],['RetNet unresolved loci',len(loci)],['RetNet Table-A + loci',len(ret_genes)+len(loci)],
        ['Current ODDB unique gene symbols',len(oddb_genes)],['Raw symbols in both',len(oddb_genes&ret_genes)],['Raw RetNet symbols absent from ODDB',len(ret_genes-oddb_genes)],
        ['Mendelian category-symbol associations',len(A)],['Complex category-symbol associations',len(C)],['Unresolved locus-category associations',len(B)],
        ['Candidates already in ODDB',stat['already_in_oddb']],['Candidate new associations',stat['candidate_new_association']],['Candidate unmapped disease',stat['candidate_unmapped_disease']]]
    with (reports/f'summary_{stamp}.tsv').open('w',newline='',encoding='utf-8') as f: csv.writer(f,delimiter='\t').writerows(summary)
    print(f'Completed RetNet harmonization for snapshot {stamp}.')
    print(f'Table-A symbols: {len(ret_genes)}; loci: {len(loci)}; candidate rows: {len(candidates)}')
    print(f'Next: python scripts/normalize_hgnc.py --input {processed / "oddb_retnet_candidates_latest.tsv"}')

if __name__=='__main__': main()
