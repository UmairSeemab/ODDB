#!/usr/bin/env python3
"""
Build the clean legacy ODDB drug layer.

Creates:
  1) Drug_v1_legacy
     One row per normalized drug entity.

  2) Disease_Drug_Association_v1_legacy
     One row per canonical DiseaseID + Drug_ID.

IMPORTANT:
- GeneSymbol is deliberately ignored when creating drug relationships because
  the legacy audit showed disease-level drugs were replicated across genes.
- Phase is stored on the disease-drug relationship, not on the Drug entity.
- No Gene/Drug_Target associations are created by this script.
"""

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path

import pandas as pd


def clean(x):
    return str(x or "").strip()


def norm_name(x):
    x = clean(x).lower()
    x = re.sub(r"\s+", " ", x)
    return x


def uniq_join(values):
    out, seen = [], set()
    for x in values:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return " | ".join(out)


def preferred_name(values):
    vals = [clean(x) for x in values if clean(x)]
    if not vals:
        return ""
    counts = Counter(vals)
    # Most frequent; deterministic alphabetical tie break.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))[0][0]


def stable_drug_id(inchikey, cid, drugbank, name_norm):
    if clean(inchikey):
        identity = f"INCHIKEY|{clean(inchikey).upper()}"
    elif clean(cid):
        identity = f"PUBCHEM|{clean(cid)}"
    elif clean(drugbank):
        identity = f"DRUGBANK|{clean(drugbank).upper()}"
    else:
        identity = f"NAME|{name_norm}"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-DRUG-{digest}", identity.split("|", 1)[0].lower()


def stable_dda_id(disease_id, drug_id):
    key = f"{clean(disease_id)}|{clean(drug_id)}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"ODDB-DDA-{digest}"


def phase_number(x):
    x = clean(x)
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def fmt_phase(x):
    if x is None:
        return ""
    if float(x).is_integer():
        return str(int(x))
    return str(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--canonical-diseases", required=True)
    ap.add_argument("--drug-output", required=True)
    ap.add_argument("--disease-drug-output", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    legacy = pd.read_csv(args.legacy, sep="\t", dtype=str).fillna("")
    diseases = pd.read_csv(
        args.canonical_diseases, sep="\t", dtype=str
    ).fillna("")

    required = [
        "DiseaseID", "Ocular.disease", "Drug_name", "Phase",
        "Merged_RefNew", "Standard_inchiKey", "CID", "DrugBank_ID"
    ]
    missing = [c for c in required if c not in legacy.columns]
    if missing:
        raise SystemExit(f"Missing legacy columns: {missing}")

    for c in required:
        legacy[c] = legacy[c].map(clean)

    canonical_ids = set(diseases["DiseaseID"])
    disease_name_map = dict(
        zip(diseases["DiseaseID"], diseases["Disease_Name"])
    )

    drug_rows = legacy[legacy["Drug_name"].ne("")].copy()
    drug_rows["Drug_Name_Normalized"] = drug_rows["Drug_name"].map(norm_name)

    # ------------------------------------------------------------------
    # Drug master
    # ------------------------------------------------------------------
    drug_master_rows = []
    name_to_drug_id = {}

    for name_norm, g in drug_rows.groupby("Drug_Name_Normalized", sort=True):
        inchikeys = sorted(set(x for x in g["Standard_inchiKey"] if x))
        cids = sorted(set(x for x in g["CID"] if x))
        drugbanks = sorted(set(x for x in g["DrugBank_ID"] if x))

        if len(inchikeys) > 1 or len(cids) > 1 or len(drugbanks) > 1:
            raise SystemExit(
                f"Identifier conflict for drug {name_norm!r}. "
                "Resolve conflicts before canonical build."
            )

        inchikey = inchikeys[0] if inchikeys else ""
        cid = cids[0] if cids else ""
        drugbank = drugbanks[0] if drugbanks else ""

        did, basis = stable_drug_id(
            inchikey, cid, drugbank, name_norm
        )
        name_to_drug_id[name_norm] = did

        observed_names = sorted(set(x for x in g["Drug_name"] if x))
        pref = preferred_name(g["Drug_name"])

        drug_master_rows.append({
            "Drug_ID": did,
            "Preferred_Name": pref,
            "Normalized_Name": name_norm,
            "Alternative_Names_From_Legacy": " | ".join(
                x for x in observed_names if x != pref
            ),
            "Standard_InChIKey": inchikey,
            "PubChem_CID": cid,
            "DrugBank_ID": drugbank,
            "ChEMBL_ID": "",
            "Drug_Entity_Type": "drug_or_therapeutic_compound",
            "Identity_Basis": basis,
            "Identifier_Curation_Status":
                "legacy_identifier_available"
                if (inchikey or cid or drugbank)
                else "name_only_needs_external_normalization",
            "Legacy_Disease_Count":
                g["DiseaseID"].replace("", pd.NA).nunique(dropna=True),
            "Legacy_Source_Row_Count": len(g),
            "Source": "ODDB legacy drug layer",
        })

    drug_master = pd.DataFrame(drug_master_rows)

    # Detect accidental Drug_ID collision.
    if drug_master["Drug_ID"].duplicated().any():
        dup = drug_master[
            drug_master["Drug_ID"].duplicated(keep=False)
        ]
        raise SystemExit(
            "Drug_ID collision detected:\n" + dup.to_string(index=False)
        )

    # ------------------------------------------------------------------
    # Disease-drug associations
    # ------------------------------------------------------------------
    dda_rows = []

    for (disease_id, name_norm), g in drug_rows.groupby(
        ["DiseaseID", "Drug_Name_Normalized"], sort=True
    ):
        if not disease_id or not name_norm:
            continue

        if disease_id not in canonical_ids:
            raise SystemExit(
                f"Non-canonical DiseaseID in drug data: {disease_id}"
            )

        drug_id = name_to_drug_id[name_norm]
        phase_values = sorted(
            set(x for x in g["Phase"] if clean(x)),
            key=lambda x: (
                phase_number(x) is None,
                phase_number(x) if phase_number(x) is not None else x
            )
        )
        numeric_phases = [
            phase_number(x) for x in phase_values
            if phase_number(x) is not None
        ]
        max_phase = max(numeric_phases) if numeric_phases else None

        refs = uniq_join(g["Merged_RefNew"])

        dda_rows.append({
            "Disease_Drug_Association_ID":
                stable_dda_id(disease_id, drug_id),
            "DiseaseID": disease_id,
            "Disease_Name": disease_name_map.get(disease_id, ""),
            "Drug_ID": drug_id,
            "Drug_Name": preferred_name(g["Drug_name"]),
            "Relationship_Type": "legacy_disease_drug_evidence",
            "Observed_Development_Phases": " | ".join(phase_values),
            "Maximum_Observed_Phase": fmt_phase(max_phase),
            "Phase_Curation_Note":
                "Phase retained from legacy disease-drug evidence; "
                "not a Drug entity attribute.",
            "References": refs,
            "Reference_Count":
                g.loc[g["Merged_RefNew"].ne(""), "Merged_RefNew"].nunique(),
            "Evidence_Source": "ODDB legacy drug layer",
            "Evidence_Provenance":
                "Disease-level relationship recovered from merged legacy table. "
                "Gene columns were ignored because audit demonstrated systematic "
                "disease-drug replication across genes.",
            "Curation_Status":
                "retained_pending_external_validation",
            "Legacy_Source_Row_Count": len(g),
        })

    dda = pd.DataFrame(dda_rows)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    problems = []

    if dda["Disease_Drug_Association_ID"].duplicated().any():
        problems.append("duplicate Disease_Drug_Association_ID")

    if dda.duplicated(["DiseaseID", "Drug_ID"]).any():
        problems.append("duplicate DiseaseID + Drug_ID pairs")

    if (~dda["DiseaseID"].isin(canonical_ids)).any():
        problems.append("invalid DiseaseID foreign key")

    if (~dda["Drug_ID"].isin(set(drug_master["Drug_ID"]))).any():
        problems.append("invalid Drug_ID foreign key")

    name_only = drug_master[
        drug_master["Identifier_Curation_Status"]
        == "name_only_needs_external_normalization"
    ].copy()

    multiphase = dda[
        dda["Observed_Development_Phases"].str.contains(
            r"\|", regex=True, na=False
        )
    ].copy()

    report = pd.DataFrame([
        ["Drug_master_rows", len(drug_master)],
        ["Unique_Drug_IDs", drug_master["Drug_ID"].nunique()],
        ["Drugs_with_InChIKey",
         int(drug_master["Standard_InChIKey"].ne("").sum())],
        ["Drugs_with_PubChem_CID",
         int(drug_master["PubChem_CID"].ne("").sum())],
        ["Drugs_with_DrugBank_ID",
         int(drug_master["DrugBank_ID"].ne("").sum())],
        ["Drugs_name_only_pending_external_normalization", len(name_only)],
        ["Disease_Drug_Association_rows", len(dda)],
        ["Unique_diseases_with_drugs", dda["DiseaseID"].nunique()],
        ["Disease_drug_pairs_with_multiple_phase_values", len(multiphase)],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    outdir = Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    Path(args.drug_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.disease_drug_output).parent.mkdir(parents=True, exist_ok=True)

    drug_master.to_csv(args.drug_output, sep="\t", index=False)
    dda.to_csv(args.disease_drug_output, sep="\t", index=False)
    name_only.to_csv(
        outdir / "drug_name_only_pending_external_normalization.tsv",
        sep="\t", index=False
    )
    multiphase.to_csv(
        outdir / "disease_drug_multiphase_review.tsv",
        sep="\t", index=False
    )
    report.to_csv(
        outdir / "drug_layer_build_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame(
        {"Problem": problems}
    ).to_csv(
        outdir / "drug_layer_build_problems.tsv",
        sep="\t", index=False
    )

    print("ODDB CLEAN LEGACY DRUG LAYER BUILD")
    print(report.to_string(index=False))

    print("\nName-only drugs requiring external identifier normalization:")
    if len(name_only):
        print(
            name_only[
                [
                    "Drug_ID",
                    "Preferred_Name",
                    "Legacy_Disease_Count",
                    "Legacy_Source_Row_Count"
                ]
            ].to_string(index=False)
        )
    else:
        print("None")

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print(f"\nDrug master: {args.drug_output}")
    print(f"Disease-drug associations: {args.disease_drug_output}")
    print(f"Reports: {outdir}")
    print("\nNo gene/drug-target associations were inferred from legacy data.")


if __name__ == "__main__":
    main()
