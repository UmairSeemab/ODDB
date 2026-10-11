#!/usr/bin/env python3
import argparse
import csv
import hashlib
import re
import sqlite3
import unicodedata
from pathlib import Path


GENERIC_NAMES = {
    "", "-", "not provided", "not specified", "not applicable",
    "see cases", "variant of uncertain significance", "condition"
}

def clean(x):
    return str(x or "").strip()

def norm_name(s):
    s = unicodedata.normalize("NFKD", clean(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def stable_id(disease_id, variant_id):
    key = f"{clean(disease_id)}|{clean(variant_id)}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-DVA-{h}"

def split_multi(value):
    return [x.strip() for x in re.split(r"\s*[|;]\s*", clean(value)) if x.strip()]

def norm_omim(x):
    m = re.search(r"(\d{5,7})", clean(x))
    return m.group(1) if m else ""

def norm_orpha(x):
    m = re.search(r"(\d+)", clean(x))
    return m.group(1) if m else ""

def norm_mondo(x):
    m = re.search(r"(\d{4,})", clean(x))
    return f"MONDO:{m.group(1).zfill(7)}" if m else ""

def norm_cui(x):
    m = re.search(r"\b(CN?\d+|C\d+)\b", clean(x).upper())
    return m.group(1) if m else ""

def add_index(index, key, disease_id):
    if key:
        index.setdefault(key, set()).add(disease_id)

def parse_clinvar_ids(group):
    out = []
    for raw in re.split(r"\s*,\s*", clean(group)):
        if not raw:
            continue
        if ":" in raw:
            ns, val = raw.split(":", 1)
        else:
            ns, val = "", raw
        ns_l = ns.strip().lower()
        val = val.strip()

        if ns_l in {"medgen", "umls", "cui"}:
            v = norm_cui(val)
            if v:
                out.append(("CUI", v, raw))
        elif ns_l in {"omim", "mim"}:
            v = norm_omim(val)
            if v:
                out.append(("OMIM", v, raw))
        elif ns_l in {"orphanet", "orpha", "ordo"}:
            v = norm_orpha(val)
            if v:
                out.append(("ORPHA", v, raw))
        elif ns_l == "mondo":
            v = norm_mondo(val)
            if v:
                out.append(("MONDO", v, raw))
        else:
            # Handle forms like ORPHA100 / C0004135 without a colon.
            u = raw.upper()
            if u.startswith("ORPHA"):
                v = norm_orpha(raw)
                if v:
                    out.append(("ORPHA", v, raw))
            elif re.fullmatch(r"C[N]?\d+", u):
                out.append(("CUI", u, raw))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--sqlite-temp")
    args = ap.parse_args()

    disease_path = Path(args.diseases)
    variant_path = Path(args.variants)
    out_path = Path(args.output)
    report_dir = Path(args.report_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Build disease indexes using csv module to keep dependencies minimal.
    with disease_path.open("r", encoding="utf-8", newline="") as fh:
        dr = csv.DictReader(fh, delimiter="\t")
        disease_rows = list(dr)

    disease_by_id = {}
    id_indexes = {"CUI": {}, "OMIM": {}, "ORPHA": {}, "MONDO": {}}
    name_index = {}

    for r in disease_rows:
        did = clean(r.get("DiseaseID"))
        dname = clean(r.get("Disease_Name"))
        if not did:
            continue
        disease_by_id[did] = dname

        for x in split_multi(r.get("MedGen_UMLS_CUI", "")):
            add_index(id_indexes["CUI"], norm_cui(x), did)
        for x in split_multi(r.get("OMIM_ID", "")):
            add_index(id_indexes["OMIM"], norm_omim(x), did)
        for x in split_multi(r.get("Orphanet_ID", "")):
            add_index(id_indexes["ORPHA"], norm_orpha(x), did)
        for x in split_multi(r.get("MONDO_ID", "")):
            add_index(id_indexes["MONDO"], norm_mondo(x), did)

        names = [dname]
        names += split_multi(r.get("Synonyms", ""))
        names += split_multi(r.get("Alternative_Disease_Names_From_Legacy", ""))
        for n in names:
            nn = norm_name(n)
            if nn and nn not in GENERIC_NAMES:
                name_index.setdefault(nn, set()).add(did)

    db_path = Path(args.sqlite_temp) if args.sqlite_temp else report_dir / "_dva_tmp.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE dva (
            Disease_Variant_Association_ID TEXT PRIMARY KEY,
            DiseaseID TEXT NOT NULL,
            Disease_Name TEXT,
            Variant_ID TEXT NOT NULL,
            ClinVar_Variation_ID TEXT NOT NULL,
            Mapping_Method TEXT,
            Matched_Identifier TEXT,
            ClinVar_Phenotype_Name TEXT,
            ClinVar_Phenotype_IDs TEXT,
            RCV_Accessions_Raw TEXT,
            Variant_Level_Clinical_Significance TEXT,
            Variant_Level_Review_Status TEXT,
            Condition_Specific_Classification_Available TEXT,
            Source TEXT
        )
    """)
    con.execute("""
        CREATE TABLE unresolved (
            Status TEXT,
            Variant_ID TEXT,
            ClinVar_Variation_ID TEXT,
            ClinVar_Phenotype_Name TEXT,
            ClinVar_Phenotype_IDs TEXT,
            Candidate_DiseaseIDs TEXT
        )
    """)

    insert_dva = """
        INSERT OR IGNORE INTO dva VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    insert_unresolved = """
        INSERT INTO unresolved VALUES (?,?,?,?,?,?)
    """

    total_variants = 0
    phenotype_concepts = 0
    exact_id_links = 0
    exact_name_links = 0
    ambiguous = 0
    unmapped = 0
    no_phenotype = 0

    with variant_path.open("r", encoding="utf-8", newline="") as fh:
        vr = csv.DictReader(fh, delimiter="\t")
        required = {
            "Variant_ID", "ClinVar_Variation_ID", "Phenotype_IDs_Raw",
            "Phenotype_List_Raw", "RCV_Accessions_Raw",
            "Clinical_Significance", "Review_Status"
        }
        missing = required - set(vr.fieldnames or [])
        if missing:
            raise SystemExit(f"Variant table missing columns: {sorted(missing)}")

        for r in vr:
            total_variants += 1
            vid = clean(r["Variant_ID"])
            cvid = clean(r["ClinVar_Variation_ID"])
            id_groups = [x.strip() for x in clean(r["Phenotype_IDs_Raw"]).split(";")]
            name_groups = [x.strip() for x in clean(r["Phenotype_List_Raw"]).split(";")]

            if not any(id_groups) and not any(name_groups):
                no_phenotype += 1
                continue

            n = max(len(id_groups), len(name_groups))
            for i in range(n):
                ids_raw = id_groups[i] if i < len(id_groups) else ""
                name_raw = name_groups[i] if i < len(name_groups) else ""
                if not ids_raw and not name_raw:
                    continue
                phenotype_concepts += 1

                candidates = set()
                matched_ids = []

                for ns, value, raw in parse_clinvar_ids(ids_raw):
                    hits = id_indexes.get(ns, {}).get(value, set())
                    if hits:
                        candidates |= hits
                        matched_ids.append(raw)

                method = ""
                matched_identifier = ""

                if len(candidates) == 1:
                    method = "exact_identifier"
                    matched_identifier = ",".join(matched_ids)
                    exact_id_links += 1
                elif len(candidates) > 1:
                    ambiguous += 1
                    con.execute(
                        insert_unresolved,
                        ("ambiguous_identifier", vid, cvid, name_raw, ids_raw,
                         "|".join(sorted(candidates)))
                    )
                    continue
                else:
                    nn = norm_name(name_raw)
                    name_hits = name_index.get(nn, set()) if nn not in GENERIC_NAMES else set()
                    if len(name_hits) == 1:
                        candidates = set(name_hits)
                        method = "exact_name"
                        exact_name_links += 1
                    elif len(name_hits) > 1:
                        ambiguous += 1
                        con.execute(
                            insert_unresolved,
                            ("ambiguous_name", vid, cvid, name_raw, ids_raw,
                             "|".join(sorted(name_hits)))
                        )
                        continue
                    else:
                        unmapped += 1
                        con.execute(
                            insert_unresolved,
                            ("unmapped", vid, cvid, name_raw, ids_raw, "")
                        )
                        continue

                did = next(iter(candidates))
                assoc_id = stable_id(did, vid)
                con.execute(
                    insert_dva,
                    (
                        assoc_id,
                        did,
                        disease_by_id.get(did, ""),
                        vid,
                        cvid,
                        method,
                        matched_identifier,
                        name_raw,
                        ids_raw,
                        clean(r["RCV_Accessions_Raw"]),
                        clean(r["Clinical_Significance"]),
                        clean(r["Review_Status"]),
                        "No - variant_summary is variant-centric",
                        "NCBI ClinVar variant_summary"
                    )
                )

            if total_variants % 100000 == 0:
                con.commit()
                print(f"Processed {total_variants:,} variants...")

    con.commit()

    dva_rows = con.execute("SELECT COUNT(*) FROM dva").fetchone()[0]
    dva_variants = con.execute("SELECT COUNT(DISTINCT Variant_ID) FROM dva").fetchone()[0]
    dva_diseases = con.execute("SELECT COUNT(DISTINCT DiseaseID) FROM dva").fetchone()[0]

    cols = [
        "Disease_Variant_Association_ID","DiseaseID","Disease_Name","Variant_ID",
        "ClinVar_Variation_ID","Mapping_Method","Matched_Identifier",
        "ClinVar_Phenotype_Name","ClinVar_Phenotype_IDs","RCV_Accessions_Raw",
        "Variant_Level_Clinical_Significance","Variant_Level_Review_Status",
        "Condition_Specific_Classification_Available","Source"
    ]

    with out_path.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for row in con.execute(
            "SELECT " + ",".join('"' + c + '"' for c in cols) +
            " FROM dva ORDER BY DiseaseID, CAST(ClinVar_Variation_ID AS INTEGER)"
        ):
            w.writerow(row)

    unresolved_path = report_dir / "clinvar_disease_mapping_unresolved.tsv"
    with unresolved_path.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t", lineterminator="\n")
        w.writerow([
            "Status","Variant_ID","ClinVar_Variation_ID",
            "ClinVar_Phenotype_Name","ClinVar_Phenotype_IDs","Candidate_DiseaseIDs"
        ])
        for row in con.execute(
            "SELECT Status,Variant_ID,ClinVar_Variation_ID,ClinVar_Phenotype_Name,"
            "ClinVar_Phenotype_IDs,Candidate_DiseaseIDs FROM unresolved"
        ):
            w.writerow(row)

    summary = [
        ("Variant_rows_processed", total_variants),
        ("ClinVar_phenotype_concepts_processed", phenotype_concepts),
        ("Disease_variant_association_rows", dva_rows),
        ("Unique_variants_mapped_to_ODDB_disease", dva_variants),
        ("Unique_ODDB_diseases_with_variant_links", dva_diseases),
        ("Exact_identifier_concepts", exact_id_links),
        ("Exact_name_concepts", exact_name_links),
        ("Ambiguous_concepts", ambiguous),
        ("Unmapped_concepts", unmapped),
        ("Variants_without_phenotype_text_or_ids", no_phenotype),
    ]

    summary_path = report_dir / "disease_variant_build_summary.tsv"
    with summary_path.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t", lineterminator="\n")
        w.writerow(["Metric","Value"])
        w.writerows(summary)

    print("\nODDB DISEASE-VARIANT EXACT MAPPING")
    for k, v in summary:
        print(f"{k}: {v:,}")
    print(f"\nAssociation table: {out_path}")
    print(f"Unresolved review: {unresolved_path}")
    print(f"Summary: {summary_path}")
    print("\nOnly exact identifier or exact normalized-name mappings were accepted.")
    print("No fuzzy matches were promoted.")

    con.close()
    if not args.sqlite_temp and db_path.exists():
        db_path.unlink()

if __name__ == "__main__":
    main()
