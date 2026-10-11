#!/usr/bin/env python3
"""
Patch the four externally-normalized ODDB legacy drug entities without
changing their internal Drug_IDs.

Updates:
- AMA0076 -> Sovesudil
- Cholestyramine
- Padeliporfin Potassium
- Vitamin E

Important:
- Existing ODDB Drug_ID values are preserved.
- Disease_Drug_Association foreign keys therefore remain stable.
- Structure fields are intentionally left blank for non-discrete entities
  (e.g. cholestyramine resin, generic vitamin E).
- Multiple valid external cross-references are preserved rather than collapsed.
"""

import argparse
from pathlib import Path
import pandas as pd


def clean(x):
    return str(x or "").strip()


def add_alt(existing, values):
    out = []
    seen = set()
    for x in [clean(existing)] + list(values):
        if not x:
            continue
        parts = [p.strip() for p in x.split(" | ") if p.strip()]
        for p in parts:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return " | ".join(out)


PATCHES = {
    "Ama0076": {
        "Preferred_Name": "Sovesudil",
        "Alternative_Names_From_Legacy_add": [
            "Ama0076", "AMA0076", "AMA-0076", "PHP-201", "PHP201"
        ],
        "Standard_InChIKey": "PNWBYIFLWUCWKS-UHFFFAOYSA-N",
        "PubChem_CID": "68245749",
        "DrugBank_ID": "DB18812",
        "ChEMBL_ID": "CHEMBL2440750",
        "ChEMBL_ID_Alternative": "CHEMBL3545073",
        "UNII": "C23O3R93BM",
        "DrugBank_Salt_ID": "",
        "Parent_DrugBank_ID": "",
        "Drug_Entity_Type": "small_molecule",
        "External_Normalization_Status": "verified",
        "External_Normalization_Notes":
            "AMA0076 is the development code for sovesudil. "
            "CHEMBL2440750 is the ChEMBL/GtoPdb molecule cross-reference; "
            "CHEMBL3545073 is also used by Open Targets/FDA GSRS and is "
            "preserved as an alternative cross-reference."
    },
    "Cholestyramine": {
        "Preferred_Name": "Cholestyramine",
        "Alternative_Names_From_Legacy_add": [
            "Cholestyramine resin", "Colestyramine"
        ],
        "Standard_InChIKey": "",
        "PubChem_CID": "",
        "DrugBank_ID": "DB01432",
        "ChEMBL_ID": "CHEMBL1201625",
        "ChEMBL_ID_Alternative": "",
        "UNII": "4B33BGI082",
        "DrugBank_Salt_ID": "",
        "Parent_DrugBank_ID": "",
        "Drug_Entity_Type": "polymeric_drug_resin",
        "External_Normalization_Status": "verified_non_discrete_structure",
        "External_Normalization_Notes":
            "Cholestyramine is a polymeric anion-exchange resin. "
            "No discrete PubChem compound CID/InChIKey is assigned; "
            "structure-specific identifiers are intentionally left blank."
    },
    "Padeliporfin Potassium": {
        "Preferred_Name": "Padeliporfin potassium",
        "Alternative_Names_From_Legacy_add": [
            "Padeliporfin Potassium", "Padeliporfin dipotassium",
            "WST-11 dipotassium", "Tookad"
        ],
        # Deliberately blank: current authoritative resources differ in
        # representation/InChIKey for the potassium salt.
        "Standard_InChIKey": "",
        "PubChem_CID": "135391044",
        "DrugBank_ID": "DB15575",
        "ChEMBL_ID": "CHEMBL4594285",
        "ChEMBL_ID_Alternative": "",
        "UNII": "JQ72VD4XUL",
        "DrugBank_Salt_ID": "DBSALT003133",
        "Parent_DrugBank_ID": "DB15575",
        "Drug_Entity_Type": "drug_salt",
        "External_Normalization_Status": "verified_structure_representation_review",
        "External_Normalization_Notes":
            "Padeliporfin potassium is a salt/product ingredient of parent "
            "padeliporfin. PubChem CID and ChEMBL ID are retained. "
            "The InChIKey is intentionally left blank because current "
            "authoritative resources encode the salt differently."
    },
    "Vitamin e": {
        "Preferred_Name": "Vitamin E",
        "Alternative_Names_From_Legacy_add": [
            "Vitamin e", "Vitamin E", "tocopherols"
        ],
        "Standard_InChIKey": "",
        "PubChem_CID": "",
        "DrugBank_ID": "DB00163",
        "ChEMBL_ID": "CHEMBL3989727",
        "ChEMBL_ID_Alternative": "",
        "UNII": "",
        "DrugBank_Salt_ID": "",
        "Parent_DrugBank_ID": "",
        "Drug_Entity_Type": "vitamin_group_or_mixture",
        "External_Normalization_Status": "verified_non_discrete_structure",
        "External_Normalization_Notes":
            "Vitamin E is an umbrella term covering multiple tocopherols and "
            "tocotrienols. It is not automatically collapsed to alpha-tocopherol; "
            "therefore no discrete PubChem CID/InChIKey is assigned."
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--disease-drug", required=True)
    ap.add_argument("--drug-output", required=True)
    ap.add_argument("--disease-drug-output", required=True)
    ap.add_argument("--report-output", required=True)
    args = ap.parse_args()

    drugs = pd.read_csv(args.drugs, sep="\t", dtype=str).fillna("")
    dda = pd.read_csv(args.disease_drug, sep="\t", dtype=str).fillna("")

    for col in [
        "ChEMBL_ID_Alternative",
        "UNII",
        "DrugBank_Salt_ID",
        "Parent_DrugBank_ID",
        "External_Normalization_Status",
        "External_Normalization_Notes",
    ]:
        if col not in drugs.columns:
            drugs[col] = ""

    report_rows = []

    for legacy_name, patch in PATCHES.items():
        mask = drugs["Preferred_Name"].astype(str).str.strip().eq(legacy_name)

        if mask.sum() != 1:
            raise SystemExit(
                f"Expected exactly one Drug row for {legacy_name!r}; "
                f"found {mask.sum()}"
            )

        idx = drugs.index[mask][0]
        drug_id = clean(drugs.at[idx, "Drug_ID"])
        old_name = clean(drugs.at[idx, "Preferred_Name"])

        drugs.at[idx, "Preferred_Name"] = patch["Preferred_Name"]
        drugs.at[idx, "Normalized_Name"] = patch["Preferred_Name"].lower()

        drugs.at[idx, "Alternative_Names_From_Legacy"] = add_alt(
            drugs.at[idx, "Alternative_Names_From_Legacy"],
            patch["Alternative_Names_From_Legacy_add"]
        )

        for col in [
            "Standard_InChIKey",
            "PubChem_CID",
            "DrugBank_ID",
            "ChEMBL_ID",
            "ChEMBL_ID_Alternative",
            "UNII",
            "DrugBank_Salt_ID",
            "Parent_DrugBank_ID",
            "Drug_Entity_Type",
            "External_Normalization_Status",
            "External_Normalization_Notes",
        ]:
            drugs.at[idx, col] = patch[col]

        drugs.at[idx, "Identifier_Curation_Status"] = (
            "externally_normalized_verified"
        )

        # Update display name on disease-drug rows but preserve Drug_ID.
        dda_mask = dda["Drug_ID"].eq(drug_id)
        dda.loc[dda_mask, "Drug_Name"] = patch["Preferred_Name"]

        report_rows.append({
            "Drug_ID": drug_id,
            "Old_Name": old_name,
            "Preferred_Name": patch["Preferred_Name"],
            "PubChem_CID": patch["PubChem_CID"],
            "DrugBank_ID": patch["DrugBank_ID"],
            "DrugBank_Salt_ID": patch["DrugBank_Salt_ID"],
            "ChEMBL_ID": patch["ChEMBL_ID"],
            "ChEMBL_ID_Alternative": patch["ChEMBL_ID_Alternative"],
            "UNII": patch["UNII"],
            "Drug_Entity_Type": patch["Drug_Entity_Type"],
            "Disease_Drug_Rows_Updated": int(dda_mask.sum()),
            "Normalization_Status": patch["External_Normalization_Status"],
        })

    # Validation
    problems = []

    if drugs["Drug_ID"].duplicated().any():
        problems.append("duplicate Drug_ID after patch")

    if dda["Disease_Drug_Association_ID"].duplicated().any():
        problems.append("duplicate Disease_Drug_Association_ID after patch")

    if (~dda["Drug_ID"].isin(set(drugs["Drug_ID"]))).any():
        problems.append("Disease_Drug_Association contains invalid Drug_ID")

    still_name_only = drugs[
        drugs["Identifier_Curation_Status"]
        == "name_only_needs_external_normalization"
    ]

    if len(still_name_only):
        problems.append(
            f"{len(still_name_only)} name-only drug(s) remain unresolved"
        )

    Path(args.drug_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.disease_drug_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_output).parent.mkdir(parents=True, exist_ok=True)

    drugs.to_csv(args.drug_output, sep="\t", index=False)
    dda.to_csv(args.disease_drug_output, sep="\t", index=False)

    report = pd.DataFrame(report_rows)
    report.to_csv(args.report_output, sep="\t", index=False)

    print("ODDB DRUG EXTERNAL NORMALIZATION PATCH")
    print(report.to_string(index=False))

    print("\nFinal drug master:")
    print("Rows:", len(drugs))
    print("Unique Drug_IDs:", drugs["Drug_ID"].nunique())
    print(
        "Remaining name-only drugs:",
        len(still_name_only)
    )
    print(
        "Drugs with ChEMBL ID:",
        int(drugs["ChEMBL_ID"].astype(str).str.strip().ne("").sum())
    )
    print(
        "Drugs with DrugBank ID:",
        int(drugs["DrugBank_ID"].astype(str).str.strip().ne("").sum())
    )
    print(
        "Drugs with PubChem CID:",
        int(drugs["PubChem_CID"].astype(str).str.strip().ne("").sum())
    )

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print(f"\nDrug master: {args.drug_output}")
    print(f"Disease-drug table: {args.disease_drug_output}")
    print(f"Normalization report: {args.report_output}")


if __name__ == "__main__":
    main()
