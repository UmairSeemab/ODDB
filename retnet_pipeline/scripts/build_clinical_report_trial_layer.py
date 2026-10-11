#!/usr/bin/env python3
"""
Build ODDB v1 Clinical Report / Clinical Trial layer from Open Targets 26.09
clinical_report parquet.

Core design
-----------
Clinical_Report_v1
    One row per Open Targets clinical report relevant to ODDB, where at least
    one ODDB disease and at least one ODDB drug are mapped.

Disease_Clinical_Report_Association_v1
    Disease -> clinical report links.

Drug_Clinical_Report_Association_v1
    Drug -> clinical report links.

ClinicalTrial_v1
    Subset of relevant clinical reports that contain an NCT identifier.

Disease_ClinicalTrial_Association_v1
Drug_ClinicalTrial_Association_v1

IMPORTANT
---------
We DO NOT create disease-drug cross-products from multi-disease/multi-drug
reports. Reports and trials are modeled as independent entities with separate
disease and drug association tables.

Disease mapping:
1) exact MONDO ID
2) exact canonical disease name
3) exact disease alias
No fuzzy promotion.

Drug mapping:
1) exact ChEMBL/Open Targets drug ID
2) exact unique normalized drug name
No fuzzy promotion.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


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
    return f"MONDO:{m.group(1).zfill(7)}" if m else ""


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def uniq(values):
    out, seen = [], set()
    for v in values:
        v = clean(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def uniq_join(values):
    return " | ".join(uniq(values))


def json_safe(value):
    if value is None:
        return None

    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass

    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def json_text(value):
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
    )


def as_list(value):
    value = json_safe(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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


def extract_nct_ids(*values):
    hits = []
    for value in values:
        text = clean(value)
        if not text:
            continue
        hits.extend(
            x.upper()
            for x in re.findall(r"\bNCT\d{8}\b", text, flags=re.I)
        )
    return uniq(hits)


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--clinical-report-parquet", required=True)
    ap.add_argument("--diseases", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--drugs", required=True)

    ap.add_argument("--clinical-report-output", required=True)
    ap.add_argument("--disease-report-output", required=True)
    ap.add_argument("--drug-report-output", required=True)

    ap.add_argument("--clinical-trial-output", required=True)
    ap.add_argument("--disease-trial-output", required=True)
    ap.add_argument("--drug-trial-output", required=True)

    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--release", default="26.09")

    args = ap.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    for path in [
        args.clinical_report_output,
        args.disease_report_output,
        args.drug_report_output,
        args.clinical_trial_output,
        args.disease_trial_output,
        args.drug_trial_output,
    ]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load canonical ODDB data
    # ------------------------------------------------------------------
    diseases = pd.read_csv(
        args.diseases, sep="\t", dtype=str
    ).fillna("")

    aliases = pd.read_csv(
        args.aliases, sep="\t", dtype=str
    ).fillna("")

    drugs = pd.read_csv(
        args.drugs, sep="\t", dtype=str
    ).fillna("")

    disease_name_col = find_col(
        diseases,
        ["Disease_Name", "Ocular.disease", "Disease"],
        required=True,
    )

    mondo_col = find_col(
        diseases,
        ["MONDO_ID", "Mondo_ID", "MONDO"],
        required=False,
    )

    alias_disease_col = find_col(
        aliases,
        ["Canonical_DiseaseID", "DiseaseID"],
        required=True,
    )

    alias_name_col = find_col(
        aliases,
        ["Alias_Name", "Disease_Alias", "Alias", "Alias_Disease_Name"],
        required=False,
    )

    if alias_name_col is None:
        candidates = [
            c for c in aliases.columns
            if c != alias_disease_col
        ]
        preferred = [
            c for c in candidates
            if "alias" in c.lower() or "name" in c.lower()
        ]
        if preferred:
            alias_name_col = preferred[0]
        elif candidates:
            alias_name_col = candidates[0]
        else:
            raise SystemExit("Cannot identify disease alias text column.")

    drug_name_col = find_col(
        drugs,
        ["Preferred_Name", "Drug_Name", "Name"],
        required=True,
    )

    # ------------------------------------------------------------------
    # Disease indexes
    # ------------------------------------------------------------------
    disease_name_map = dict(
        zip(diseases["DiseaseID"], diseases[disease_name_col])
    )

    mondo_index = defaultdict(set)
    disease_name_index = defaultdict(set)
    disease_alias_index = defaultdict(set)

    for _, r in diseases.iterrows():
        did = clean(r["DiseaseID"])

        nm = norm_name(r[disease_name_col])
        if nm:
            disease_name_index[nm].add(did)

        if mondo_col:
            raw_values = re.split(
                r"\s*[|;]\s*",
                clean(r[mondo_col])
            )
            for raw in raw_values:
                mondo = norm_mondo(raw)
                if mondo:
                    mondo_index[mondo].add(did)

    for _, r in aliases.iterrows():
        did = clean(r[alias_disease_col])
        nm = norm_name(r[alias_name_col])
        if did and nm:
            disease_alias_index[nm].add(did)

    # ------------------------------------------------------------------
    # Drug indexes
    # ------------------------------------------------------------------
    drug_name_map = dict(
        zip(drugs["Drug_ID"], drugs[drug_name_col])
    )

    chembl_index = defaultdict(set)
    drug_name_index = defaultdict(set)

    chembl_cols = [
        c for c in [
            "ChEMBL_ID",
            "ChEMBL_ID_Alternative",
            "OpenTargets_Drug_IDs",
        ]
        if c in drugs.columns
    ]

    name_cols = [
        c for c in [
            drug_name_col,
            "OpenTargets_Name",
            "Alternative_Names_From_Legacy",
            "OpenTargets_Synonyms",
            "OpenTargets_Trade_Names",
        ]
        if c in drugs.columns
    ]

    for _, r in drugs.iterrows():
        drug_id = clean(r["Drug_ID"])

        for col in chembl_cols:
            for value in re.split(
                r"\s*[|;,]\s*",
                clean(r[col])
            ):
                value = clean(value).upper()
                if value.startswith("CHEMBL"):
                    chembl_index[value].add(drug_id)

        for col in name_cols:
            for value in re.split(
                r"\s*[|]\s*",
                clean(r[col])
            ):
                nm = norm_name(value)
                if nm:
                    drug_name_index[nm].add(drug_id)

    # ------------------------------------------------------------------
    # Load Open Targets clinical_report
    # ------------------------------------------------------------------
    table = pq.read_table(args.clinical_report_parquet)
    cr = table.to_pandas()

    print("Open Targets clinical_report rows:", len(cr))

    clinical_report_rows = []
    disease_report_rows = []
    drug_report_rows = []

    disease_unresolved_rows = []
    disease_ambiguous_rows = []
    drug_unresolved_rows = []
    drug_ambiguous_rows = []

    one_sided_rows = []

    nct_report_payloads = {}

    # ------------------------------------------------------------------
    # Process reports
    # ------------------------------------------------------------------
    for _, r in cr.iterrows():
        source_report_id = clean(r.get("id"))
        if not source_report_id:
            continue

        raw_diseases = as_list(r.get("diseases"))
        raw_drugs = as_list(r.get("drugs"))

        mapped_diseases = []
        mapped_drugs = []

        # ------------------------------
        # Map diseases
        # ------------------------------
        for d in raw_diseases:
            if not isinstance(d, dict):
                continue

            src_name = clean(d.get("diseaseFromSource"))
            src_id = clean(d.get("diseaseId"))

            candidates = set()
            methods = []

            mondo = norm_mondo(src_id)
            if mondo and mondo in mondo_index:
                candidates |= mondo_index[mondo]
                methods.append("exact_mondo_identifier")

            nn = norm_name(src_name)

            if nn and nn in disease_name_index:
                candidates |= disease_name_index[nn]
                methods.append("exact_canonical_name")

            if nn and nn in disease_alias_index:
                candidates |= disease_alias_index[nn]
                methods.append("exact_alias_name")

            if len(candidates) == 1:
                did = next(iter(candidates))
                mapped_diseases.append({
                    "DiseaseID": did,
                    "Disease_Name": disease_name_map.get(did, ""),
                    "Source_Disease_ID": src_id,
                    "Source_Disease_Name": src_name,
                    "Match_Method": " | ".join(methods),
                })

            elif len(candidates) > 1:
                disease_ambiguous_rows.append({
                    "OpenTargets_Clinical_Report_ID": source_report_id,
                    "Source_Disease_ID": src_id,
                    "Source_Disease_Name": src_name,
                    "Candidate_DiseaseIDs":
                        " | ".join(sorted(candidates)),
                    "Candidate_Disease_Names":
                        " | ".join(
                            sorted(
                                disease_name_map.get(x, x)
                                for x in candidates
                            )
                        ),
                    "Match_Methods": " | ".join(methods),
                })

            else:
                disease_unresolved_rows.append({
                    "OpenTargets_Clinical_Report_ID": source_report_id,
                    "Source_Disease_ID": src_id,
                    "Source_Disease_Name": src_name,
                })

        # De-duplicate mapped disease IDs within a report.
        md_by_id = {}
        for d in mapped_diseases:
            md_by_id.setdefault(d["DiseaseID"], d)
        mapped_diseases = list(md_by_id.values())

        # ------------------------------
        # Map drugs
        # ------------------------------
        for d in raw_drugs:
            if not isinstance(d, dict):
                continue

            src_name = clean(d.get("drugFromSource"))
            src_id = clean(d.get("drugId")).upper()

            candidates = set()
            methods = []

            if src_id and src_id in chembl_index:
                candidates |= chembl_index[src_id]
                methods.append("exact_chembl_identifier")

            nn = norm_name(src_name)
            if nn and nn in drug_name_index:
                name_hits = drug_name_index[nn]

                if len(name_hits) == 1:
                    candidates |= name_hits
                    methods.append("exact_unique_name")
                elif len(name_hits) > 1 and not candidates:
                    drug_ambiguous_rows.append({
                        "OpenTargets_Clinical_Report_ID": source_report_id,
                        "Source_Drug_ID": src_id,
                        "Source_Drug_Name": src_name,
                        "Candidate_Drug_IDs":
                            " | ".join(sorted(name_hits)),
                        "Candidate_Drug_Names":
                            " | ".join(
                                sorted(
                                    drug_name_map.get(x, x)
                                    for x in name_hits
                                )
                            ),
                        "Reason": "ambiguous_exact_name",
                    })
                    continue

            if len(candidates) == 1:
                drug_id = next(iter(candidates))
                mapped_drugs.append({
                    "Drug_ID": drug_id,
                    "Drug_Name": drug_name_map.get(drug_id, ""),
                    "Source_Drug_ID": src_id,
                    "Source_Drug_Name": src_name,
                    "Match_Method": " | ".join(methods),
                })

            elif len(candidates) > 1:
                drug_ambiguous_rows.append({
                    "OpenTargets_Clinical_Report_ID": source_report_id,
                    "Source_Drug_ID": src_id,
                    "Source_Drug_Name": src_name,
                    "Candidate_Drug_IDs":
                        " | ".join(sorted(candidates)),
                    "Candidate_Drug_Names":
                        " | ".join(
                            sorted(
                                drug_name_map.get(x, x)
                                for x in candidates
                            )
                        ),
                    "Reason": "identifier_name_conflict_or_multiple_match",
                })

            else:
                drug_unresolved_rows.append({
                    "OpenTargets_Clinical_Report_ID": source_report_id,
                    "Source_Drug_ID": src_id,
                    "Source_Drug_Name": src_name,
                })

        dd_by_id = {}
        for d in mapped_drugs:
            dd_by_id.setdefault(d["Drug_ID"], d)
        mapped_drugs = list(dd_by_id.values())

        # ------------------------------
        # Relevance
        # ------------------------------
        has_disease = len(mapped_diseases) > 0
        has_drug = len(mapped_drugs) > 0

        if not (has_disease and has_drug):
            if has_disease or has_drug:
                one_sided_rows.append({
                    "OpenTargets_Clinical_Report_ID": source_report_id,
                    "Mapped_Disease_Count": len(mapped_diseases),
                    "Mapped_Drug_Count": len(mapped_drugs),
                    "Mapped_DiseaseIDs":
                        uniq_join(x["DiseaseID"] for x in mapped_diseases),
                    "Mapped_Drug_IDs":
                        uniq_join(x["Drug_ID"] for x in mapped_drugs),
                    "Source": clean(r.get("source")),
                    "Provider": clean(r.get("provider")),
                    "Type": clean(r.get("type")),
                    "Clinical_Stage": clean(r.get("clinicalStage")),
                    "Title": clean(r.get("title")),
                })
            continue

        report_id = stable_id(
            "ODDB-CR",
            args.release,
            source_report_id,
        )

        sponsor = json_safe(r.get("trialSponsor"))
        if not isinstance(sponsor, dict):
            sponsor = {}

        nct_ids = extract_nct_ids(
            source_report_id,
            r.get("url"),
            r.get("title"),
            r.get("trialOfficialTitle"),
        )

        entity_context = (
            "single_disease_single_drug"
            if len(mapped_diseases) == 1 and len(mapped_drugs) == 1
            else "multi_entity_report_context"
        )

        clinical_report_rows.append({
            "Clinical_Report_ID": report_id,
            "OpenTargets_Clinical_Report_ID": source_report_id,
            "Clinical_Stage": clean(r.get("clinicalStage")),
            "Origin": clean(r.get("origin")),
            "Report_Type": clean(r.get("type")),
            "Source": clean(r.get("source")),
            "Provider": clean(r.get("provider")),
            "Phase_From_Source": clean(r.get("phaseFromSource")),
            "Trial_Phase": clean(r.get("trialPhase")),
            "Trial_Overall_Status": clean(r.get("trialOverallStatus")),
            "Trial_Study_Type": clean(r.get("trialStudyType")),
            "Trial_Primary_Purpose": clean(r.get("trialPrimaryPurpose")),
            "Trial_Official_Title": clean(r.get("trialOfficialTitle")),
            "Title": clean(r.get("title")),
            "Trial_Description": clean(r.get("trialDescription")),
            "Trial_Sponsor_Name": clean(sponsor.get("name")),
            "Trial_Sponsor_Agency_Class":
                clean(sponsor.get("agencyClass")),
            "Countries_JSON": json_text(r.get("countries")),
            "Trial_Literature_JSON": json_text(r.get("trialLiterature")),
            "Side_Effects_JSON": json_text(r.get("sideEffects")),
            "Quality_Controls_JSON": json_text(r.get("qualityControls")),
            "Trial_Why_Stopped": clean(r.get("trialWhyStopped")),
            "Trial_Stop_Reason_Categories_JSON":
                json_text(r.get("trialStopReasonCategories")),
            "Trial_Number_Of_Arms": clean(r.get("trialNumberOfArms")),
            "Year": clean(r.get("year")),
            "Trial_Start_Date": clean(r.get("trialStartDate")),
            "URL": clean(r.get("url")),
            "NCT_IDs": uniq_join(nct_ids),
            "Mapped_Disease_Count": len(mapped_diseases),
            "Mapped_Drug_Count": len(mapped_drugs),
            "Entity_Context": entity_context,
            "Source_Release": args.release,
            "Interpretation":
                "Source-level clinical report. Disease and drug entities "
                "are linked independently; multi-entity reports are not "
                "converted into disease-drug cross-product assertions.",
        })

        for d in mapped_diseases:
            disease_report_rows.append({
                "Disease_Clinical_Report_Association_ID":
                    stable_id(
                        "ODDB-DCR",
                        d["DiseaseID"],
                        report_id,
                    ),
                "DiseaseID": d["DiseaseID"],
                "Disease_Name": d["Disease_Name"],
                "Clinical_Report_ID": report_id,
                "OpenTargets_Clinical_Report_ID": source_report_id,
                "Source_Disease_ID": d["Source_Disease_ID"],
                "Source_Disease_Name": d["Source_Disease_Name"],
                "Match_Method": d["Match_Method"],
                "Source_Release": args.release,
            })

        for d in mapped_drugs:
            drug_report_rows.append({
                "Drug_Clinical_Report_Association_ID":
                    stable_id(
                        "ODDB-DGCR",
                        d["Drug_ID"],
                        report_id,
                    ),
                "Drug_ID": d["Drug_ID"],
                "Drug_Name": d["Drug_Name"],
                "Clinical_Report_ID": report_id,
                "OpenTargets_Clinical_Report_ID": source_report_id,
                "Source_Drug_ID": d["Source_Drug_ID"],
                "Source_Drug_Name": d["Source_Drug_Name"],
                "Match_Method": d["Match_Method"],
                "Source_Release": args.release,
            })

        if nct_ids:
            nct_report_payloads[report_id] = {
                "row": r,
                "nct_ids": nct_ids,
                "diseases": mapped_diseases,
                "drugs": mapped_drugs,
                "clinical_report_id": report_id,
                "source_report_id": source_report_id,
            }

    # ------------------------------------------------------------------
    # DataFrames
    # ------------------------------------------------------------------
    clinical_reports = pd.DataFrame(clinical_report_rows)
    disease_reports = pd.DataFrame(disease_report_rows)
    drug_reports = pd.DataFrame(drug_report_rows)

    # ------------------------------------------------------------------
    # Build ClinicalTrial subset
    # ------------------------------------------------------------------
    trial_rows = []
    disease_trial_rows = []
    drug_trial_rows = []

    for report_id, payload in nct_report_payloads.items():
        r = payload["row"]

        sponsor = json_safe(r.get("trialSponsor"))
        if not isinstance(sponsor, dict):
            sponsor = {}

        for nct_id in payload["nct_ids"]:
            trial_rows.append({
                "ClinicalTrial_ID": nct_id,
                "NCT_ID": nct_id,
                "Clinical_Report_ID": report_id,
                "OpenTargets_Clinical_Report_ID":
                    payload["source_report_id"],
                "Clinical_Stage": clean(r.get("clinicalStage")),
                "Phase_From_Source": clean(r.get("phaseFromSource")),
                "Trial_Phase": clean(r.get("trialPhase")),
                "Overall_Status": clean(r.get("trialOverallStatus")),
                "Study_Type": clean(r.get("trialStudyType")),
                "Primary_Purpose": clean(r.get("trialPrimaryPurpose")),
                "Official_Title": clean(r.get("trialOfficialTitle")),
                "Brief_Title": clean(r.get("title")),
                "Description": clean(r.get("trialDescription")),
                "Sponsor_Name": clean(sponsor.get("name")),
                "Sponsor_Agency_Class":
                    clean(sponsor.get("agencyClass")),
                "Countries_JSON": json_text(r.get("countries")),
                "Literature_JSON": json_text(r.get("trialLiterature")),
                "Why_Stopped": clean(r.get("trialWhyStopped")),
                "Stop_Reason_Categories_JSON":
                    json_text(r.get("trialStopReasonCategories")),
                "Number_Of_Arms": clean(r.get("trialNumberOfArms")),
                "Start_Date": clean(r.get("trialStartDate")),
                "Year": clean(r.get("year")),
                "URL": clean(r.get("url")),
                "Source": clean(r.get("source")),
                "Provider": clean(r.get("provider")),
                "Source_Release": args.release,
            })

            for d in payload["diseases"]:
                disease_trial_rows.append({
                    "Disease_ClinicalTrial_Association_ID":
                        stable_id(
                            "ODDB-DCT",
                            d["DiseaseID"],
                            nct_id,
                        ),
                    "DiseaseID": d["DiseaseID"],
                    "Disease_Name": d["Disease_Name"],
                    "ClinicalTrial_ID": nct_id,
                    "NCT_ID": nct_id,
                    "Clinical_Report_ID": report_id,
                    "Source_Disease_ID": d["Source_Disease_ID"],
                    "Source_Disease_Name": d["Source_Disease_Name"],
                    "Match_Method": d["Match_Method"],
                })

            for d in payload["drugs"]:
                drug_trial_rows.append({
                    "Drug_ClinicalTrial_Association_ID":
                        stable_id(
                            "ODDB-DGCT",
                            d["Drug_ID"],
                            nct_id,
                        ),
                    "Drug_ID": d["Drug_ID"],
                    "Drug_Name": d["Drug_Name"],
                    "ClinicalTrial_ID": nct_id,
                    "NCT_ID": nct_id,
                    "Clinical_Report_ID": report_id,
                    "Source_Drug_ID": d["Source_Drug_ID"],
                    "Source_Drug_Name": d["Source_Drug_Name"],
                    "Match_Method": d["Match_Method"],
                })

    trials = pd.DataFrame(trial_rows)
    disease_trials = pd.DataFrame(disease_trial_rows)
    drug_trials = pd.DataFrame(drug_trial_rows)

    # Dedupe stable relationships.
    if len(clinical_reports):
        clinical_reports = clinical_reports.drop_duplicates(
            "Clinical_Report_ID"
        )

    if len(disease_reports):
        disease_reports = disease_reports.drop_duplicates(
            "Disease_Clinical_Report_Association_ID"
        )

    if len(drug_reports):
        drug_reports = drug_reports.drop_duplicates(
            "Drug_Clinical_Report_Association_ID"
        )

    if len(trials):
        # Multiple source reports should not normally map to the same NCT,
        # but retain first deterministically and report conflicts below.
        trial_dup = trials["ClinicalTrial_ID"].duplicated(keep=False)
    else:
        trial_dup = pd.Series(dtype=bool)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    problems = []

    if len(clinical_reports) and clinical_reports[
        "Clinical_Report_ID"
    ].duplicated().any():
        problems.append("duplicate Clinical_Report_ID")

    if len(disease_reports) and disease_reports[
        "Disease_Clinical_Report_Association_ID"
    ].duplicated().any():
        problems.append(
            "duplicate Disease_Clinical_Report_Association_ID"
        )

    if len(drug_reports) and drug_reports[
        "Drug_Clinical_Report_Association_ID"
    ].duplicated().any():
        problems.append(
            "duplicate Drug_Clinical_Report_Association_ID"
        )

    trial_conflicts = pd.DataFrame()

    if len(trials) and trial_dup.any():
        trial_conflicts = trials.loc[trial_dup].copy()
        problems.append(
            "same NCT ID appears in multiple relevant clinical reports"
        )
    elif len(trials):
        trials = trials.drop_duplicates("ClinicalTrial_ID")

    valid_reports = (
        set(clinical_reports["Clinical_Report_ID"])
        if len(clinical_reports) else set()
    )

    if len(disease_reports) and (
        ~disease_reports["Clinical_Report_ID"].isin(valid_reports)
    ).any():
        problems.append("invalid disease->clinical report FK")

    if len(drug_reports) and (
        ~drug_reports["Clinical_Report_ID"].isin(valid_reports)
    ).any():
        problems.append("invalid drug->clinical report FK")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    multi_entity_count = (
        int(
            clinical_reports["Entity_Context"]
            .eq("multi_entity_report_context")
            .sum()
        )
        if len(clinical_reports) else 0
    )

    summary = pd.DataFrame([
        ["OpenTargets_clinical_report_rows_input", len(cr)],
        ["Relevant_reports_with_ODDB_disease_and_drug",
         len(clinical_reports)],
        ["Disease_Clinical_Report_links", len(disease_reports)],
        ["Drug_Clinical_Report_links", len(drug_reports)],
        ["Relevant_single_disease_single_drug_reports",
         len(clinical_reports) - multi_entity_count],
        ["Relevant_multi_entity_reports", multi_entity_count],
        ["Unique_ODDB_diseases_in_reports",
         disease_reports["DiseaseID"].nunique()
         if len(disease_reports) else 0],
        ["Unique_ODDB_drugs_in_reports",
         drug_reports["Drug_ID"].nunique()
         if len(drug_reports) else 0],
        ["ClinicalTrial_NCT_rows", len(trials)],
        ["Disease_ClinicalTrial_links", len(disease_trials)],
        ["Drug_ClinicalTrial_links", len(drug_trials)],
        ["Unique_ODDB_diseases_with_NCT_trials",
         disease_trials["DiseaseID"].nunique()
         if len(disease_trials) else 0],
        ["Unique_ODDB_drugs_with_NCT_trials",
         drug_trials["Drug_ID"].nunique()
         if len(drug_trials) else 0],
        ["Disease_mapping_ambiguous_rows",
         len(disease_ambiguous_rows)],
        ["Disease_mapping_unresolved_rows",
         len(disease_unresolved_rows)],
        ["Drug_mapping_ambiguous_rows",
         len(drug_ambiguous_rows)],
        ["Drug_mapping_unresolved_rows",
         len(drug_unresolved_rows)],
        ["One_sided_relevant_reports", len(one_sided_rows)],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    # ------------------------------------------------------------------
    # Write canonical outputs
    # ------------------------------------------------------------------
    clinical_reports.to_csv(
        args.clinical_report_output,
        sep="\t",
        index=False,
    )

    disease_reports.to_csv(
        args.disease_report_output,
        sep="\t",
        index=False,
    )

    drug_reports.to_csv(
        args.drug_report_output,
        sep="\t",
        index=False,
    )

    trials.to_csv(
        args.clinical_trial_output,
        sep="\t",
        index=False,
    )

    disease_trials.to_csv(
        args.disease_trial_output,
        sep="\t",
        index=False,
    )

    drug_trials.to_csv(
        args.drug_trial_output,
        sep="\t",
        index=False,
    )

    # ------------------------------------------------------------------
    # Review / QC outputs
    # ------------------------------------------------------------------
    pd.DataFrame(disease_ambiguous_rows).to_csv(
        report_dir / "clinical_report_disease_ambiguous.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame(disease_unresolved_rows).to_csv(
        report_dir / "clinical_report_disease_unresolved.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame(drug_ambiguous_rows).to_csv(
        report_dir / "clinical_report_drug_ambiguous.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame(drug_unresolved_rows).to_csv(
        report_dir / "clinical_report_drug_unresolved.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame(one_sided_rows).to_csv(
        report_dir / "clinical_report_one_sided_matches.tsv",
        sep="\t",
        index=False,
    )

    trial_conflicts.to_csv(
        report_dir / "clinical_trial_nct_conflicts.tsv",
        sep="\t",
        index=False,
    )

    summary.to_csv(
        report_dir / "clinical_report_trial_build_summary.tsv",
        sep="\t",
        index=False,
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        report_dir / "clinical_report_trial_build_problems.tsv",
        sep="\t",
        index=False,
    )

    print("ODDB CLINICAL REPORT / CLINICAL TRIAL LAYER BUILD")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print("\nClinical reports:", args.clinical_report_output)
    print("Disease-report links:", args.disease_report_output)
    print("Drug-report links:", args.drug_report_output)
    print("Clinical trials:", args.clinical_trial_output)
    print("Disease-trial links:", args.disease_trial_output)
    print("Drug-trial links:", args.drug_trial_output)
    print("Reports:", report_dir)

    print(
        "\nNo disease-drug cross-products were created from multi-entity "
        "clinical reports."
    )


if __name__ == "__main__":
    main()
