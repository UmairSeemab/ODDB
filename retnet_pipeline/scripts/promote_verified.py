#!/usr/bin/env python3
import csv, argparse
from datetime import date
PUBLIC_FIELDS=['ODDB_DiseaseID','ODDB_Disease','GeneSymbol','HGNC_ID','Inheritance','Association_Type','Primary_Reference_PMID','ClinGen_Status','ClinVar_Support','Evidence_Status','Curated_Date']
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--candidates',required=True); ap.add_argument('--out',required=True); args=ap.parse_args()
    rows=[]
    with open(args.candidates,encoding='utf-8') as f:
        rd=csv.DictReader(f,delimiter='\t')
        for r in rd:
            if r.get('Independent_Verification_Status')=='Verified' and r.get('Curator_Decision')=='Include' and r.get('Approved_GeneSymbol'):
                rows.append({
                    'ODDB_DiseaseID':r.get('ODDB_DiseaseID',''),'ODDB_Disease':r.get('ODDB_Disease',''),
                    'GeneSymbol':r.get('Approved_GeneSymbol',''),'HGNC_ID':r.get('HGNC_ID',''),
                    'Inheritance':r.get('Inheritance',''),'Association_Type':r.get('Association_Type',''),
                    'Primary_Reference_PMID':r.get('Primary_Reference_PMID',''),'ClinGen_Status':r.get('ClinGen_Status',''),
                    'ClinVar_Support':r.get('ClinVar_Support',''),'Evidence_Status':'Independently verified','Curated_Date':date.today().isoformat()})
    with open(args.out,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=PUBLIC_FIELDS,delimiter='\t'); w.writeheader(); w.writerows(rows)
    print(f'Promoted {len(rows)} independently verified records.')
if __name__=='__main__': main()
