#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re
from urllib.parse import quote
import pymysql

ANATOMY = {
    "refractive errors":"ANAT-01","retinal diseases":"ANAT-02","others":"ANAT-03",
    "lens diseases":"ANAT-04","ocular hypertension":"ANAT-05",
    "ocular motility disorders":"ANAT-06","uveal diseases":"ANAT-07",
    "corneal diseases":"ANAT-08","conjunctival diseases":"ANAT-09",
    "orbital diseases":"ANAT-10","eye neoplasms":"ANAT-11",
    "lacrimal apparatus diseases":"ANAT-12"
}
INH = [
    ("INH-01",[r"\bautosomal dominant\b",r"\bad\b"]),
    ("INH-02",[r"\bautosomal recessive\b",r"\bar\b"]),
    ("INH-03",[r"\bisolated cases?\b",r"\bisolated\b",r"\bsporadic\b"]),
    ("INH-04",[r"\bmitochondrial\b"]),
    ("INH-06",[r"\bx[- ]linked dominant\b"]),
    ("INH-07",[r"\bx[- ]linked recessive\b",r"\bx[- ]linked\b"]),
]
GENE = [
    ("GENE-03",[r"\blncrna\b",r"long non[- ]coding rna"]),
    ("GENE-04",[r"\bmirna\b",r"\bmicro[- ]?rna\b"]),
    ("GENE-05",[r"\bmt[_ -]?trna\b",r"mitochondrial.*trna"]),
    ("GENE-01",[r"\bpseudogene\b"]),
    ("GENE-07",[r"\bprotein[- _]?coding\b"]),
    ("GENE-08",[r"\brna gene\b",r"\bribosomal rna\b",r"\bsnrna\b",r"\bsnorna\b"]),
    ("GENE-06",[r"^other$"]),
]
CONSEQ = {
    "missense variant":"VARC-01","inframe deletion":"VARC-02",
    "frameshift variant":"VARC-03","intron variant":"VARC-04",
    "regulatory region variant":"VARC-05","intergenic variant":"VARC-06",
    "splice region variant":"VARC-07","splice donor variant":"VARC-08",
    "non coding transcript exon variant":"VARC-09","3-prime utr variant":"VARC-10",
    "5-prime utr variant":"VARC-11","stop gained":"VARC-12",
    "synonymous variant":"VARC-13","tf binding site variant":"VARC-14",
    "splice acceptor variant":"VARC-15","downstream gene variant":"VARC-16",
    "stop lost":"VARC-17","upstream gene variant":"VARC-18",
    "inframe insertion":"VARC-19","protein altering variant":"VARC-20",
    "multiple reported":"VARC-21"
}

def norm(x):
    x=str(x or "").strip().replace("_"," ").replace("’","'")
    return re.sub(r"\s+"," ",x).lower()

def stable(prefix,*parts):
    s="|".join(str(x or "") for x in parts)
    return prefix+"-"+hashlib.sha1(s.encode()).hexdigest()[:16].upper()

def json_values(raw):
    try: obj=json.loads(raw or "{}")
    except Exception: return []
    out=[]
    def walk(x,path=""):
        if isinstance(x,dict):
            for k,v in x.items():
                np=f"{path}.{k}" if path else k
                nk=norm(k)
                if isinstance(v,(str,int,float)) and any(t in nk for t in ("consequence","variant type","gene type","locus type","biotype","url","link")):
                    out.append((np,str(v)))
                walk(v,np)
        elif isinstance(x,list):
            for i,v in enumerate(x): walk(v,f"{path}[{i}]")
    walk(obj)
    return out

def add_link(cur,etype,eid,res,external_id,url,order=100,source="generated_from_canonical_identifier"):
    if not eid or not url: return 0
    lid=stable("ODDB-LINK",etype,eid,res,url)
    cur.execute("""INSERT IGNORE INTO entity_external_link
      (link_id,entity_type,entity_id,resource_name,external_id,url,display_label,display_order,source)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
      (lid,etype,eid,res,external_id,url,res,order,source))
    return cur.rowcount

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--host",default=os.getenv("MYSQL_HOST","127.0.0.1"))
    ap.add_argument("--port",type=int,default=int(os.getenv("MYSQL_PORT","3306")))
    ap.add_argument("--user",default=os.getenv("MYSQL_USER","root"))
    ap.add_argument("--password",default=os.getenv("MYSQL_PASSWORD",""))
    ap.add_argument("--database",default=os.getenv("MYSQL_DATABASE","oddb_v1"))
    args=ap.parse_args()
    conn=pymysql.connect(host=args.host,port=args.port,user=args.user,password=args.password,
                         database=args.database,charset="utf8mb4",autocommit=False,
                         cursorclass=pymysql.cursors.DictCursor)
    stats={k:0 for k in ["anatomy_memberships","inheritance_memberships","gene_type_memberships","variant_consequences","external_links"]}
    try:
        with conn.cursor() as cur:
            for table in ("disease_category_membership","gene_category_membership","variant_consequence","entity_external_link"):
                cur.execute(f"DELETE FROM {table}")
            conn.commit()

            cur.execute("""SELECT disease_id,localization,inheritance,mondo_id,omim_id,orphanet_id,source_record_json FROM disease""")
            diseases=cur.fetchall()
            cur.execute("""SELECT disease_id,GROUP_CONCAT(DISTINCT inheritance SEPARATOR ' | ') inh
                           FROM disease_gene_association
                           WHERE inheritance IS NOT NULL AND inheritance<>''
                           GROUP BY disease_id""")
            dga_inh={r["disease_id"]:r["inh"] for r in cur.fetchall()}
            for d in diseases:
                did=d["disease_id"]; loc=norm(d["localization"])
                if loc in ANATOMY:
                    cur.execute("""INSERT IGNORE INTO disease_category_membership
                      (disease_id,category_id,membership_basis,source,curation_status)
                      VALUES(%s,%s,%s,'ODDB disease.localization','mapped')""",
                      (did,ANATOMY[loc],d["localization"]))
                    stats["anatomy_memberships"]+=cur.rowcount
                txt=" | ".join(x for x in [d.get("inheritance",""),dga_inh.get(did,"")] if x)
                nt=norm(txt); matched=set()
                for cid,pats in INH:
                    if any(re.search(p,nt,re.I) for p in pats): matched.add(cid)
                if not matched and nt: matched.add("INH-05")
                for cid in matched:
                    cur.execute("""INSERT IGNORE INTO disease_category_membership
                      (disease_id,category_id,membership_basis,source,curation_status)
                      VALUES(%s,%s,%s,'ODDB disease/DGA inheritance','mapped')""",(did,cid,txt))
                    stats["inheritance_memberships"]+=cur.rowcount
                if d.get("mondo_id"):
                    stats["external_links"]+=add_link(cur,"disease",did,"MONDO",d["mondo_id"],
                        "https://monarchinitiative.org/disease/"+quote(d["mondo_id"],safe=":"))
                if d.get("omim_id"):
                    om=re.sub(r"\D","",str(d["omim_id"]))
                    if om: stats["external_links"]+=add_link(cur,"disease",did,"OMIM",d["omim_id"],"https://omim.org/entry/"+om)

            cur.execute("""SELECT hgnc_id,gene_symbol,gene_entity_type,ensembl_gene_id,ncbi_gene_id,source_record_json FROM gene""")
            for g in cur.fetchall():
                vals=[g.get("gene_entity_type","")]
                jv=json_values(g.get("source_record_json"))
                for k,v in jv:
                    if any(t in norm(k) for t in ("gene type","locus type","biotype")): vals.append(v)
                txt=" | ".join(x for x in vals if x); nt=norm(txt); assigned=None
                for cid,pats in GENE:
                    if any(re.search(p,nt,re.I) for p in pats): assigned=cid; break
                if assigned:
                    cur.execute("""INSERT IGNORE INTO gene_category_membership
                      (hgnc_id,gene_category_id,membership_basis,source)
                      VALUES(%s,%s,%s,'ODDB/HGNC-derived field')""",(g["hgnc_id"],assigned,txt))
                    stats["gene_type_memberships"]+=cur.rowcount
                hid=g["hgnc_id"]; sym=g.get("gene_symbol") or ""
                stats["external_links"]+=add_link(cur,"gene",hid,"HGNC",hid,
                    "https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/"+quote(hid,safe=":"))
                if g.get("ensembl_gene_id"):
                    e=g["ensembl_gene_id"]; stats["external_links"]+=add_link(cur,"gene",hid,"Ensembl",e,
                        "https://www.ensembl.org/Homo_sapiens/Gene/Summary?g="+quote(e))
                if g.get("ncbi_gene_id"):
                    n=str(g["ncbi_gene_id"]); stats["external_links"]+=add_link(cur,"gene",hid,"NCBI Gene",n,
                        "https://www.ncbi.nlm.nih.gov/gene/"+quote(n))
                if sym:
                    stats["external_links"]+=add_link(cur,"gene",hid,"GeneCards",sym,
                        "https://www.genecards.org/cgi-bin/carddisp.pl?gene="+quote(sym))
                for k,v in jv:
                    if re.match(r"^https?://",v.strip(),re.I):
                        stats["external_links"]+=add_link(cur,"gene",hid,k.split(".")[-1],None,v.strip(),200,"legacy_source_record_json")

            cur.execute("""SELECT variant_id,clinvar_variation_id,variant_type,rs_id,source_record_json FROM variant""")
            processed=0
            for v in cur:
                vid=v["variant_id"]; jv=json_values(v.get("source_record_json"))
                vals=[v.get("variant_type","")]+[x for k,x in jv if "consequence" in norm(k) or "variant type" in norm(k)]
                mapped=set()
                for raw in vals:
                    for part in re.split(r"[|,;/]+",str(raw or "")):
                        n=norm(part).replace("3 prime","3-prime").replace("5 prime","5-prime")
                        if n in CONSEQ: mapped.add((CONSEQ[n],part.strip()))
                for cid,raw in mapped:
                    vcid=stable("ODDB-VC",vid,cid,"")
                    cur.execute("""INSERT IGNORE INTO variant_consequence
                      (variant_consequence_id,variant_id,consequence_id,hgnc_id,source,source_value)
                      VALUES(%s,%s,%s,NULL,'exact controlled-term match',%s)""",(vcid,vid,cid,raw))
                    stats["variant_consequences"]+=cur.rowcount
                if v.get("clinvar_variation_id"):
                    c=str(v["clinvar_variation_id"]); stats["external_links"]+=add_link(cur,"variant",vid,"ClinVar",c,
                        "https://www.ncbi.nlm.nih.gov/clinvar/variation/"+quote(c)+"/")
                if v.get("rs_id"):
                    rs=str(v["rs_id"]).strip()
                    if rs: stats["external_links"]+=add_link(cur,"variant",vid,"dbSNP",rs,"https://www.ncbi.nlm.nih.gov/snp/"+quote(rs))
                for k,url in jv:
                    if re.match(r"^https?://",url.strip(),re.I):
                        stats["external_links"]+=add_link(cur,"variant",vid,k.split(".")[-1],None,url.strip(),200,"legacy_source_record_json")
                processed+=1
                if processed%50000==0:
                    conn.commit(); print(f"Variants processed: {processed:,}")

            cur.execute("SELECT drug_id,chembl_id,drugbank_id,pubchem_cid FROM drug")
            for d in cur.fetchall():
                did=d["drug_id"]
                if d.get("chembl_id"):
                    x=d["chembl_id"]; stats["external_links"]+=add_link(cur,"drug",did,"ChEMBL",x,"https://www.ebi.ac.uk/chembl/explore/compound/"+quote(x))
                if d.get("drugbank_id"):
                    x=d["drugbank_id"]; stats["external_links"]+=add_link(cur,"drug",did,"DrugBank",x,"https://go.drugbank.com/drugs/"+quote(x))
                if d.get("pubchem_cid"):
                    x=str(d["pubchem_cid"]); stats["external_links"]+=add_link(cur,"drug",did,"PubChem",x,"https://pubchem.ncbi.nlm.nih.gov/compound/"+quote(x))
            cur.execute("SELECT clinical_trial_id,nct_id FROM clinical_trial")
            for t in cur.fetchall():
                if t.get("nct_id"):
                    n=t["nct_id"]; stats["external_links"]+=add_link(cur,"trial",t["clinical_trial_id"],"ClinicalTrials.gov",n,"https://clinicaltrials.gov/study/"+quote(n))
            conn.commit()

            print("\nODDB v1 WEB TAXONOMY BACKFILL")
            for k,v in stats.items(): print(f"{k}: {v:,}")
            print("\nDisease category counts:")
            cur.execute("""SELECT c.category_system,c.category_name,COUNT(DISTINCT m.disease_id) n
              FROM disease_category c LEFT JOIN disease_category_membership m ON m.category_id=c.category_id
              GROUP BY c.category_id,c.category_system,c.category_name,c.display_order
              ORDER BY c.category_system,c.display_order""")
            for r in cur.fetchall(): print(f"{r['category_system']:12s} {r['category_name']:32s} {r['n']:4d}")
            print("\nGene category counts:")
            cur.execute("""SELECT c.gene_category_id,c.category_name,c.entity_scope,COUNT(DISTINCT m.hgnc_id) n
              FROM gene_category c LEFT JOIN gene_category_membership m ON m.gene_category_id=c.gene_category_id
              GROUP BY c.gene_category_id,c.category_name,c.entity_scope,c.display_order ORDER BY c.display_order""")
            rows=cur.fetchall()
            for r in rows:
                n=r["n"]
                if r["entity_scope"]=="locus":
                    cur.execute("SELECT COUNT(*) n FROM locus"); n=cur.fetchone()["n"]
                print(f"{r['category_name']:28s} {n:5d}")
            print("\nVariant consequence counts:")
            cur.execute("""SELECT c.consequence_term,COUNT(DISTINCT v.variant_id) n
              FROM variant_consequence_category c LEFT JOIN variant_consequence v ON v.consequence_id=c.consequence_id
              GROUP BY c.consequence_id,c.consequence_term,c.display_order ORDER BY c.display_order""")
            for r in cur.fetchall(): print(f"{r['consequence_term']:38s} {r['n']:7d}")
    finally:
        conn.close()

if __name__=="__main__":
    main()
