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


INHERITANCE_PREFIXES = [
    (r"^(autosomal\s+)?recessive\b", "Autosomal recessive"),
    (r"^(autosomal\s+)?dominant\b", "Autosomal dominant"),
    (r"^x[\s-]*linked\b", "X-linked"),
    (r"^mitochondrial\b", "Mitochondrial"),
    (r"^maternal(?:ly inherited)?\b", "Mitochondrial"),
]


def strip_inheritance(phenotype):
    raw = str(phenotype or "").strip()
    low = norm_text(raw)

    inferred = ""
    core = raw

    for pattern, label in INHERITANCE_PREFIXES:
        m = re.match(pattern, low, flags=re.I)
        if m:
            inferred = label

            # Strip the equivalent prefix from the original text conservatively.
            core = re.sub(
                pattern,
                "",
                raw,
                count=1,
                flags=re.I,
            ).strip(" ,;:-")
            break

    return inferred, core


def split_phenotype_segment(segment):
    # RetNet sometimes stores two disease names in one DOM segment separated
    # by semicolons. Split only on semicolons. Do not split on commas because
    # commas can be part of one disease name.
    return [
        x.strip()
        for x in re.split(r"\s*;\s*", str(segment or ""))
        if x.strip()
    ]


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

    # Give a mild boost when one complete normalized disease name contains
    # the other, but never turn it into an automatic exact match.
    containment = 0.0
    if a_n in b_n or b_n in a_n:
        shorter = min(len(a_n), len(b_n))
        longer = max(len(a_n), len(b_n))
        containment = shorter / longer if longer else 0.0

    return max(seq, jac, containment)


def inheritance_compatible(candidate_inh, phenotype_inh):
    c = norm_text(candidate_inh)
    p = norm_text(phenotype_inh)

    if not p:
        return True

    mapping = {
        "autosomal recessive": "autosomal recessive",
        "recessive": "autosomal recessive",
        "autosomal dominant": "autosomal dominant",
        "dominant": "autosomal dominant",
        "x linked": "x linked",
        "x-linked": "x linked",
        "mitochondrial": "mitochondrial",
    }

    c2 = mapping.get(c, c)
    p2 = mapping.get(p, p)
    return c2 == p2


def best_oddb_match(phenotype_core, oddb_diseases):
    target = norm_text(phenotype_core)

    exact = [
        row for row in oddb_diseases
        if norm_text(row["ODDB_Disease"]) == target
    ]

    if exact:
        return {
            "status": "exact",
            "score": 1.0,
            "disease_id": exact[0]["ODDB_DiseaseID"],
            "disease": exact[0]["ODDB_Disease"],
        }

    scored = []
    for row in oddb_diseases:
        score = similarity(phenotype_core, row["ODDB_Disease"])
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "status": "no_oddb_diseases",
            "score": 0.0,
            "disease_id": "",
            "disease": "",
        }

    score, row = scored[0]

    # Conservative thresholds. These are suggestions only.
    if score >= 0.92:
        status = "high_confidence_suggestion"
    elif score >= 0.78:
        status = "review_suggestion"
    else:
        status = "no_close_oddb_match"

    return {
        "status": status,
        "score": score,
        "disease_id": row["ODDB_DiseaseID"],
        "disease": row["ODDB_Disease"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--details", required=True)
    ap.add_argument("--oddb", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--summary-output", required=False)
    args = ap.parse_args()

    cand = pd.read_csv(args.candidates, sep="\t", dtype=str).fillna("")
    details = pd.read_csv(args.details, sep="\t", dtype=str).fillna("")
    oddb = pd.read_csv(args.oddb, sep="\t", dtype=str).fillna("")

    required_c = {
        "Integration_Class",
        "Approved_GeneSymbol",
        "HGNC_ID",
        "RetNet_Disease_Category",
        "Inheritance",
    }
    miss = required_c - set(cand.columns)
    if miss:
        raise SystemExit(f"Candidate file missing columns: {sorted(miss)}")

    required_d = {
        "RetNet_Primary_Symbol",
        "Disease_Phenotype_Segments",
        "Location",
    }
    miss = required_d - set(details.columns)
    if miss:
        raise SystemExit(f"Details file missing columns: {sorted(miss)}")

    if "Ocular.disease" not in oddb.columns or "DiseaseID" not in oddb.columns:
        raise SystemExit("ODDB file must contain Ocular.disease and DiseaseID.")

    review = cand[
        cand["Integration_Class"].eq("D_disease_mapping_review")
    ].copy()

    # One canonical row per ODDB disease.
    disease_rows = (
        oddb[["DiseaseID", "Ocular.disease"]]
        .drop_duplicates()
        .rename(columns={
            "DiseaseID": "ODDB_DiseaseID",
            "Ocular.disease": "ODDB_Disease",
        })
        .to_dict("records")
    )

    details_by_symbol = {}
    for _, r in details.iterrows():
        symbol = str(r["RetNet_Primary_Symbol"]).strip().upper()
        if symbol:
            details_by_symbol.setdefault(symbol, []).append(r)

    out_rows = []

    for _, r in review.iterrows():
        gene = str(r["Approved_GeneSymbol"]).strip()
        symbol_key = gene.upper()

        matching_details = details_by_symbol.get(symbol_key, [])

        if not matching_details:
            row = r.to_dict()
            row.update({
                "Detailed_Record_Found": "No",
                "Detailed_Location": "",
                "Detailed_Phenotype_Raw": "",
                "Detailed_Phenotype_Core": "",
                "Detailed_Phenotype_Inheritance": "",
                "Inheritance_Compatible": "",
                "Suggested_ODDB_DiseaseID": "",
                "Suggested_ODDB_Disease": "",
                "Detailed_Disease_Match_Status": "no_detailed_record",
                "Detailed_Disease_Match_Score": "",
                "Disease_Harmonization_Action": "manual_review",
            })
            out_rows.append(row)
            continue

        produced = 0

        for det in matching_details:
            try:
                segments = json.loads(det["Disease_Phenotype_Segments"])
            except Exception:
                segments = []

            phenotype_items = []
            for seg in segments:
                phenotype_items.extend(split_phenotype_segment(seg))

            # First pass: retain inheritance-compatible phenotypes.
            compatible = []
            fallback = []

            for phenotype in phenotype_items:
                ph_inh, core = strip_inheritance(phenotype)
                item = (phenotype, ph_inh, core)

                if inheritance_compatible(r["Inheritance"], ph_inh):
                    compatible.append(item)
                else:
                    fallback.append(item)

            # If RetNet DOM did not include an inheritance prefix for any
            # relevant phenotype, compatible will still contain those items.
            # If every item appears incompatible, retain all for manual review
            # rather than silently dropping the gene.
            chosen = compatible if compatible else fallback

            for phenotype, ph_inh, core in chosen:
                match = best_oddb_match(core, disease_rows)

                if match["status"] == "exact":
                    action = "candidate_exact_oddb_disease"
                elif match["status"] == "high_confidence_suggestion":
                    action = "review_high_confidence_match"
                elif match["status"] == "review_suggestion":
                    action = "review_possible_match"
                elif match["status"] == "no_close_oddb_match":
                    action = "review_possible_new_disease"
                else:
                    action = "manual_review"

                row = r.to_dict()
                row.update({
                    "Detailed_Record_Found": "Yes",
                    "Detailed_Location": str(det["Location"]).strip(),
                    "Detailed_Phenotype_Raw": phenotype,
                    "Detailed_Phenotype_Core": core,
                    "Detailed_Phenotype_Inheritance": ph_inh,
                    "Inheritance_Compatible": (
                        "Yes"
                        if inheritance_compatible(r["Inheritance"], ph_inh)
                        else "No"
                    ),
                    "Suggested_ODDB_DiseaseID": match["disease_id"],
                    "Suggested_ODDB_Disease": match["disease"],
                    "Detailed_Disease_Match_Status": match["status"],
                    "Detailed_Disease_Match_Score": f"{match['score']:.4f}",
                    "Disease_Harmonization_Action": action,
                })
                out_rows.append(row)
                produced += 1

        if produced == 0:
            row = r.to_dict()
            row.update({
                "Detailed_Record_Found": "Yes",
                "Detailed_Location": "",
                "Detailed_Phenotype_Raw": "",
                "Detailed_Phenotype_Core": "",
                "Detailed_Phenotype_Inheritance": "",
                "Inheritance_Compatible": "",
                "Suggested_ODDB_DiseaseID": "",
                "Suggested_ODDB_Disease": "",
                "Detailed_Disease_Match_Status": "no_parsed_phenotype",
                "Detailed_Disease_Match_Score": "",
                "Disease_Harmonization_Action": "manual_review",
            })
            out_rows.append(row)

    out = pd.DataFrame(out_rows)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, sep="\t", index=False)

    print(f"Input disease-review candidate rows: {len(review)}")
    print(f"Output candidate × detailed-phenotype rows: {len(out)}")
    print(
        "Genes with detailed record:",
        out.loc[out["Detailed_Record_Found"].eq("Yes"), "HGNC_ID"]
        .replace("", pd.NA).dropna().nunique()
    )
    print(
        "Genes without detailed record:",
        out.loc[out["Detailed_Record_Found"].eq("No"), "HGNC_ID"]
        .replace("", pd.NA).dropna().nunique()
    )

    print("\nDetailed disease match status:")
    print(out["Detailed_Disease_Match_Status"].value_counts().to_string())

    print("\nSuggested action:")
    print(out["Disease_Harmonization_Action"].value_counts().to_string())

    if args.summary_output:
        summary = (
            out.groupby(
                ["Detailed_Disease_Match_Status", "Disease_Harmonization_Action"],
                dropna=False
            )
            .size()
            .reset_index(name="Rows")
        )
        Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(args.summary_output, sep="\t", index=False)
        print(f"\nSummary written: {args.summary_output}")

    print(f"\nReview table written: {args.output}")
    print("No ODDB records were changed.")

if __name__ == "__main__":
    main()
