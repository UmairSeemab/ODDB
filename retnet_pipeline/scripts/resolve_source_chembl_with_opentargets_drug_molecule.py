#!/usr/bin/env python3
"""
Resolve ODDB clinical-report source ChEMBL IDs against Open Targets drug_molecule.

AUDIT ONLY. No canonical or frozen files are modified.

This script corrects the identity-level counting artifact from the previous
audit by using only (Drug_ID, Source_Drug_ID) as the mismatch identity key.

For every unique mismatching source ChEMBL ID it retrieves the corresponding
Open Targets drug_molecule record and compares:
- preferred/name
- parentId
- childChemblIds
- InChIKey
- drug type
- synonyms
- trade names

It then classifies whether there is an explicit parent/child relationship or
whether the pair needs manual identity review.
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds


def clean(x):
    if x is None:
        return ""
    return str(x).strip()


def norm(x):
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", " ", x)
    return " ".join(x.split())


def as_list(x):
    if x is None:
        return []
    if hasattr(x, "tolist"):
        x = x.tolist()
    if isinstance(x, (list, tuple, set)):
        return [clean(v) for v in x if clean(v)]
    s = clean(x)
    if not s:
        return []
    return [v.strip() for v in re.split(r"\s*[|;,]\s*", s) if v.strip()]


def json_safe(x):
    if x is None:
        return None
    if hasattr(x, "tolist"):
        return json_safe(x.tolist())
    if isinstance(x, dict):
        return {str(k): json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [json_safe(v) for v in x]
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--mismatch-detail", required=True)
    ap.add_argument("--drug-molecule-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    mm = pd.read_csv(
        args.mismatch_detail, sep="\t", dtype=str
    ).fillna("")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Correct identity-level de-duplication:
    identities = (
        mm[[
            "Drug_ID",
            "Drug_Name",
            "Canonical_ChEMBL_ID",
            "Source_Drug_ID",
        ]]
        .drop_duplicates(["Drug_ID", "Source_Drug_ID"])
        .copy()
    )

    drug_lookup = {
        clean(r["Drug_ID"]): r.to_dict()
        for _, r in drugs.iterrows()
    }

    source_ids = sorted(
        set(
            x.upper()
            for x in identities["Source_Drug_ID"]
            if clean(x).upper().startswith("CHEMBL")
        )
    )

    dm_path = Path(args.drug_molecule_dir)
    if not dm_path.exists():
        raise SystemExit(
            f"drug_molecule path not found: {dm_path}"
        )

    dataset = ds.dataset(
        str(dm_path),
        format="parquet",
        partitioning="hive",
    )

    available = set(dataset.schema.names)

    wanted = [
        "id",
        "name",
        "parentId",
        "childChemblIds",
        "canonicalSmiles",
        "inchiKey",
        "drugType",
        "synonyms",
        "tradeNames",
        "crossReferences",
        "maximumClinicalStage",
        "description",
    ]
    cols = [c for c in wanted if c in available]

    table = dataset.to_table(
        columns=cols,
        filter=ds.field("id").isin(source_ids),
    )

    dm = table.to_pandas().fillna("")

    source_lookup = {
        clean(r["id"]).upper(): r.to_dict()
        for _, r in dm.iterrows()
    }

    resolved_rows = []

    for _, ident in identities.iterrows():
        drug_id = clean(ident["Drug_ID"])
        source_id = clean(
            ident["Source_Drug_ID"]
        ).upper()

        canonical = drug_lookup.get(drug_id, {})
        src = source_lookup.get(source_id)

        canonical_chembl = clean(
            canonical.get("ChEMBL_ID")
        ).upper()

        canonical_parent = clean(
            canonical.get("OpenTargets_Parent_ID")
        ).upper()

        preferred = clean(
            canonical.get("Preferred_Name")
        )

        if src is None:
            resolved_rows.append({
                "Drug_ID": drug_id,
                "Drug_Name": preferred,
                "Canonical_ChEMBL_ID": canonical_chembl,
                "Canonical_OpenTargets_Parent_ID":
                    canonical_parent,
                "Source_Drug_ID": source_id,
                "Source_OT_Name": "",
                "Source_OT_Parent_ID": "",
                "Source_OT_Child_ChEMBL_IDs": "",
                "Source_OT_InChIKey": "",
                "Source_OT_Drug_Type": "",
                "Source_OT_Maximum_Clinical_Stage": "",
                "Name_Matches_Canonical": "",
                "Identity_Resolution_Class":
                    "source_chembl_not_found_in_drug_molecule",
                "Recommended_Action":
                    "manual_review",
            })
            continue

        source_name = clean(src.get("name"))
        source_parent = clean(
            src.get("parentId")
        ).upper()

        children = [
            clean(x).upper()
            for x in as_list(src.get("childChemblIds"))
        ]

        syns = as_list(src.get("synonyms"))
        trades = as_list(src.get("tradeNames"))

        known_names = {
            norm(preferred),
            norm(canonical.get("Normalized_Name")),
        }

        for col in [
            "Alternative_Names_From_Legacy",
            "OpenTargets_Synonyms",
            "OpenTargets_Trade_Names",
        ]:
            for x in as_list(canonical.get(col)):
                if norm(x):
                    known_names.add(norm(x))

        source_names = {
            norm(source_name),
            *(norm(x) for x in syns),
            *(norm(x) for x in trades),
        }
        source_names.discard("")

        name_match = bool(
            known_names.intersection(source_names)
        )

        # Explicit relation checks first.
        if canonical_chembl and source_parent == canonical_chembl:
            cls = "source_is_explicit_child_of_canonical"
            action = (
                "preserve_separate_drug_entities_and_add_form_relationship"
            )

        elif canonical_chembl and canonical_chembl in children:
            cls = "source_explicitly_lists_canonical_as_child"
            action = (
                "preserve_separate_drug_entities_and_review_direction"
            )

        elif canonical_parent and source_id == canonical_parent:
            cls = "source_is_explicit_parent_of_canonical"
            action = (
                "preserve_separate_drug_entities_and_add_form_relationship"
            )

        elif canonical_chembl:
            cls = "different_chembl_no_explicit_relation"
            action = (
                "manual_identity_review_no_automatic_remap"
            )

        elif name_match and not source_parent:
            cls = "missing_canonical_chembl_exact_identity_candidate"
            action = (
                "candidate_for_canonical_chembl_enrichment_after_review"
            )

        elif name_match and source_parent:
            cls = "missing_canonical_chembl_source_has_parent"
            action = (
                "review_parent_before_assigning_source_chembl"
            )

        else:
            cls = "missing_canonical_chembl_name_not_confirmed"
            action = (
                "manual_identity_review"
            )

        resolved_rows.append({
            "Drug_ID": drug_id,
            "Drug_Name": preferred,
            "Canonical_ChEMBL_ID": canonical_chembl,
            "Canonical_OpenTargets_Parent_ID":
                canonical_parent,
            "Source_Drug_ID": source_id,
            "Source_OT_Name": source_name,
            "Source_OT_Parent_ID": source_parent,
            "Source_OT_Child_ChEMBL_IDs":
                " | ".join(children),
            "Source_OT_InChIKey":
                clean(src.get("inchiKey")),
            "Source_OT_Drug_Type":
                clean(src.get("drugType")),
            "Source_OT_Maximum_Clinical_Stage":
                clean(src.get("maximumClinicalStage")),
            "Source_OT_Synonyms":
                " | ".join(syns),
            "Source_OT_Trade_Names":
                " | ".join(trades),
            "Name_Matches_Canonical":
                "Yes" if name_match else "No",
            "Identity_Resolution_Class": cls,
            "Recommended_Action": action,
        })

    resolved = pd.DataFrame(resolved_rows)

    counts = (
        resolved["Identity_Resolution_Class"]
        .value_counts()
        .rename_axis("Identity_Resolution_Class")
        .reset_index(name="Unique_Identity_Pair_Count")
    )

    different = resolved[
        resolved["Canonical_ChEMBL_ID"].ne("")
    ].copy()

    missing = resolved[
        resolved["Canonical_ChEMBL_ID"].eq("")
    ].copy()

    summary = pd.DataFrame([
        ["Mismatch_links_input", len(mm)],
        [
            "Unique_identity_pairs_DrugID_SourceChEMBL",
            len(identities),
        ],
        [
            "Unique_source_ChEMBL_IDs",
            len(source_ids),
        ],
        [
            "Source_ChEMBL_records_found_in_drug_molecule",
            int(
                resolved[
                    "Identity_Resolution_Class"
                ].ne(
                    "source_chembl_not_found_in_drug_molecule"
                ).sum()
            ),
        ],
        [
            "Source_ChEMBL_records_not_found",
            int(
                resolved[
                    "Identity_Resolution_Class"
                ].eq(
                    "source_chembl_not_found_in_drug_molecule"
                ).sum()
            ),
        ],
        [
            "Identity_pairs_with_missing_canonical_ChEMBL",
            len(missing),
        ],
        [
            "Identity_pairs_with_different_canonical_ChEMBL",
            len(different),
        ],
        [
            "Explicit_parent_child_relationship_pairs",
            int(
                resolved[
                    "Identity_Resolution_Class"
                ].isin([
                    "source_is_explicit_child_of_canonical",
                    "source_explicitly_lists_canonical_as_child",
                    "source_is_explicit_parent_of_canonical",
                ]).sum()
            ),
        ],
    ], columns=["Metric", "Value"])

    resolved.to_csv(
        outdir / "drug_source_chembl_identity_resolution.tsv",
        sep="\t",
        index=False,
    )

    missing.to_csv(
        outdir / "missing_canonical_chembl_resolution.tsv",
        sep="\t",
        index=False,
    )

    different.to_csv(
        outdir / "different_canonical_chembl_resolution.tsv",
        sep="\t",
        index=False,
    )

    counts.to_csv(
        outdir / "drug_source_chembl_resolution_class_counts.tsv",
        sep="\t",
        index=False,
    )

    summary.to_csv(
        outdir / "drug_source_chembl_resolution_summary.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB SOURCE ChEMBL / OPEN TARGETS DRUG-MOLECULE RESOLUTION")
    print(summary.to_string(index=False))

    print("\nResolution classes:")
    print(counts.to_string(index=False))

    print("\nDIFFERENT CANONICAL ChEMBL CASES:")
    if len(different):
        cols_show = [
            "Drug_ID",
            "Drug_Name",
            "Canonical_ChEMBL_ID",
            "Source_Drug_ID",
            "Source_OT_Name",
            "Source_OT_Parent_ID",
            "Source_OT_Child_ChEMBL_IDs",
            "Source_OT_InChIKey",
            "Identity_Resolution_Class",
            "Recommended_Action",
        ]
        print(
            different[cols_show]
            .to_string(index=False)
        )
    else:
        print("None")

    print("\nReports:", outdir)
    print(
        "\nAUDIT ONLY: no canonical or frozen files were modified."
    )


if __name__ == "__main__":
    main()
