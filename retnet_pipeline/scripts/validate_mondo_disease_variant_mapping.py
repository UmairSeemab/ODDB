#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


def clean(x):
    return str(x or "").strip()


def split_pipe(x):
    return [v.strip() for v in clean(x).split("|") if v.strip()]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--variants", required=True)
    ap.add_argument("--unresolved", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    before = pd.read_csv(args.before, sep="\t", dtype=str).fillna("")
    after = pd.read_csv(args.after, sep="\t", dtype=str).fillna("")
    disease = pd.read_csv(args.diseases, sep="\t", dtype=str).fillna("")
    variants = pd.read_csv(
        args.variants,
        sep="\t",
        dtype=str,
        usecols=["Variant_ID", "ClinVar_Variation_ID"]
    ).fillna("")

    required_after = [
        "Disease_Variant_Association_ID", "DiseaseID", "Variant_ID",
        "ClinVar_Variation_ID", "Mapping_Method"
    ]
    missing = [c for c in required_after if c not in after.columns]
    if missing:
        raise SystemExit(f"After table missing columns: {missing}")

    # ---------------------------------------------------------
    # Coverage comparison
    # ---------------------------------------------------------
    before_keys = set(zip(before["DiseaseID"], before["Variant_ID"]))
    after_keys = set(zip(after["DiseaseID"], after["Variant_ID"]))

    before_diseases = set(before["DiseaseID"])
    after_diseases = set(after["DiseaseID"])

    new_links = after_keys - before_keys
    lost_links = before_keys - after_keys
    gained_diseases = after_diseases - before_diseases
    lost_diseases = before_diseases - after_diseases

    comparison = pd.DataFrame([
        ["Associations_before", len(before)],
        ["Associations_after", len(after)],
        ["Net_association_gain", len(after) - len(before)],
        ["New_exact_association_keys", len(new_links)],
        ["Lost_previous_association_keys", len(lost_links)],
        ["Unique_variants_before", before["Variant_ID"].nunique()],
        ["Unique_variants_after", after["Variant_ID"].nunique()],
        ["Unique_diseases_before", before["DiseaseID"].nunique()],
        ["Unique_diseases_after", after["DiseaseID"].nunique()],
        ["Diseases_newly_gaining_variant_links", len(gained_diseases)],
        ["Diseases_losing_all_variant_links", len(lost_diseases)],
    ], columns=["Metric", "Value"])
    comparison.to_csv(
        outdir / "before_after_comparison.tsv", sep="\t", index=False
    )

    # ---------------------------------------------------------
    # Structural validation
    # ---------------------------------------------------------
    disease_ids = set(disease["DiseaseID"])
    variant_ids = set(variants["Variant_ID"])

    duplicate_assoc_id = after.duplicated(
        ["Disease_Variant_Association_ID"], keep=False
    )
    duplicate_pair = after.duplicated(
        ["DiseaseID", "Variant_ID"], keep=False
    )

    problems = []

    if duplicate_assoc_id.any():
        p = after.loc[duplicate_assoc_id].copy()
        p.insert(0, "Problem_Type", "duplicate_association_id")
        problems.append(p)

    if duplicate_pair.any():
        p = after.loc[duplicate_pair].copy()
        p.insert(0, "Problem_Type", "duplicate_disease_variant_pair")
        problems.append(p)

    p = after[~after["DiseaseID"].isin(disease_ids)].copy()
    if len(p):
        p.insert(0, "Problem_Type", "missing_disease_fk")
        problems.append(p)

    p = after[~after["Variant_ID"].isin(variant_ids)].copy()
    if len(p):
        p.insert(0, "Problem_Type", "missing_variant_fk")
        problems.append(p)

    problem_df = (
        pd.concat(problems, ignore_index=True)
        if problems
        else pd.DataFrame(columns=["Problem_Type"] + list(after.columns))
    )
    problem_df.to_csv(
        outdir / "disease_variant_validation_problems.tsv",
        sep="\t",
        index=False
    )

    # ---------------------------------------------------------
    # Mapping method distribution
    # ---------------------------------------------------------
    (
        after["Mapping_Method"]
        .value_counts()
        .rename_axis("Mapping_Method")
        .reset_index(name="Associations")
        .to_csv(
            outdir / "mapping_method_counts.tsv",
            sep="\t",
            index=False
        )
    )

    # Newly gained diseases
    gained = disease[disease["DiseaseID"].isin(gained_diseases)].copy()
    gained_counts = (
        after[after["DiseaseID"].isin(gained_diseases)]
        .groupby("DiseaseID")
        .agg(
            Disease_Variant_Associations=("Variant_ID", "size"),
            Unique_Variants=("Variant_ID", "nunique")
        )
        .reset_index()
    )
    gained = gained.merge(gained_counts, how="left", on="DiseaseID")
    cols = [
        c for c in [
            "DiseaseID", "Disease_Name", "MONDO_ID", "OMIM_ID",
            "Orphanet_ID", "MedGen_UMLS_CUI",
            "Disease_Variant_Associations", "Unique_Variants"
        ]
        if c in gained.columns
    ]
    gained[cols].sort_values(
        "Disease_Variant_Associations", ascending=False
    ).to_csv(
        outdir / "newly_mapped_diseases.tsv",
        sep="\t",
        index=False
    )

    # New exact links
    new_df = after[
        after.apply(
            lambda r: (r["DiseaseID"], r["Variant_ID"]) in new_links,
            axis=1
        )
    ].copy()
    new_df.to_csv(
        outdir / "new_exact_disease_variant_links.tsv",
        sep="\t",
        index=False
    )

    # ---------------------------------------------------------
    # Identifier collision audit in Disease master
    # ---------------------------------------------------------
    indexes = {
        "MONDO": defaultdict(set),
        "OMIM": defaultdict(set),
        "ORPHA": defaultdict(set),
        "CUI": defaultdict(set),
    }

    for _, r in disease.iterrows():
        did = clean(r.get("DiseaseID"))

        for x in split_pipe(r.get("MONDO_ID", "")):
            v = norm_mondo(x)
            if v:
                indexes["MONDO"][v].add(did)

        for x in split_pipe(r.get("OMIM_ID", "")):
            v = norm_omim(x)
            if v:
                indexes["OMIM"][v].add(did)

        for x in split_pipe(r.get("Orphanet_ID", "")):
            v = norm_orpha(x)
            if v:
                indexes["ORPHA"][v].add(did)

        for x in split_pipe(r.get("MedGen_UMLS_CUI", "")):
            v = norm_cui(x)
            if v:
                indexes["CUI"][v].add(did)

    collision_rows = []
    for namespace, idx in indexes.items():
        for identifier, dids in idx.items():
            if len(dids) > 1:
                names = []
                for did in sorted(dids):
                    hit = disease.loc[
                        disease["DiseaseID"] == did, "Disease_Name"
                    ]
                    names.append(
                        hit.iloc[0] if len(hit) else ""
                    )
                collision_rows.append({
                    "Namespace": namespace,
                    "Identifier": identifier,
                    "Disease_Count": len(dids),
                    "DiseaseIDs": " | ".join(sorted(dids)),
                    "Disease_Names": " | ".join(names),
                })

    collisions = pd.DataFrame(
        collision_rows,
        columns=[
            "Namespace", "Identifier", "Disease_Count",
            "DiseaseIDs", "Disease_Names"
        ]
    )
    collisions.to_csv(
        outdir / "disease_identifier_collisions.tsv",
        sep="\t",
        index=False
    )

    # ---------------------------------------------------------
    # Ambiguous concept summary
    # ---------------------------------------------------------
    amb_counter = Counter()
    amb_variants = defaultdict(set)

    with open(args.unresolved, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            status = clean(row.get("Status"))
            if not status.startswith("ambiguous"):
                continue

            name = clean(row.get("ClinVar_Phenotype_Name"))
            ids = clean(row.get("ClinVar_Phenotype_IDs"))
            cand = clean(row.get("Candidate_DiseaseIDs"))
            vid = clean(row.get("Variant_ID"))

            key = (status, name, ids, cand)
            amb_counter[key] += 1
            if vid:
                amb_variants[key].add(vid)

    ambiguous_rows = []
    for key, n in amb_counter.items():
        status, name, ids, cand = key
        ambiguous_rows.append({
            "Status": status,
            "ClinVar_Phenotype_Name": name,
            "ClinVar_Phenotype_IDs": ids,
            "Candidate_DiseaseIDs": cand,
            "Occurrence_Count": n,
            "Unique_Variant_Count": len(amb_variants[key]),
        })

    ambiguous_rows.sort(
        key=lambda r: -r["Occurrence_Count"]
    )

    pd.DataFrame(ambiguous_rows).to_csv(
        outdir / "ambiguous_concept_summary.tsv",
        sep="\t",
        index=False
    )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    summary = pd.DataFrame([
        ["Association_rows", len(after)],
        ["Unique_association_IDs",
         after["Disease_Variant_Association_ID"].nunique()],
        ["Unique_disease_variant_pairs",
         after[["DiseaseID", "Variant_ID"]].drop_duplicates().shape[0]],
        ["Unique_variants", after["Variant_ID"].nunique()],
        ["Unique_diseases", after["DiseaseID"].nunique()],
        ["Validation_problem_rows", len(problem_df)],
        ["Disease_identifier_collision_rows", len(collisions)],
        ["Unique_ambiguous_concept_records", len(ambiguous_rows)],
        ["New_exact_links_vs_pre_MONDO", len(new_links)],
        ["Lost_links_vs_pre_MONDO", len(lost_links)],
    ], columns=["Metric", "Value"])
    summary.to_csv(
        outdir / "disease_variant_validation_summary.tsv",
        sep="\t",
        index=False
    )

    print("ODDB DISEASE-VARIANT VALIDATION")
    print(summary.to_string(index=False))

    print("\nBefore/after MONDO:")
    print(comparison.to_string(index=False))

    if len(collisions):
        print("\nIdentifier collisions detected in Disease master:", len(collisions))
        print(
            collisions.head(20).to_string(index=False)
        )
    else:
        print("\nNo disease identifier collisions detected.")

    print("\nTop ambiguous ClinVar concepts:")
    if ambiguous_rows:
        print(
            pd.DataFrame(ambiguous_rows[:20]).to_string(index=False)
        )
    else:
        print("None")

    if len(problem_df) == 0:
        print("\nSTRUCTURAL VALIDATION PASSED.")
    else:
        print("\nSTRUCTURAL VALIDATION NEEDS REVIEW.")

    print(f"\nReports written to: {outdir}")


if __name__ == "__main__":
    main()
