#!/usr/bin/env python3
import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd

def norm_text(value):
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[/_,:()\[\]]+", " ", s)
    s = re.sub(r"[-–—]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

INHERITANCE_PATTERNS = [
    (r"^(?:autosomal\s+)?recessive\b", "Autosomal recessive"),
    (r"^(?:autosomal\s+)?dominant\b", "Autosomal dominant"),
    (r"^x[\s-]*linked\b", "X-linked"),
    (r"^mitochondrial\b", "Mitochondrial"),
    (r"^maternal(?:ly inherited)?\b", "Mitochondrial"),
]

PARENT_RULES = [
    (r"\busher syndrome\b", "USHER SYNDROME"),
    (r"\bleber congenital amaurosis\b", "LEBER CONGENITAL AMAUROSIS"),
    (r"\bretinitis pigmentosa\b", "RETINITIS PIGMENTOSA"),
    (r"\bcone[- ]rod dystrophy\b", "CONE-ROD DYSTROPHY"),
    (r"\bjoubert syndrome\b", "JOUBERT SYNDROME"),
    (r"\bsenior[- ]loken syndrome\b", "SENIOR-LOKEN SYNDROME"),
    (r"\bbardet[- ]biedl syndrome\b", "BARDET-BIEDL SYNDROME"),
    (r"\bmeckel syndrome\b", "MECKEL SYNDROME"),
    (r"\bnephronophthisis\b", "NEPHRONOPHTHISIS"),
    (r"\boptic atrophy\b", "OPTIC ATROPHY"),
    (r"\bstickler syndrome\b", "STICKLER SYNDROME"),
    (r"\bwolfram syndrome\b", "WOLFRAM SYNDROME"),
    (r"\bknobloch syndrome\b", "KNOBLOCH SYNDROME"),
    (r"\bachromatopsia\b", "ACHROMATOPSIA"),
    (r"\bretinoschisis\b", "RETINOSCHISIS"),
    (r"\bchoroideremia\b", "CHOROIDEREMIA"),
    (r"\bmacular dystrophy\b", "MACULAR DYSTROPHY"),
    (r"\bretinal degeneration\b", "RETINAL DEGENERATION"),
    (r"\bretinal dystrophy\b", "RETINAL DYSTROPHY"),
    (r"\bceroid lipofuscinosis\b", "CEROID LIPOFUSCINOSIS, NEURONAL"),
    (r"\brefsum disease\b", "REFSUM DISEASE"),
    (r"\bspastic paraplegia\b", "SPASTIC PARAPLEGIA"),
    (r"\bspinocerebellar ataxia\b", "SPINOCEREBELLAR ATAXIA"),
]

def strip_inheritance(phenotype):
    raw = str(phenotype or "").strip()
    low = norm_text(raw)
    for pattern, label in INHERITANCE_PATTERNS:
        if re.match(pattern, low, flags=re.I):
            core = re.sub(pattern, "", raw, count=1, flags=re.I).strip(" ,;:-")
            return label, core
    return "", raw

def split_phenotype_segment(segment):
    return [x.strip() for x in re.split(r"\s*;\s*", str(segment or "")) if x.strip()]

def canonical_inheritance(value):
    s = norm_text(value)
    if s in {"autosomal recessive", "recessive"}:
        return "Autosomal recessive"
    if s in {"autosomal dominant", "dominant"}:
        return "Autosomal dominant"
    if s in {"x linked", "x-linked"}:
        return "X-linked"
    if s == "mitochondrial":
        return "Mitochondrial"
    return str(value or "").strip()

def inheritance_compatible(candidate_inh, phenotype_inh):
    if not phenotype_inh:
        return True
    return canonical_inheritance(candidate_inh) == canonical_inheritance(phenotype_inh)

def token_jaccard(a, b):
    ta = set(norm_text(a).split())
    tb = set(norm_text(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def similarity(a, b):
    a_n = norm_text(a)
    b_n = norm_text(b)
    if not a_n or not b_n:
        return 0.0
    seq = SequenceMatcher(None, a_n, b_n).ratio()
    jac = token_jaccard(a_n, b_n)
    containment = 0.0
    if a_n in b_n or b_n in a_n:
        shorter = min(len(a_n), len(b_n))
        longer = max(len(a_n), len(b_n))
        containment = shorter / longer if longer else 0.0
    return max(seq, jac, containment)

def disease_lookup(oddb):
    rows = (
        oddb[["DiseaseID", "Ocular.disease"]]
        .drop_duplicates()
        .rename(columns={"DiseaseID": "ODDB_DiseaseID", "Ocular.disease": "ODDB_Disease"})
    )
    by_norm = {}
    for _, r in rows.iterrows():
        by_norm.setdefault(norm_text(r["ODDB_Disease"]), []).append(
            {"ODDB_DiseaseID": str(r["ODDB_DiseaseID"]).strip(),
             "ODDB_Disease": str(r["ODDB_Disease"]).strip()}
        )
    return rows.to_dict("records"), by_norm

def exact_oddb(core, by_norm):
    hits = by_norm.get(norm_text(core), [])
    return hits[0] if hits else None

def parent_oddb(core, by_norm):
    n = norm_text(core)
    for pattern, canonical in PARENT_RULES:
        if re.search(pattern, n, flags=re.I):
            hits = by_norm.get(norm_text(canonical), [])
            if hits:
                return hits[0], canonical
    return None, ""

def fuzzy_oddb(core, oddb_rows):
    scored = [(similarity(core, x["ODDB_Disease"]), x) for x in oddb_rows]
    scored.sort(key=lambda z: z[0], reverse=True)
    if not scored:
        return 0.0, {"ODDB_DiseaseID": "", "ODDB_Disease": ""}
    return scored[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--details", required=True)
    ap.add_argument("--oddb", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--summary-output")
    args = ap.parse_args()

    cand = pd.read_csv(args.candidates, sep="\t", dtype=str).fillna("")
    details = pd.read_csv(args.details, sep="\t", dtype=str).fillna("")
    oddb = pd.read_csv(args.oddb, sep="\t", dtype=str).fillna("")

    review = cand[cand["Integration_Class"].eq("D_disease_mapping_review")].copy()
    oddb_rows, by_norm = disease_lookup(oddb)

    details_by_symbol = {}
    for _, r in details.iterrows():
        s = str(r["RetNet_Primary_Symbol"]).strip().upper()
        if s:
            details_by_symbol.setdefault(s, []).append(r)

    out = []

    for _, c in review.iterrows():
        gene = str(c["Approved_GeneSymbol"]).strip()
        recs = details_by_symbol.get(gene.upper(), [])

        if not recs:
            row = c.to_dict()
            row.update({
                "Detailed_Record_Found": "No",
                "Detailed_Phenotype_Raw": "",
                "Detailed_Phenotype_Core": "",
                "Detailed_Phenotype_Inheritance": "",
                "Inheritance_Compatible": "",
                "Suggested_ODDB_DiseaseID": "",
                "Suggested_ODDB_Disease": "",
                "Detailed_Disease_Match_Status": "no_detailed_record",
                "Detailed_Disease_Match_Score": "",
                "Disease_Harmonization_Action": "manual_review",
                "Parent_Rule": "",
            })
            out.append(row)
            continue

        produced = False
        for det in recs:
            try:
                segs = json.loads(det["Disease_Phenotype_Segments"])
            except Exception:
                segs = []

            phenotypes = []
            for seg in segs:
                phenotypes.extend(split_phenotype_segment(seg))

            for phenotype in phenotypes:
                ph_inh, core = strip_inheritance(phenotype)
                compatible = inheritance_compatible(c["Inheritance"], ph_inh)

                row = c.to_dict()
                row.update({
                    "Detailed_Record_Found": "Yes",
                    "Detailed_Location": str(det.get("Location", "")).strip(),
                    "Detailed_Phenotype_Raw": phenotype,
                    "Detailed_Phenotype_Core": core,
                    "Detailed_Phenotype_Inheritance": ph_inh,
                    "Inheritance_Compatible": "Yes" if compatible else "No",
                    "Parent_Rule": "",
                })

                if not compatible:
                    row.update({
                        "Suggested_ODDB_DiseaseID": "",
                        "Suggested_ODDB_Disease": "",
                        "Detailed_Disease_Match_Status": "inheritance_conflict",
                        "Detailed_Disease_Match_Score": "",
                        "Disease_Harmonization_Action": "manual_review_inheritance_conflict",
                    })
                    out.append(row)
                    produced = True
                    continue

                exact = exact_oddb(core, by_norm)
                if exact:
                    row.update({
                        "Suggested_ODDB_DiseaseID": exact["ODDB_DiseaseID"],
                        "Suggested_ODDB_Disease": exact["ODDB_Disease"],
                        "Detailed_Disease_Match_Status": "exact",
                        "Detailed_Disease_Match_Score": "1.0000",
                        "Disease_Harmonization_Action": "candidate_exact_oddb_disease",
                    })
                    out.append(row)
                    produced = True
                    continue

                parent, rule_name = parent_oddb(core, by_norm)
                if parent:
                    row.update({
                        "Suggested_ODDB_DiseaseID": parent["ODDB_DiseaseID"],
                        "Suggested_ODDB_Disease": parent["ODDB_Disease"],
                        "Detailed_Disease_Match_Status": "parent_disease_suggestion",
                        "Detailed_Disease_Match_Score": "",
                        "Disease_Harmonization_Action": "review_parent_disease_match",
                        "Parent_Rule": rule_name,
                    })
                    out.append(row)
                    produced = True
                    continue

                score, best = fuzzy_oddb(core, oddb_rows)
                if score >= 0.92:
                    status = "high_confidence_suggestion"
                    action = "review_high_confidence_match"
                elif score >= 0.78:
                    status = "review_suggestion"
                    action = "review_possible_match"
                else:
                    status = "no_close_oddb_match"
                    action = "review_possible_new_disease"

                row.update({
                    "Suggested_ODDB_DiseaseID": best["ODDB_DiseaseID"],
                    "Suggested_ODDB_Disease": best["ODDB_Disease"],
                    "Detailed_Disease_Match_Status": status,
                    "Detailed_Disease_Match_Score": f"{score:.4f}",
                    "Disease_Harmonization_Action": action,
                })
                out.append(row)
                produced = True

        if not produced:
            row = c.to_dict()
            row.update({
                "Detailed_Record_Found": "Yes",
                "Detailed_Phenotype_Raw": "",
                "Detailed_Phenotype_Core": "",
                "Detailed_Phenotype_Inheritance": "",
                "Inheritance_Compatible": "",
                "Suggested_ODDB_DiseaseID": "",
                "Suggested_ODDB_Disease": "",
                "Detailed_Disease_Match_Status": "no_parsed_phenotype",
                "Detailed_Disease_Match_Score": "",
                "Disease_Harmonization_Action": "manual_review",
                "Parent_Rule": "",
            })
            out.append(row)

    result = pd.DataFrame(out)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, sep="\t", index=False)

    print(f"Input disease-review candidate rows: {len(review)}")
    print(f"Output candidate × detailed-phenotype rows: {len(result)}")
    print("\nDetailed disease match status:")
    print(result["Detailed_Disease_Match_Status"].value_counts().to_string())
    print("\nSuggested action:")
    print(result["Disease_Harmonization_Action"].value_counts().to_string())
    print(f"\nInheritance conflicts isolated: {(result['Detailed_Disease_Match_Status'] == 'inheritance_conflict').sum()}")

    if args.summary_output:
        summary = (
            result.groupby(
                ["Detailed_Disease_Match_Status", "Disease_Harmonization_Action"],
                dropna=False
            ).size().reset_index(name="Rows")
        )
        Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(args.summary_output, sep="\t", index=False)
        print(f"Summary written: {args.summary_output}")

    print(f"Review table written: {args.output}")
    print("No ODDB records were changed.")

if __name__ == "__main__":
    main()
