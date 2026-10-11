#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import quote

import pymysql


ANATOMY_IDS = {
    "refractive errors": "ANAT-01",
    "retinal diseases": "ANAT-02",
    "others": "ANAT-03",
    "lens diseases": "ANAT-04",
    "ocular hypertension": "ANAT-05",
    "ocular motility disorders": "ANAT-06",
    "uveal diseases": "ANAT-07",
    "corneal diseases": "ANAT-08",
    "conjunctival diseases": "ANAT-09",
    "orbital diseases": "ANAT-10",
    "eye neoplasms": "ANAT-11",
    "lacrimal apparatus diseases": "ANAT-12",
}

# Conservative display synonyms only. These do not invent a category from disease name.
ANATOMY_SYNONYMS = {
    "refractive error": "refractive errors",
    "retinal disease": "retinal diseases",
    "retina diseases": "retinal diseases",
    "lens disease": "lens diseases",
    "ocular hypertension": "ocular hypertension",
    "ocular motility disorder": "ocular motility disorders",
    "uveal disease": "uveal diseases",
    "corneal disease": "corneal diseases",
    "conjunctival disease": "conjunctival diseases",
    "orbital disease": "orbital diseases",
    "eye neoplasm": "eye neoplasms",
    "lacrimal apparatus disease": "lacrimal apparatus diseases",
    "other": "others",
}

GENE_CATEGORY_NAMES = {
    "GENE-01": "Pseudogene",
    "GENE-03": "lncRNA",
    "GENE-04": "miRNA",
    "GENE-05": "mt_tRNA",
    "GENE-06": "Other",
    "GENE-07": "Protein coding",
    "GENE-08": "RNA gene",
}

CONSEQUENCE_TERMS = {
    "missense variant": "VARC-01",
    "inframe deletion": "VARC-02",
    "frameshift variant": "VARC-03",
    "intron variant": "VARC-04",
    "regulatory region variant": "VARC-05",
    "intergenic variant": "VARC-06",
    "splice region variant": "VARC-07",
    "splice donor variant": "VARC-08",
    "non coding transcript exon variant": "VARC-09",
    "3-prime utr variant": "VARC-10",
    "5-prime utr variant": "VARC-11",
    "stop gained": "VARC-12",
    "synonymous variant": "VARC-13",
    "tf binding site variant": "VARC-14",
    "splice acceptor variant": "VARC-15",
    "downstream gene variant": "VARC-16",
    "stop lost": "VARC-17",
    "upstream gene variant": "VARC-18",
    "inframe insertion": "VARC-19",
    "protein altering variant": "VARC-20",
    "multiple reported": "VARC-21",
}


def norm(x):
    x = str(x or "").strip()
    x = x.replace("_", " ").replace("–", "-").replace("—", "-")
    x = re.sub(r"\s+", " ", x)
    return x.lower()


def stable(prefix, *parts):
    payload = "|".join(str(x or "") for x in parts)
    return prefix + "-" + hashlib.sha1(payload.encode()).hexdigest()[:16].upper()


def load_json(raw):
    try:
        x = json.loads(raw or "{}")
        return x if isinstance(x, dict) else {}
    except Exception:
        return {}


def scalar_candidates(obj, key_predicate):
    out = []
    for k, v in obj.items():
        if not key_predicate(norm(k)):
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            out.append((k, str(v).strip()))
    return out


def split_values(value):
    # Keep labels like "X-linked recessive" intact; split only strong delimiters.
    return [x.strip() for x in re.split(r"\s*[|;/]\s*", str(value or "")) if x.strip()]


def map_anatomy_value(value):
    n = norm(value)
    if n in ANATOMY_IDS:
        return ANATOMY_IDS[n]
    if n in ANATOMY_SYNONYMS:
        return ANATOMY_IDS[ANATOMY_SYNONYMS[n]]

    # Sometimes the field has a numeric prefix from the legacy UI.
    n2 = re.sub(r"^\s*\d+\s*[\.\):-]?\s*", "", n)
    if n2 in ANATOMY_IDS:
        return ANATOMY_IDS[n2]
    if n2 in ANATOMY_SYNONYMS:
        return ANATOMY_IDS[ANATOMY_SYNONYMS[n2]]
    return None


def inheritance_categories(value):
    """
    Return only categories explicitly supported by the inheritance text.
    Generic 'X-linked' is left as Other rather than being assumed recessive.
    """
    n = norm(value)
    cats = set()
    if not n:
        return cats

    if re.search(r"\bautosomal dominant\b", n) or re.fullmatch(r"ad", n):
        cats.add("INH-01")
    if re.search(r"\bautosomal recessive\b", n) or re.fullmatch(r"ar", n):
        cats.add("INH-02")
    if any(x in n for x in ("isolated case", "isolated cases", "sporadic")):
        cats.add("INH-03")
    if "mitochondrial" in n or "maternal inheritance" in n:
        cats.add("INH-04")
    if "x-linked dominant" in n or "x linked dominant" in n or re.fullmatch(r"xld", n):
        cats.add("INH-06")
    if "x-linked recessive" in n or "x linked recessive" in n or re.fullmatch(r"xlr", n):
        cats.add("INH-07")

    if not cats:
        # Common source abbreviations / textual values that are explicit.
        if re.fullmatch(r"(xd|xld)", n):
            cats.add("INH-06")
        elif re.fullmatch(r"(xr|xlr)", n):
            cats.add("INH-07")
        elif n in {"x-linked", "x linked", "xl", "other", "unknown", "various",
                   "multifactorial", "complex", "digenic", "oligogenic"}:
            cats.add("INH-05")
    return cats


def map_gene_category(gene_symbol, chromosome, values):
    """
    Map HGNC/legacy gene entity terminology into the user's display vocabulary.
    """
    text = " | ".join(v for v in values if v)
    n = norm(text)
    symbol = str(gene_symbol or "").upper()
    chrom = str(chromosome or "").upper()

    if "pseudogene" in n:
        return "GENE-01"

    # HGNC common locus_type terminology.
    if (
        "gene with protein product" in n
        or "protein coding" in n
        or "protein-coding" in n
        or "protein coding gene" in n
    ):
        return "GENE-07"

    if (
        "long non-coding" in n
        or "long noncoding" in n
        or "lncrna" in n
        or "rna, long non-coding" in n
    ):
        return "GENE-03"

    if "microrna" in n or "micro rna" in n or "rna, micro" in n or "mirna" in n:
        return "GENE-04"

    is_trna = (
        "transfer rna" in n
        or "rna, transfer" in n
        or re.search(r"\btrna\b", n)
    )
    if is_trna and (chrom in {"MT", "M"} or symbol.startswith("MT-T")):
        return "GENE-05"

    if any(token in n for token in (
        "rna, ribosomal", "ribosomal rna", "rna, small nuclear",
        "rna, small nucleolar", "rna, vault", "rna, y", "rna gene",
        "non-coding rna", "noncoding rna", "transfer rna"
    )):
        return "GENE-08"

    # HGNC locus_group values.
    if "protein-coding gene" in n:
        return "GENE-07"
    if "non-coding rna" in n:
        return "GENE-08"

    if n:
        return "GENE-06"
    return None


def add_link(cur, etype, eid, resource, external_id, url, order=100,
             source="generated_from_canonical_identifier"):
    if not eid or not url:
        return 0
    lid = stable("ODDB-LINK", etype, eid, resource, url)
    cur.execute(
        """INSERT IGNORE INTO entity_external_link
        (link_id,entity_type,entity_id,resource_name,external_id,url,
         display_label,display_order,source)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (lid, etype, eid, resource, external_id, url, resource, order, source),
    )
    return cur.rowcount


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    args = ap.parse_args()

    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.database, charset="utf8mb4", autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

    anatomy_unmapped = Counter()
    inheritance_values = Counter()
    gene_source_values = Counter()

    try:
        with conn.cursor() as cur:
            # Rebuild web-derived memberships. Keep variant_consequence untouched:
            # a future ClinVar MC/VEP importer may populate it.
            cur.execute("DELETE FROM disease_category_membership")
            cur.execute("DELETE FROM gene_category_membership")
            cur.execute("DELETE FROM entity_external_link")
            conn.commit()

            # ---------------- Diseases ----------------
            cur.execute("""
                SELECT disease_id,disease_name,localization,inheritance,
                       mondo_id,omim_id,orphanet_id,source_record_json
                FROM disease
            """)
            diseases = cur.fetchall()

            cur.execute("""
                SELECT disease_id,inheritance,source_record_json
                FROM disease_gene_association
            """)
            dga_rows = cur.fetchall()
            dga_by_disease = defaultdict(list)
            for r in dga_rows:
                dga_by_disease[r["disease_id"]].append(r)

            anatomy_n = 0
            inheritance_n = 0
            links_n = 0

            for d in diseases:
                did = d["disease_id"]
                src = load_json(d.get("source_record_json"))

                anatomy_candidates = []
                if d.get("localization"):
                    anatomy_candidates.append(("normalized.localization", d["localization"]))

                anatomy_candidates += scalar_candidates(
                    src,
                    lambda k: (
                        "localization" in k
                        or "localisation" in k
                        or "anatom" in k
                        or "disease category" in k
                        or k in {"category", "disease class", "disease group"}
                    ),
                )

                anatomy_ids = set()
                for key, value in anatomy_candidates:
                    for piece in split_values(value):
                        cid = map_anatomy_value(piece)
                        if cid:
                            anatomy_ids.add((cid, f"{key}={piece}"))
                        else:
                            anatomy_unmapped[(key, piece)] += 1

                for cid, basis in sorted(anatomy_ids):
                    cur.execute(
                        """INSERT IGNORE INTO disease_category_membership
                        (disease_id,category_id,membership_basis,source,curation_status)
                        VALUES(%s,%s,%s,'ODDB frozen source','mapped')""",
                        (did, cid, basis),
                    )
                    anatomy_n += cur.rowcount

                inh_candidates = []
                if d.get("inheritance"):
                    inh_candidates.append(("disease.inheritance", d["inheritance"]))
                inh_candidates += scalar_candidates(
                    src, lambda k: ("inherit" in k or "mode of" in k)
                )

                for a in dga_by_disease.get(did, []):
                    if a.get("inheritance"):
                        inh_candidates.append(("DGA.inheritance", a["inheritance"]))
                    asrc = load_json(a.get("source_record_json"))
                    inh_candidates += scalar_candidates(
                        asrc, lambda k: ("inherit" in k or "mode of" in k)
                    )

                inh_ids = set()
                for key, value in inh_candidates:
                    for piece in split_values(value):
                        inheritance_values[piece] += 1
                        for cid in inheritance_categories(piece):
                            inh_ids.add((cid, f"{key}={piece}"))

                for cid, basis in sorted(inh_ids):
                    cur.execute(
                        """INSERT IGNORE INTO disease_category_membership
                        (disease_id,category_id,membership_basis,source,curation_status)
                        VALUES(%s,%s,%s,'ODDB frozen source','mapped')""",
                        (did, cid, basis),
                    )
                    inheritance_n += cur.rowcount

                if d.get("mondo_id"):
                    links_n += add_link(
                        cur, "disease", did, "MONDO", d["mondo_id"],
                        "https://monarchinitiative.org/disease/"
                        + quote(str(d["mondo_id"]), safe=":"),
                    )
                if d.get("omim_id"):
                    om = re.sub(r"\D", "", str(d["omim_id"]))
                    if om:
                        links_n += add_link(
                            cur, "disease", did, "OMIM", d["omim_id"],
                            "https://omim.org/entry/" + om,
                        )

                for key, url in scalar_candidates(
                    src, lambda k: ("url" in k or "link" in k)
                ):
                    if re.match(r"^https?://", url, re.I):
                        links_n += add_link(
                            cur, "disease", did, key, None, url, 200,
                            "legacy_source_record_json",
                        )

            # ---------------- Genes ----------------
            cur.execute("""
                SELECT hgnc_id,gene_symbol,chromosome,gene_entity_type,
                       ensembl_gene_id,ncbi_gene_id,source_record_json
                FROM gene
            """)
            genes = cur.fetchall()
            gene_n = 0

            for g in genes:
                src = load_json(g.get("source_record_json"))
                vals = []
                if g.get("gene_entity_type"):
                    vals.append(g["gene_entity_type"])

                for key, value in scalar_candidates(
                    src,
                    lambda k: (
                        "locus type" in k
                        or "locus group" in k
                        or "gene type" in k
                        or "genetic entity" in k
                        or "biotype" in k
                    ),
                ):
                    vals.append(value)
                    gene_source_values[(key, value)] += 1

                cid = map_gene_category(
                    g.get("gene_symbol"), g.get("chromosome"), vals
                )
                if cid:
                    cur.execute(
                        """INSERT IGNORE INTO gene_category_membership
                        (hgnc_id,gene_category_id,membership_basis,source)
                        VALUES(%s,%s,%s,'HGNC/ODDB frozen source')""",
                        (g["hgnc_id"], cid, " | ".join(dict.fromkeys(vals))),
                    )
                    gene_n += cur.rowcount

                hid = g["hgnc_id"]
                if hid:
                    links_n += add_link(
                        cur, "gene", hid, "HGNC", hid,
                        "https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/"
                        + quote(str(hid), safe=":"),
                    )
                if g.get("ensembl_gene_id"):
                    x = str(g["ensembl_gene_id"])
                    links_n += add_link(
                        cur, "gene", hid, "Ensembl", x,
                        "https://www.ensembl.org/Homo_sapiens/Gene/Summary?g="
                        + quote(x),
                    )
                if g.get("ncbi_gene_id"):
                    x = str(g["ncbi_gene_id"])
                    links_n += add_link(
                        cur, "gene", hid, "NCBI Gene", x,
                        "https://www.ncbi.nlm.nih.gov/gene/" + quote(x),
                    )
                if g.get("gene_symbol"):
                    x = str(g["gene_symbol"])
                    links_n += add_link(
                        cur, "gene", hid, "GeneCards", x,
                        "https://www.genecards.org/cgi-bin/carddisp.pl?gene="
                        + quote(x),
                    )
                for key, url in scalar_candidates(
                    src, lambda k: ("url" in k or "link" in k)
                ):
                    if re.match(r"^https?://", url, re.I):
                        links_n += add_link(
                            cur, "gene", hid, key, None, url, 200,
                            "legacy_source_record_json",
                        )

            # ---------------- Variant links only ----------------
            # Consequence classification is deliberately NOT invented here.
            cur.execute("""
                SELECT variant_id,clinvar_variation_id,rs_id,source_record_json
                FROM variant
            """)
            processed = 0
            for v in cur:
                vid = v["variant_id"]
                if v.get("clinvar_variation_id"):
                    x = str(v["clinvar_variation_id"])
                    links_n += add_link(
                        cur, "variant", vid, "ClinVar", x,
                        "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
                        + quote(x) + "/",
                    )
                if v.get("rs_id"):
                    x = str(v["rs_id"]).strip()
                    if x:
                        links_n += add_link(
                            cur, "variant", vid, "dbSNP", x,
                            "https://www.ncbi.nlm.nih.gov/snp/" + quote(x),
                        )
                src = load_json(v.get("source_record_json"))
                for key, url in scalar_candidates(
                    src, lambda k: ("url" in k or "link" in k)
                ):
                    if re.match(r"^https?://", url, re.I):
                        links_n += add_link(
                            cur, "variant", vid, key, None, url, 200,
                            "legacy_source_record_json",
                        )
                processed += 1
                if processed % 50000 == 0:
                    conn.commit()
                    print(f"Variant links processed: {processed:,}")

            # ---------------- Drug links ----------------
            cur.execute("""
                SELECT drug_id,chembl_id,drugbank_id,pubchem_cid
                FROM drug
            """)
            for d in cur.fetchall():
                did = d["drug_id"]
                if d.get("chembl_id"):
                    x = str(d["chembl_id"])
                    links_n += add_link(
                        cur, "drug", did, "ChEMBL", x,
                        "https://www.ebi.ac.uk/chembl/explore/compound/" + quote(x),
                    )
                if d.get("drugbank_id"):
                    x = str(d["drugbank_id"])
                    links_n += add_link(
                        cur, "drug", did, "DrugBank", x,
                        "https://go.drugbank.com/drugs/" + quote(x),
                    )
                if d.get("pubchem_cid"):
                    x = str(d["pubchem_cid"])
                    links_n += add_link(
                        cur, "drug", did, "PubChem", x,
                        "https://pubchem.ncbi.nlm.nih.gov/compound/" + quote(x),
                    )

            cur.execute("SELECT clinical_trial_id,nct_id FROM clinical_trial")
            for t in cur.fetchall():
                if t.get("nct_id"):
                    x = str(t["nct_id"])
                    links_n += add_link(
                        cur, "trial", t["clinical_trial_id"],
                        "ClinicalTrials.gov", x,
                        "https://clinicaltrials.gov/study/" + quote(x),
                    )

            conn.commit()

            # ---------------- Report ----------------
            print("\nODDB v1 WEB TAXONOMY BACKFILL v0.3.1")
            print(f"anatomy_memberships: {anatomy_n:,}")
            print(f"inheritance_memberships: {inheritance_n:,}")
            print(f"gene_type_memberships: {gene_n:,}")
            cur.execute("SELECT COUNT(*) n FROM variant_consequence")
            print(f"variant_consequences_existing: {cur.fetchone()['n']:,}")
            print(f"external_links: {links_n:,}")

            print("\nDisease category counts:")
            cur.execute("""
                SELECT c.category_system,c.category_name,
                       COUNT(DISTINCT m.disease_id) n
                FROM disease_category c
                LEFT JOIN disease_category_membership m
                  ON m.category_id=c.category_id
                GROUP BY c.category_id,c.category_system,
                         c.category_name,c.display_order
                ORDER BY c.category_system,c.display_order
            """)
            for r in cur.fetchall():
                print(
                    f"{r['category_system']:12s} "
                    f"{r['category_name']:32s} {r['n']:4d}"
                )

            print("\nGene category counts:")
            cur.execute("""
                SELECT c.gene_category_id,c.category_name,c.entity_scope,
                       COUNT(DISTINCT m.hgnc_id) n
                FROM gene_category c
                LEFT JOIN gene_category_membership m
                  ON m.gene_category_id=c.gene_category_id
                GROUP BY c.gene_category_id,c.category_name,
                         c.entity_scope,c.display_order
                ORDER BY c.display_order
            """)
            for r in cur.fetchall():
                n = r["n"]
                if r["entity_scope"] == "locus":
                    cur.execute("SELECT COUNT(*) n FROM locus")
                    n = cur.fetchone()["n"]
                print(f"{r['category_name']:28s} {n:5d}")

            print("\nVariant consequence counts:")
            cur.execute("""
                SELECT c.consequence_term,
                       COUNT(DISTINCT v.variant_id) n
                FROM variant_consequence_category c
                LEFT JOIN variant_consequence v
                  ON v.consequence_id=c.consequence_id
                GROUP BY c.consequence_id,c.consequence_term,c.display_order
                ORDER BY c.display_order
            """)
            for r in cur.fetchall():
                print(f"{r['consequence_term']:38s} {r['n']:7d}")

            print("\nMost common raw inheritance values:")
            for value, n in inheritance_values.most_common(30):
                print(f"{n:5d}  {value}")

            print("\nMost common HGNC/ODDB gene-type source values:")
            for (key, value), n in gene_source_values.most_common(30):
                print(f"{n:5d}  {key} = {value}")

            if anatomy_unmapped:
                print("\nUnmapped anatomy/category source values:")
                for (key, value), n in anatomy_unmapped.most_common(30):
                    print(f"{n:5d}  {key} = {value}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
