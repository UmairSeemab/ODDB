#!/usr/bin/env python3
"""
Map Open Targets clinical_target context to canonical ODDB diseases.

Conservative matching only:
1) exact MONDO identifier
2) exact normalized canonical disease name
3) exact normalized disease alias

No fuzzy matching is promoted.

Inputs:
- OpenTargets_Clinical_Target_Context_v1
- Disease_v1_final
- Disease_Alias_v1_final
- Drug_v1_opentargets

Outputs:
- source-specific ODDB disease-drug clinical evidence table
- unresolved/ambiguous concept review tables
- summary report

Important:
This table represents Open Targets clinical context/evidence and does not
overwrite or replace the legacy Disease_Drug_Association table.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


def clean(x):
    return str(x or "").strip()


def norm_name(x):
    x = clean(x).lower()
    x = re.sub(r"[\u2010-\u2015]", "-", x)
    x = re.sub(r"[^a-z0-9]+", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def norm_mondo(x):
    x = clean(x).upper()
    m = re.search(r"MONDO[_:](\d+)", x)
    if not m:
        return ""
    return f"MONDO:{m.group(1).zfill(7)}"


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def uniq_join(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return " | ".join(out)


def json_load_safe(x):
    x = clean(x)
    if not x:
        return []
    try:
        v = json.loads(x)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def find_col(df, candidates, required=False):
    norm = {
        re.sub(r"[^a-z0-9]+", "", c.lower()): c
        for c in df.columns
    }
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in norm:
            return norm[key]
    if required:
        raise SystemExit(
            f"Required column not found among {candidates}. "
            f"Available: {list(df.columns)}"
        )
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clinical-context", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    clinical = pd.read_csv(
        args.clinical_context, sep="\t", dtype=str
    ).fillna("")
    diseases = pd.read_csv(
        args.diseases, sep="\t", dtype=str
    ).fillna("")
    aliases = pd.read_csv(
        args.aliases, sep="\t", dtype=str
    ).fillna("")
    drugs = pd.read_csv(
        args.drugs, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # Column discovery
    # ----------------------------
    disease_name_col = find_col(
        diseases, ["Disease_Name", "Ocular.disease"], required=True
    )
    mondo_col = find_col(
        diseases, ["MONDO_ID", "Mondo_ID", "MONDO"], required=False
    )

    alias_id_col = find_col(
        aliases,
        ["Canonical_DiseaseID", "DiseaseID"],
        required=True,
    )
    alias_name_col = find_col(
        aliases,
        ["Alias_Name", "Disease_Alias", "Alias", "Alias_Disease_Name"],
        required=False,
    )

    # If alias table uses a different structure, infer the likely text column.
    if alias_name_col is None:
        candidates = [
            c for c in aliases.columns
            if c not in {alias_id_col, "Alias_DiseaseID"}
            and aliases[c].dtype == object
        ]
        # Prefer columns containing 'name' or 'alias'
        preferred = [
            c for c in candidates
            if "name" in c.lower() or "alias" in c.lower()
        ]
        if preferred:
            alias_name_col = preferred[0]
        elif candidates:
            alias_name_col = candidates[0]
        else:
            raise SystemExit(
                "Could not identify disease alias text column."
            )

    # ----------------------------
    # Disease indexes
    # ----------------------------
    disease_name_map = dict(
        zip(diseases["DiseaseID"], diseases[disease_name_col])
    )

    mondo_index = defaultdict(set)
    name_index = defaultdict(set)
    alias_index = defaultdict(set)

    for _, r in diseases.iterrows():
        did = clean(r["DiseaseID"])
        nm = norm_name(r[disease_name_col])
        if nm:
            name_index[nm].add(did)

        if mondo_col:
            for raw in re.split(r"\s*[|;]\s*", clean(r[mondo_col])):
                m = norm_mondo(raw)
                if m:
                    mondo_index[m].add(did)

    for _, r in aliases.iterrows():
        did = clean(r[alias_id_col])
        alias = norm_name(r[alias_name_col])
        if did and alias:
            alias_index[alias].add(did)

    valid_drugs = set(drugs["Drug_ID"])
    drug_name_map = dict(
        zip(drugs["Drug_ID"], drugs["Preferred_Name"])
    )

    # ----------------------------
    # Explode clinical diseases
    # ----------------------------
    concept_rows = []

    for _, r in clinical.iterrows():
        diseases_json = json_load_safe(r["Diseases_JSON"])
        reports_json = json_load_safe(r["Clinical_Report_IDs_JSON"])

        for d in diseases_json:
            if not isinstance(d, dict):
                continue

            source_name = clean(d.get("diseaseFromSource"))
            source_id = clean(d.get("diseaseId"))

            concept_rows.append({
                "Drug_ID": clean(r["Drug_ID"]),
                "OpenTargets_Drug_ID":
                    clean(r.get("OpenTargets_Drug_ID")),
                "HGNC_ID": clean(r["HGNC_ID"]),
                "GeneSymbol": clean(r["GeneSymbol"]),
                "Ensembl_Gene_ID":
                    clean(r["Ensembl_Gene_ID"]),
                "OpenTargets_Clinical_Target_ID":
                    clean(r["OpenTargets_Clinical_Target_ID"]),
                "Maximum_Clinical_Stage":
                    clean(r["Maximum_Clinical_Stage"]),
                "OpenTargets_Disease_ID": source_id,
                "OpenTargets_Disease_Name": source_name,
                "Clinical_Report_IDs_JSON":
                    json.dumps(reports_json, ensure_ascii=False),
            })

    concepts = pd.DataFrame(concept_rows)

    # ----------------------------
    # Conservative mapping
    # ----------------------------
    mapped_rows = []
    unresolved_rows = []
    ambiguous_rows = []

    for _, r in concepts.iterrows():
        source_id = clean(r["OpenTargets_Disease_ID"])
        source_name = clean(r["OpenTargets_Disease_Name"])

        candidates = set()
        methods = []

        mondo = norm_mondo(source_id)
        if mondo and mondo in mondo_index:
            candidates |= mondo_index[mondo]
            methods.append("exact_mondo_identifier")

        nn = norm_name(source_name)
        if nn and nn in name_index:
            candidates |= name_index[nn]
            methods.append("exact_canonical_name")

        if nn and nn in alias_index:
            candidates |= alias_index[nn]
            methods.append("exact_alias_name")

        # Distinguish conflicting methods from a single clean mapping.
        if len(candidates) == 1:
            did = next(iter(candidates))

            mapped_rows.append({
                **r.to_dict(),
                "DiseaseID": did,
                "Disease_Name":
                    disease_name_map.get(did, ""),
                "Match_Method":
                    " | ".join(methods),
                "Mapping_Status": "exact",
            })

        elif len(candidates) > 1:
            ambiguous_rows.append({
                **r.to_dict(),
                "Candidate_DiseaseIDs":
                    " | ".join(sorted(candidates)),
                "Candidate_Disease_Names":
                    " | ".join(
                        sorted(
                            disease_name_map.get(x, x)
                            for x in candidates
                        )
                    ),
                "Candidate_Match_Methods":
                    " | ".join(methods),
                "Mapping_Status": "ambiguous",
            })

        else:
            unresolved_rows.append({
                **r.to_dict(),
                "Mapping_Status": "unmapped",
            })

    mapped = pd.DataFrame(mapped_rows)
    unresolved = pd.DataFrame(unresolved_rows)
    ambiguous = pd.DataFrame(ambiguous_rows)

    # ----------------------------
    # Aggregate to Disease + Drug
    # ----------------------------
    evidence_rows = []

    if len(mapped):
        for (did, drug_id), g in mapped.groupby(
            ["DiseaseID", "Drug_ID"],
            sort=True,
        ):
            evidence_rows.append({
                "Disease_Drug_OpenTargets_Evidence_ID":
                    stable_id("ODDB-DDOT", did, drug_id),
                "DiseaseID": did,
                "Disease_Name":
                    disease_name_map.get(did, ""),
                "Drug_ID": drug_id,
                "Drug_Name":
                    drug_name_map.get(drug_id, ""),
                "OpenTargets_Drug_IDs":
                    uniq_join(g["OpenTargets_Drug_ID"]),
                "Mapped_OpenTargets_Disease_IDs":
                    uniq_join(g["OpenTargets_Disease_ID"]),
                "Mapped_OpenTargets_Disease_Names":
                    uniq_join(g["OpenTargets_Disease_Name"]),
                "Target_Gene_Count":
                    g["HGNC_ID"].nunique(),
                "Target_HGNC_IDs":
                    uniq_join(g["HGNC_ID"]),
                "Target_Genes":
                    uniq_join(g["GeneSymbol"]),
                "Observed_Clinical_Stages":
                    uniq_join(g["Maximum_Clinical_Stage"]),
                "Clinical_Target_Context_Count":
                    g["OpenTargets_Clinical_Target_ID"].nunique(),
                "OpenTargets_Clinical_Target_IDs":
                    uniq_join(g["OpenTargets_Clinical_Target_ID"]),
                "Match_Methods":
                    uniq_join(g["Match_Method"]),
                "Evidence_Type":
                    "OpenTargets_clinical_target_context",
                "Source":
                    "Open Targets Platform",
                "Source_Release": "26.09",
                "Curation_Status":
                    "exact_disease_mapping_source_specific_evidence",
                "Interpretation":
                    "Open Targets provides clinical drug-target context "
                    "mapped exactly to this ODDB disease. This is retained "
                    "as source-specific disease-drug clinical evidence and "
                    "does not replace independent indication/approval review.",
            })

    evidence = pd.DataFrame(evidence_rows)

    # ----------------------------
    # Validation
    # ----------------------------
    problems = []

    if len(evidence):
        if evidence[
            "Disease_Drug_OpenTargets_Evidence_ID"
        ].duplicated().any():
            problems.append("duplicate evidence IDs")

        if evidence.duplicated(
            ["DiseaseID", "Drug_ID"]
        ).any():
            problems.append(
                "duplicate DiseaseID + Drug_ID evidence pairs"
            )

        if (~evidence["DiseaseID"].isin(
            set(diseases["DiseaseID"])
        )).any():
            problems.append("invalid DiseaseID foreign key")

        if (~evidence["Drug_ID"].isin(valid_drugs)).any():
            problems.append("invalid Drug_ID foreign key")

    summary = pd.DataFrame([
        ["Clinical_target_context_rows_input", len(clinical)],
        ["Exploded_disease_concepts", len(concepts)],
        ["Exact_mapped_concept_rows", len(mapped)],
        ["Ambiguous_concept_rows", len(ambiguous)],
        ["Unmapped_concept_rows", len(unresolved)],
        ["Disease_Drug_OpenTargets_evidence_rows", len(evidence)],
        ["Unique_ODDB_diseases_with_OpenTargets_evidence",
         evidence["DiseaseID"].nunique() if len(evidence) else 0],
        ["Unique_drugs_with_OpenTargets_disease_evidence",
         evidence["Drug_ID"].nunique() if len(evidence) else 0],
        ["Unique_target_genes_in_mapped_evidence",
         mapped["HGNC_ID"].nunique() if len(mapped) else 0],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # ----------------------------
    # Outputs
    # ----------------------------
    evidence.to_csv(
        args.output, sep="\t", index=False
    )

    mapped.to_csv(
        outdir / "opentargets_clinical_disease_concepts_mapped.tsv",
        sep="\t", index=False
    )

    ambiguous.to_csv(
        outdir / "opentargets_clinical_disease_concepts_ambiguous.tsv",
        sep="\t", index=False
    )

    unresolved.to_csv(
        outdir / "opentargets_clinical_disease_concepts_unresolved.tsv",
        sep="\t", index=False
    )

    summary.to_csv(
        outdir / "opentargets_disease_drug_mapping_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame(
        {"Problem": problems}
    ).to_csv(
        outdir / "opentargets_disease_drug_mapping_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB OPEN TARGETS DISEASE–DRUG CLINICAL EVIDENCE MAPPING")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nEvidence table:", args.output)
    print("Reports:", outdir)

    print(
        "\nOnly exact MONDO/name/alias matches were promoted. "
        "No fuzzy matches were accepted."
    )


if __name__ == "__main__":
    main()
