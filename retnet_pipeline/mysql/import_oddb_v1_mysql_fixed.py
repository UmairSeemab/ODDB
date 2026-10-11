#!/usr/bin/env python3
"""
ODDB v1 frozen-release -> MySQL importer.

Designed for:
  genetics: releases/ODDB_v1_genetics_core_2026-09-29/
  drug/clinical: releases/ODDB_v1_drug_clinical_refined_2026-09-30/

The importer:
  * discovers the frozen TSVs by filename pattern
  * normalizes only canonical columns
  * preserves every original TSV column in source_record_json
  * derives stable IDs only where a frozen table does not expose one
  * loads in FK-safe order
  * records file hashes and row counts
  * supports --truncate for a clean reproducible reload

Dependency:
  pip install pymysql
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pymysql


CURRENT_EXPECTED = {
    "disease": 162,
    "gene": 1249,
    "disease_gene_association": 1631,
    "disease_gene_association_reclassified": 1,
    "locus": 2,
    "disease_locus_association": 2,
    "variant": 707315,
    "gene_variant_association": 707315,
    "disease_variant_association": 106838,
    "drug": 805,
    "drug_form_relationship": 99,
    "drug_target_association": 1009,
    "disease_drug_association": 344,
    "disease_drug_evidence": 1142,
    "clinical_report": 1291,
    "disease_clinical_report_association": 1370,
    "drug_clinical_report_association": 1575,
    "clinical_trial": 1164,
    "disease_clinical_trial_association": 1235,
    "drug_clinical_trial_association": 1448,
    "disease_drug_aggregate_context": 157,
    "disease_drug_aggregate_context_demoted": 22,
    "disease_drug_target_overlap": 1322,
    "disease_drug_target_overlap_summary": 1203,
    "disease_drug_direct_without_target_overlap": 317,
}

TRUNCATE_ORDER = [
    "disease_drug_direct_without_target_overlap",
    "disease_drug_target_overlap_summary",
    "disease_drug_target_overlap",
    "disease_drug_aggregate_context_demoted",
    "disease_drug_aggregate_context",
    "disease_drug_evidence",
    "disease_drug_association",
    "drug_clinical_trial_association",
    "disease_clinical_trial_association",
    "clinical_trial",
    "drug_clinical_report_association",
    "disease_clinical_report_association",
    "clinical_report",
    "drug_form_relationship",
    "drug_target_association",
    "disease_variant_association",
    "gene_variant_association",
    "variant",
    "disease_locus_association",
    "locus",
    "disease_gene_association_reclassified",
    "disease_gene_association",
    "drug",
    "gene",
    "disease_alias",
    "disease",
    "oddb_import_log",
    "oddb_validation_result",
    "oddb_release",
]


def clean(v):
    if v is None:
        return ""
    return str(v).strip()


def first(row, *names, default=""):
    for name in names:
        if name in row and clean(row[name]) != "":
            return clean(row[name])
    lower = {k.lower(): k for k in row}
    for name in names:
        k = lower.get(name.lower())
        if k is not None and clean(row[k]) != "":
            return clean(row[k])
    return default


def as_int(v):
    s = clean(v).replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def as_bool(v):
    s = clean(v).lower()
    if s in {"1", "true", "yes", "y"}:
        return 1
    if s in {"0", "false", "no", "n"}:
        return 0
    return None


def stable_id(prefix, *parts):
    key = "|".join(clean(x) for x in parts)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{h}"


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_row(row):
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


def find_one(folder: Path, patterns, required=True):
    candidates = []
    for pat in patterns:
        candidates.extend(folder.glob(pat))
    candidates = sorted(set(candidates))
    if not candidates:
        if required:
            raise FileNotFoundError(
                f"No file matching {patterns} under {folder}"
            )
        return None
    if len(candidates) > 1:
        # Prefer refined/final naming if patterns were broad.
        ranked = sorted(
            candidates,
            key=lambda p: (
                "refined" not in p.name.lower(),
                "final" not in p.name.lower(),
                p.name,
            ),
        )
        return ranked[0]
    return candidates[0]


def count_tsv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        n = sum(1 for _ in f)
    return max(n - 1, 0)


def manifest_sha(release_dir: Path):
    manifests = list(release_dir.glob("*manifest*.json"))
    if not manifests:
        return None, None
    p = sorted(manifests)[0]
    return p.name, sha256_file(p)


def make_release_key(release_dir: Path):
    return release_dir.name


def insert_release(cur, release_dir: Path, release_type: str):
    manifest_name, manifest_hash = manifest_sha(release_dir)
    key = make_release_key(release_dir)
    cur.execute(
        """
        INSERT INTO oddb_release
          (release_key, release_type, release_path,
           manifest_filename, manifest_sha256, status, notes)
        VALUES (%s,%s,%s,%s,%s,'loaded',%s)
        ON DUPLICATE KEY UPDATE
          release_type=VALUES(release_type),
          release_path=VALUES(release_path),
          manifest_filename=VALUES(manifest_filename),
          manifest_sha256=VALUES(manifest_sha256),
          status='loaded'
        """,
        (
            key,
            release_type,
            str(release_dir.resolve()),
            manifest_name,
            manifest_hash,
            "Imported from immutable ODDB v1 frozen release.",
        ),
    )
    return key


def source_meta(row, source_file, release_key):
    return {
        "source_release": release_key,
        "source_file": source_file.name,
        "source_record_json": json_row(row),
    }


# ---------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------

def map_disease(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "disease_id": first(r, "DiseaseID", "Disease_ID"),
        "disease_name": first(
            r, "Disease_Name", "DiseaseName", "Preferred_Name", "Disease"
        ),
        "localization": first(r, "Localization", "Disease_Localization"),
        "mondo_id": first(r, "MONDO_ID", "Mondo_ID", "MondoID"),
        "omim_id": first(r, "OMIM_ID", "OMIM", "OMIMID"),
        "orphanet_id": first(r, "Orphanet_ID", "ORPHA_ID", "Orpha_ID"),
        "cui": first(r, "CUI", "UMLS_CUI"),
        "inheritance": first(r, "Inheritance", "Mode_of_Inheritance"),
        "curation_status": first(r, "Curation_Status", "Status"),
        "source": first(r, "Source"),
        **m,
    }


def map_disease_alias(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    alias = first(r, "Alias", "Disease_Alias", "Alias_Name", "Name")
    m = source_meta(r, sf, rel)
    return {
        "disease_alias_id": first(
            r, "Disease_Alias_ID", "Alias_ID",
            default=stable_id("ODDB-DA", disease_id, alias)
        ),
        "disease_id": disease_id,
        "alias": alias,
        "alias_type": first(r, "Alias_Type", "Type"),
        "source": first(r, "Source"),
        "source_id": first(r, "Source_ID"),
        "curation_status": first(r, "Curation_Status"),
        **m,
    }


def map_gene(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "hgnc_id": first(r, "HGNC_ID", "HGNC ID"),
        "gene_symbol": first(
            r, "Gene_Symbol", "GeneSymbol", "Approved_Symbol", "Symbol"
        ),
        "gene_name": first(r, "Gene_Name", "Approved_Name", "Name"),
        "ensembl_gene_id": first(
            r, "Ensembl_Gene_ID", "Ensembl_ID", "EnsemblGeneID"
        ),
        "ncbi_gene_id": first(
            r, "NCBI_Gene_ID", "NCBI_ID", "Entrez_ID", "Gene_ID"
        ),
        "chromosome": first(r, "Chromosome"),
        "chromosome_location": first(
            r, "Chromosome_Location", "Location", "Cytogenetic_Location"
        ),
        "gene_entity_type": first(
            r, "Genetic_Entity_Type", "Gene_Entity_Type"
        ),
        "hgnc_status": first(r, "HGNC_Status", "Status"),
        "source": first(r, "Source", default="HGNC"),
        **m,
    }


def variant_id(r):
    x = first(r, "Variant_ID", "VariantID")
    if x:
        return x
    v = first(r, "ClinVar_Variation_ID", "VariationID", "Variation_ID")
    return f"CLINVAR:{v}" if v else ""


def map_variant(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "variant_id": variant_id(r),
        "clinvar_variation_id": first(
            r, "ClinVar_Variation_ID", "VariationID", "Variation_ID"
        ),
        "variant_name": first(r, "Variant_Name", "Name"),
        "variant_type": first(r, "Variant_Type", "Type"),
        "clinical_significance": first(
            r, "Clinical_Significance", "ClinicalSignificance"
        ),
        "review_status": first(r, "Review_Status", "ReviewStatus"),
        "chromosome": first(r, "Chromosome"),
        "position_start": as_int(first(r, "Start", "Position_Start", "Start_Position")),
        "position_stop": as_int(first(r, "Stop", "Position_Stop", "End_Position")),
        "reference_allele": first(r, "ReferenceAllele", "Reference_Allele", "Ref"),
        "alternate_allele": first(r, "AlternateAllele", "Alternate_Allele", "Alt"),
        "hgvs": first(r, "HGVS", "Name"),
        "rs_id": first(r, "RS_ID", "RS# (dbSNP)", "dbSNP_ID"),
        "assembly": first(r, "Assembly"),
        "source": first(r, "Source", default="ClinVar"),
        **m,
    }


def map_dga(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    hgnc = first(r, "HGNC_ID")
    inh = first(r, "Inheritance", "Mode_of_Inheritance")
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Association_ID", "Disease_Gene_Association_ID",
            default=stable_id("ODDB-DGA", disease_id, hgnc, inh)
        ),
        "disease_id": disease_id,
        "hgnc_id": hgnc,
        "gene_symbol": first(r, "Gene_Symbol", "GeneSymbol"),
        "inheritance": inh,
        "evidence_class": first(r, "Evidence_Class"),
        "evidence_status": first(r, "Evidence_Status"),
        "source": first(r, "Source"),
        "source_id": first(r, "Source_ID"),
        "pmid": first(r, "PMID", "PubMed_ID"),
        "doi": first(r, "DOI"),
        "curation_status": first(r, "Curation_Status"),
        "curator_notes": first(r, "Curator_Notes", "Notes"),
        **m,
    }


def map_dga_reclassified(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    hgnc = first(r, "HGNC_ID", "Original_HGNC_ID")
    symbol = first(r, "Gene_Symbol", "GeneSymbol", "Original_Gene_Symbol")
    m = source_meta(r, sf, rel)
    return {
        "reclassified_id": first(
            r, "Reclassified_ID", "Association_ID",
            default=stable_id("ODDB-DGAR", disease_id, hgnc, symbol)
        ),
        "disease_id": disease_id,
        "original_hgnc_id": hgnc,
        "original_gene_symbol": symbol,
        "reclassification_type": first(
            r, "Reclassification_Type", "Classification", "Type"
        ),
        "rationale": first(r, "Rationale", "Reason", "Curator_Notes"),
        "source": first(r, "Source"),
        **m,
    }


def locus_key(r):
    return first(
        r, "Locus_ID", "Locus", "Chromosome_Location",
        "Cytogenetic_Location", "Structural_Locus"
    )


def map_locus(r, sf, rel):
    label = locus_key(r)
    m = source_meta(r, sf, rel)
    return {
        "locus_id": first(
            r, "Locus_ID",
            default=stable_id("ODDB-LOCUS", label)
        ),
        "locus_label": label,
        "chromosome_location": first(
            r, "Chromosome_Location", "Cytogenetic_Location", "Locus"
        ),
        "related_genes": first(r, "Related_Genes", "Genes"),
        "locus_type": first(r, "Locus_Type", "Type"),
        "source": first(r, "Source"),
        **m,
    }


def map_dla(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    label = locus_key(r)
    locus_id = first(
        r, "Locus_ID",
        default=stable_id("ODDB-LOCUS", label)
    )
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Association_ID", "Disease_Locus_Association_ID",
            default=stable_id("ODDB-DLA", disease_id, locus_id)
        ),
        "disease_id": disease_id,
        "locus_id": locus_id,
        "evidence_class": first(r, "Evidence_Class"),
        "evidence_status": first(r, "Evidence_Status"),
        "source": first(r, "Source"),
        "source_id": first(r, "Source_ID"),
        "pmid": first(r, "PMID"),
        "doi": first(r, "DOI"),
        "curation_status": first(r, "Curation_Status"),
        "curator_notes": first(r, "Curator_Notes", "Notes"),
        **m,
    }


def map_gva(r, sf, rel):
    hgnc = first(r, "HGNC_ID")
    vid = variant_id(r)
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Association_ID", "Gene_Variant_Association_ID",
            default=stable_id("ODDB-GVA", hgnc, vid)
        ),
        "hgnc_id": hgnc,
        "variant_id": vid,
        "gene_symbol": first(r, "Gene_Symbol", "GeneSymbol"),
        "relationship_type": first(r, "Relationship_Type", "Association_Type"),
        "source": first(r, "Source", default="ClinVar"),
        **m,
    }


def map_dva(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    vid = variant_id(r)
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Association_ID", "Disease_Variant_Association_ID",
            default=stable_id("ODDB-DVA", disease_id, vid)
        ),
        "disease_id": disease_id,
        "variant_id": vid,
        "mapping_method": first(r, "Mapping_Method", "Match_Method"),
        "evidence_class": first(r, "Evidence_Class"),
        "source": first(r, "Source", default="ClinVar"),
        "source_id": first(r, "Source_ID", "Concept_ID"),
        "curation_status": first(r, "Curation_Status"),
        **m,
    }


def map_drug(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "drug_id": first(r, "Drug_ID"),
        "preferred_name": first(r, "Preferred_Name", "Drug_Name"),
        "normalized_name": first(r, "Normalized_Name"),
        "standard_inchikey": first(r, "Standard_InChIKey", "InChIKey"),
        "pubchem_cid": first(r, "PubChem_CID"),
        "drugbank_id": first(r, "DrugBank_ID"),
        "chembl_id": first(r, "ChEMBL_ID"),
        "chembl_id_alternative": first(r, "ChEMBL_ID_Alternative"),
        "unii": first(r, "UNII"),
        "drugbank_salt_id": first(r, "DrugBank_Salt_ID"),
        "parent_drugbank_id": first(r, "Parent_DrugBank_ID"),
        "drug_entity_type": first(r, "Drug_Entity_Type"),
        "identity_basis": first(r, "Identity_Basis"),
        "identifier_curation_status": first(r, "Identifier_Curation_Status"),
        "opentargets_drug_ids": first(r, "OpenTargets_Drug_IDs"),
        "opentargets_name": first(r, "OpenTargets_Name"),
        "opentargets_drug_type": first(r, "OpenTargets_Drug_Type"),
        "opentargets_parent_id": first(r, "OpenTargets_Parent_ID"),
        "maximum_clinical_stage": first(
            r, "OpenTargets_Maximum_Clinical_Stage", "Maximum_Clinical_Stage"
        ),
        "identity_refinement_status": first(
            r, "Drug_Identity_Refinement_Status"
        ),
        "identity_refinement_notes": first(
            r, "Drug_Identity_Refinement_Notes"
        ),
        "source": first(r, "Source"),
        **m,
    }


def map_dta(r, sf, rel):
    drug_id = first(r, "Drug_ID")
    hgnc = first(r, "HGNC_ID")
    moa = first(r, "Mechanism_Of_Action", "MechanismOfAction")
    action = first(r, "Action_Type", "ActionType")
    m = source_meta(r, sf, rel)
    return {
        "drug_target_association_id": first(
            r, "Drug_Target_Association_ID", "Association_ID",
            default=stable_id("ODDB-DTA", drug_id, hgnc, moa, action)
        ),
        "drug_id": drug_id,
        "hgnc_id": hgnc,
        "gene_symbol": first(r, "Gene_Symbol", "GeneSymbol"),
        "ensembl_gene_id": first(r, "Ensembl_Gene_ID"),
        "mechanism_of_action": moa,
        "action_type": action,
        "target_name": first(r, "Target_Name"),
        "target_type": first(r, "Target_Type"),
        "source": first(r, "Source", default="Open Targets"),
        "source_id": first(r, "Source_ID", "OpenTargets_Drug_ID"),
        **m,
    }


def map_dfr(r, sf, rel):
    child = first(r, "Child_Drug_ID")
    parent = first(r, "Parent_Drug_ID")
    typ = first(r, "Relationship_Type", default="form_of")
    m = source_meta(r, sf, rel)
    return {
        "drug_form_relationship_id": first(
            r, "Drug_Form_Relationship_ID",
            default=stable_id("ODDB-DFR", child, parent, typ)
        ),
        "child_drug_id": child,
        "parent_drug_id": parent,
        "relationship_type": typ,
        "child_chembl_id": first(r, "Child_ChEMBL_ID"),
        "parent_chembl_id": first(r, "Parent_ChEMBL_ID"),
        "evidence_basis": first(r, "Evidence_Basis"),
        "source": first(r, "Source"),
        "source_id": first(r, "Source_ID"),
        "curation_status": first(r, "Curation_Status"),
        **m,
    }


def map_cr(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "clinical_report_id": first(r, "Clinical_Report_ID"),
        "opentargets_clinical_report_id": first(
            r, "OpenTargets_Clinical_Report_ID", "OpenTargets_Report_ID"
        ),
        "report_type": first(r, "Report_Type"),
        "clinical_stage": first(r, "Clinical_Stage"),
        "origin": first(r, "Origin"),
        "source": first(r, "Source"),
        "provider": first(r, "Provider"),
        "title": first(r, "Title"),
        "trial_official_title": first(r, "Trial_Official_Title"),
        "nct_ids": first(r, "NCT_IDs", "NCT_ID"),
        "trial_phase": first(r, "Trial_Phase"),
        "trial_overall_status": first(r, "Trial_Overall_Status"),
        "url": first(r, "URL", "Url"),
        **m,
    }


def map_dcr(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    report_id = first(r, "Clinical_Report_ID")
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Disease_Clinical_Report_Association_ID", "Association_ID",
            default=stable_id("ODDB-DCR", disease_id, report_id)
        ),
        "disease_id": disease_id,
        "clinical_report_id": report_id,
        "source_disease_id": first(r, "Source_Disease_ID"),
        "source_disease_name": first(r, "Source_Disease_Name"),
        "match_method": first(r, "Match_Method"),
        **m,
    }


def map_drcr(r, sf, rel):
    drug_id = first(r, "Drug_ID")
    report_id = first(r, "Clinical_Report_ID")
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Drug_Clinical_Report_Association_ID", "Association_ID",
            default=stable_id("ODDB-DRCR", drug_id, report_id)
        ),
        "drug_id": drug_id,
        "clinical_report_id": report_id,
        "drug_name": first(r, "Drug_Name"),
        "source_drug_id": first(r, "Source_Drug_ID"),
        "source_drug_name": first(r, "Source_Drug_Name"),
        "match_method": first(r, "Match_Method"),
        "identity_resolution_status": first(
            r, "Identity_Resolution_Status"
        ),
        "identity_resolution_notes": first(
            r, "Identity_Resolution_Notes"
        ),
        "original_drug_id": first(r, "Original_Drug_ID"),
        "original_drug_name": first(r, "Original_Drug_Name"),
        **m,
    }


def map_ct(r, sf, rel):
    cid = first(r, "ClinicalTrial_ID", "NCT_ID")
    nct = first(r, "NCT_ID", default=cid)
    m = source_meta(r, sf, rel)
    return {
        "clinical_trial_id": cid,
        "nct_id": nct,
        "clinical_report_id": first(r, "Clinical_Report_ID"),
        "title": first(r, "Title"),
        "official_title": first(r, "Official_Title", "Trial_Official_Title"),
        "phase": first(r, "Phase", "Trial_Phase"),
        "overall_status": first(r, "Overall_Status", "Trial_Overall_Status"),
        "study_type": first(r, "Study_Type"),
        "start_date": first(r, "Start_Date"),
        "completion_date": first(r, "Completion_Date"),
        "source": first(r, "Source", default="ClinicalTrials.gov"),
        **m,
    }


def map_dct(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    trial_id = first(r, "ClinicalTrial_ID", "NCT_ID")
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Disease_ClinicalTrial_Association_ID", "Association_ID",
            default=stable_id("ODDB-DCT", disease_id, trial_id)
        ),
        "disease_id": disease_id,
        "clinical_trial_id": trial_id,
        **m,
    }


def map_drct(r, sf, rel):
    drug_id = first(r, "Drug_ID")
    trial_id = first(r, "ClinicalTrial_ID", "NCT_ID")
    m = source_meta(r, sf, rel)
    return {
        "association_id": first(
            r, "Drug_ClinicalTrial_Association_ID", "Association_ID",
            default=stable_id("ODDB-DRCT", drug_id, trial_id)
        ),
        "drug_id": drug_id,
        "clinical_trial_id": trial_id,
        "drug_name": first(r, "Drug_Name"),
        "identity_resolution_status": first(
            r, "Identity_Resolution_Status"
        ),
        "identity_resolution_notes": first(
            r, "Identity_Resolution_Notes"
        ),
        "original_drug_id": first(r, "Original_Drug_ID"),
        "original_drug_name": first(r, "Original_Drug_Name"),
        **m,
    }


def map_dda(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    drug_id = first(r, "Drug_ID")
    m = source_meta(r, sf, rel)
    return {
        "disease_drug_association_id": first(
            r, "Disease_Drug_Association_ID", "Association_ID",
            default=stable_id("ODDB-DDA", disease_id, drug_id)
        ),
        "disease_id": disease_id,
        "drug_id": drug_id,
        "disease_name": first(r, "Disease_Name"),
        "drug_name": first(r, "Drug_Name"),
        "association_class": first(r, "Association_Class"),
        "evidence_strength_class": first(r, "Evidence_Strength_Class"),
        "has_clinical_trial_evidence": as_bool(
            first(r, "Has_Clinical_Trial_Evidence")
        ),
        "has_drug_label_evidence": as_bool(
            first(r, "Has_Drug_Label_Evidence")
        ),
        "has_regulatory_evidence": as_bool(
            first(r, "Has_Regulatory_Evidence")
        ),
        "has_curated_indication_evidence": as_bool(
            first(r, "Has_Curated_Indication_Evidence")
        ),
        **m,
    }


def map_dde(r, sf, rel):
    m = source_meta(r, sf, rel)
    return {
        "disease_drug_evidence_id": first(
            r, "Disease_Drug_Evidence_ID", "Evidence_ID"
        ),
        "disease_drug_association_id": first(
            r, "Disease_Drug_Association_ID"
        ),
        "disease_id": first(r, "DiseaseID", "Disease_ID"),
        "drug_id": first(r, "Drug_ID"),
        "evidence_subtype": first(r, "Evidence_Subtype"),
        "evidence_strength_class": first(r, "Evidence_Strength_Class"),
        "clinical_report_id": first(r, "Clinical_Report_ID") or None,
        "clinical_trial_id": first(
            r, "ClinicalTrial_ID", "NCT_ID"
        ) or None,
        "source": first(r, "Source"),
        "source_id": first(r, "Source_ID"),
        "clinical_stage": first(r, "Clinical_Stage"),
        "evidence_text": first(r, "Evidence_Text", "Evidence"),
        **m,
    }


def map_context(r, sf, rel, demoted=False):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    drug_id = first(r, "Drug_ID")
    cls = first(r, "Aggregate_Context_Class")
    prefix = "ODDB-DDACD" if demoted else "ODDB-DDAC"
    m = source_meta(r, sf, rel)
    out = {
        "aggregate_context_id": first(
            r, "Aggregate_Context_ID",
            default=stable_id(prefix, disease_id, drug_id, cls)
        ),
        "disease_id": disease_id,
        "drug_id": drug_id,
        "aggregate_context_class": cls,
        "source": first(r, "Source", default="Open Targets"),
        "source_id": first(r, "Source_ID"),
        **m,
    }
    if demoted:
        out["demotion_reason"] = first(
            r, "Demotion_Reason",
            default="aggregate_context_only_not_direct_pair_evidence"
        )
    return out


def map_overlap(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    drug_id = first(r, "Drug_ID")
    hgnc = first(r, "HGNC_ID")
    m = source_meta(r, sf, rel)
    return {
        "disease_drug_target_overlap_id": first(
            r, "Disease_Drug_Target_Overlap_ID",
            default=stable_id("ODDB-DDTO", disease_id, drug_id, hgnc)
        ),
        "disease_id": disease_id,
        "drug_id": drug_id,
        "hgnc_id": hgnc,
        "gene_symbol": first(r, "Gene_Symbol", "GeneSymbol"),
        "direct_disease_drug_evidence": as_bool(
            first(r, "Direct_Disease_Drug_Evidence")
        ) or 0,
        "action_type": first(r, "Action_Type"),
        "mechanism_of_action": first(r, "Mechanism_Of_Action"),
        **m,
    }


def map_overlap_summary(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    drug_id = first(r, "Drug_ID")
    m = source_meta(r, sf, rel)
    return {
        "summary_id": first(
            r, "Disease_Drug_Target_Summary_ID", "Summary_ID",
            default=stable_id("ODDB-DDTOS", disease_id, drug_id)
        ),
        "disease_id": disease_id,
        "drug_id": drug_id,
        "direct_disease_drug_evidence": as_bool(
            first(r, "Direct_Disease_Drug_Evidence")
        ) or 0,
        "target_gene_count": as_int(first(r, "Target_Gene_Count", "Gene_Count")),
        "target_genes": first(r, "Target_Genes", "Genes"),
        **m,
    }


def map_no_overlap(r, sf, rel):
    disease_id = first(r, "DiseaseID", "Disease_ID")
    drug_id = first(r, "Drug_ID")
    m = source_meta(r, sf, rel)
    return {
        "record_id": first(
            r, "Record_ID",
            default=stable_id("ODDB-DD-NO", disease_id, drug_id)
        ),
        "disease_id": disease_id,
        "drug_id": drug_id,
        "disease_drug_association_id": first(
            r, "Disease_Drug_Association_ID"
        ) or None,
        **m,
    }


TABLE_COLUMNS = {
    "disease": [
        "disease_id","disease_name","localization","mondo_id","omim_id",
        "orphanet_id","cui","inheritance","curation_status","source",
        "source_release","source_file","source_record_json"
    ],
    "disease_alias": [
        "disease_alias_id","disease_id","alias","alias_type","source",
        "source_id","curation_status","source_release","source_file",
        "source_record_json"
    ],
    "gene": [
        "hgnc_id","gene_symbol","gene_name","ensembl_gene_id","ncbi_gene_id",
        "chromosome","chromosome_location","gene_entity_type","hgnc_status",
        "source","source_release","source_file","source_record_json"
    ],
    "locus": [
        "locus_id","locus_label","chromosome_location","related_genes",
        "locus_type","source","source_release","source_file","source_record_json"
    ],
    "variant": [
        "variant_id","clinvar_variation_id","variant_name","variant_type",
        "clinical_significance","review_status","chromosome","position_start",
        "position_stop","reference_allele","alternate_allele","hgvs","rs_id",
        "assembly","source","source_release","source_file","source_record_json"
    ],
    "drug": [
        "drug_id","preferred_name","normalized_name","standard_inchikey",
        "pubchem_cid","drugbank_id","chembl_id","chembl_id_alternative","unii",
        "drugbank_salt_id","parent_drugbank_id","drug_entity_type",
        "identity_basis","identifier_curation_status","opentargets_drug_ids",
        "opentargets_name","opentargets_drug_type","opentargets_parent_id",
        "maximum_clinical_stage","identity_refinement_status",
        "identity_refinement_notes","source","source_release","source_file",
        "source_record_json"
    ],
    "clinical_report": [
        "clinical_report_id","opentargets_clinical_report_id","report_type",
        "clinical_stage","origin","source","provider","title",
        "trial_official_title","nct_ids","trial_phase","trial_overall_status",
        "url","source_release","source_file","source_record_json"
    ],
    "clinical_trial": [
        "clinical_trial_id","nct_id","clinical_report_id","title",
        "official_title","phase","overall_status","study_type","start_date",
        "completion_date","source","source_release","source_file",
        "source_record_json"
    ],
    "disease_gene_association": [
        "association_id","disease_id","hgnc_id","gene_symbol","inheritance",
        "evidence_class","evidence_status","source","source_id","pmid","doi",
        "curation_status","curator_notes","source_release","source_file",
        "source_record_json"
    ],
    "disease_gene_association_reclassified": [
        "reclassified_id","disease_id","original_hgnc_id",
        "original_gene_symbol","reclassification_type","rationale","source",
        "source_release","source_file","source_record_json"
    ],
    "disease_locus_association": [
        "association_id","disease_id","locus_id","evidence_class",
        "evidence_status","source","source_id","pmid","doi","curation_status",
        "curator_notes","source_release","source_file","source_record_json"
    ],
    "gene_variant_association": [
        "association_id","hgnc_id","variant_id","gene_symbol",
        "relationship_type","source","source_release","source_file",
        "source_record_json"
    ],
    "disease_variant_association": [
        "association_id","disease_id","variant_id","mapping_method",
        "evidence_class","source","source_id","curation_status",
        "source_release","source_file","source_record_json"
    ],
    "drug_target_association": [
        "drug_target_association_id","drug_id","hgnc_id","gene_symbol",
        "ensembl_gene_id","mechanism_of_action","action_type","target_name",
        "target_type","source","source_id","source_release","source_file",
        "source_record_json"
    ],
    "drug_form_relationship": [
        "drug_form_relationship_id","child_drug_id","parent_drug_id",
        "relationship_type","child_chembl_id","parent_chembl_id",
        "evidence_basis","source","source_id","curation_status",
        "source_release","source_file","source_record_json"
    ],
    "disease_clinical_report_association": [
        "association_id","disease_id","clinical_report_id","source_disease_id",
        "source_disease_name","match_method","source_release","source_file",
        "source_record_json"
    ],
    "drug_clinical_report_association": [
        "association_id","drug_id","clinical_report_id","drug_name",
        "source_drug_id","source_drug_name","match_method",
        "identity_resolution_status","identity_resolution_notes",
        "original_drug_id","original_drug_name","source_release","source_file",
        "source_record_json"
    ],
    "disease_clinical_trial_association": [
        "association_id","disease_id","clinical_trial_id","source_release",
        "source_file","source_record_json"
    ],
    "drug_clinical_trial_association": [
        "association_id","drug_id","clinical_trial_id","drug_name",
        "identity_resolution_status","identity_resolution_notes",
        "original_drug_id","original_drug_name","source_release","source_file",
        "source_record_json"
    ],
    "disease_drug_association": [
        "disease_drug_association_id","disease_id","drug_id","disease_name",
        "drug_name","association_class","evidence_strength_class",
        "has_clinical_trial_evidence","has_drug_label_evidence",
        "has_regulatory_evidence","has_curated_indication_evidence",
        "source_release","source_file","source_record_json"
    ],
    "disease_drug_evidence": [
        "disease_drug_evidence_id","disease_drug_association_id","disease_id",
        "drug_id","evidence_subtype","evidence_strength_class",
        "clinical_report_id","clinical_trial_id","source","source_id",
        "clinical_stage","evidence_text","source_release","source_file",
        "source_record_json"
    ],
    "disease_drug_aggregate_context": [
        "aggregate_context_id","disease_id","drug_id","aggregate_context_class",
        "source","source_id","source_release","source_file","source_record_json"
    ],
    "disease_drug_aggregate_context_demoted": [
        "aggregate_context_id","disease_id","drug_id","aggregate_context_class",
        "source","source_id","demotion_reason","source_release","source_file",
        "source_record_json"
    ],
    "disease_drug_target_overlap": [
        "disease_drug_target_overlap_id","disease_id","drug_id","hgnc_id",
        "gene_symbol","direct_disease_drug_evidence","action_type",
        "mechanism_of_action","source_release","source_file","source_record_json"
    ],
    "disease_drug_target_overlap_summary": [
        "summary_id","disease_id","drug_id","direct_disease_drug_evidence",
        "target_gene_count","target_genes","source_release","source_file",
        "source_record_json"
    ],
    "disease_drug_direct_without_target_overlap": [
        "record_id","disease_id","drug_id","disease_drug_association_id",
        "source_release","source_file","source_record_json"
    ],
}


def insert_rows(conn, table, rows, batch_size=2000):
    cols = TABLE_COLUMNS[table]
    placeholders = ",".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO `{table}` "
        f"({','.join('`'+c+'`' for c in cols)}) "
        f"VALUES ({placeholders})"
    )
    batch = []
    inserted = 0
    with conn.cursor() as cur:
        for mapped in rows:
            vals = [mapped.get(c) for c in cols]
            batch.append(vals)
            if len(batch) >= batch_size:
                cur.executemany(sql, batch)
                inserted += len(batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
            inserted += len(batch)
    return inserted


def iter_mapped(path, mapper, release_key):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            mapped = mapper(row, path, release_key)
            yield mapped



def import_disease_alias_file(conn, path, release_key, batch_size):
    """Resolve alias/history rows to a current disease FK without losing retired IDs."""
    started = dt.datetime.now()
    source_rows = count_tsv_rows(path)

    with conn.cursor() as cur:
        cur.execute("SELECT disease_id FROM disease")
        valid_disease_ids = {clean(r[0]) for r in cur.fetchall()}

    explicit_canonical_cols = [
        "Canonical_DiseaseID", "Canonical_Disease_ID",
        "Current_DiseaseID", "Current_Disease_ID",
        "Target_DiseaseID", "Target_Disease_ID",
        "Preferred_DiseaseID", "Preferred_Disease_ID",
        "Mapped_DiseaseID", "Mapped_Disease_ID",
    ]
    ordinary_cols = ["DiseaseID", "Disease_ID"]

    rows = []
    remaps = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row_number, row in enumerate(reader, start=2):
            alias = first(
                row, "Alias", "Disease_Alias", "Alias_Name",
                "Previous_Disease_Name", "Retired_Disease_Name", "Name"
            )
            if not alias:
                raise ValueError(
                    f"{path.name}:{row_number}: alias text is blank. "
                    f"Columns={list(row.keys())}"
                )

            original_id = first(
                row,
                "Retired_DiseaseID", "Retired_Disease_ID",
                "Original_DiseaseID", "Original_Disease_ID",
                "Old_DiseaseID", "Old_Disease_ID",
                "Previous_DiseaseID", "Previous_Disease_ID",
                "Source_DiseaseID", "Source_Disease_ID",
            )

            canonical_candidates = []
            for col in explicit_canonical_cols:
                v = first(row, col)
                if v and v in valid_disease_ids:
                    canonical_candidates.append(v)

            ordinary_value = first(row, *ordinary_cols)
            if ordinary_value and ordinary_value in valid_disease_ids:
                canonical_candidates.append(ordinary_value)

            if not canonical_candidates:
                for value in row.values():
                    s = clean(value)
                    if not s:
                        continue
                    for token in re.findall(r"ODDB-\d+", s, flags=re.I):
                        token = token.upper()
                        if token in valid_disease_ids:
                            canonical_candidates.append(token)

            canonical_candidates = sorted(set(canonical_candidates))
            if len(canonical_candidates) != 1:
                all_oddb_ids = sorted(set(
                    token.upper()
                    for value in row.values()
                    for token in re.findall(r"ODDB-\d+", clean(value), flags=re.I)
                ))
                raise ValueError(
                    f"{path.name}:{row_number}: could not resolve exactly one "
                    f"current disease_id for alias {alias!r}. "
                    f"Current candidates={canonical_candidates}; "
                    f"ODDB IDs in row={all_oddb_ids}; row={row}"
                )

            disease_id = canonical_candidates[0]
            if not original_id and ordinary_value and ordinary_value != disease_id:
                original_id = ordinary_value

            source_id = first(row, "Source_ID")
            if not source_id and original_id:
                source_id = original_id

            mapped = {
                "disease_alias_id": first(
                    row, "Disease_Alias_ID", "Alias_ID",
                    default=stable_id("ODDB-DA", disease_id, alias, original_id)
                ),
                "disease_id": disease_id,
                "alias": alias,
                "alias_type": first(row, "Alias_Type", "Type", "Relationship_Type"),
                "source": first(row, "Source"),
                "source_id": source_id,
                "curation_status": first(row, "Curation_Status"),
                **source_meta(row, path, release_key),
            }
            rows.append(mapped)

            if original_id and original_id != disease_id:
                remaps.append((original_id, disease_id, alias))
            elif ordinary_value and ordinary_value != disease_id:
                remaps.append((ordinary_value, disease_id, alias))

    inserted = insert_rows(conn, "disease_alias", iter(rows), batch_size)
    finished = dt.datetime.now()
    file_hash = sha256_file(path)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO oddb_import_log
              (release_key, table_name, source_file, source_rows,
               inserted_rows, file_sha256, started_at, finished_at,
               status, message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                release_key, "disease_alias", path.name, source_rows, inserted,
                file_hash, started, finished,
                "ok" if source_rows == inserted else "warning",
                f"canonical_alias_remaps={len(remaps)}",
            ),
        )
    conn.commit()

    print(
        f"[OK] disease_alias: {inserted:,} rows <- {path.name} "
        f"(canonical remaps: {len(remaps)})"
    )
    for old_id, new_id, alias in remaps:
        print(f"     alias remap: {old_id} -> {new_id} | {alias}")
    return inserted


def import_file(conn, table, path, mapper, release_key, batch_size):
    started = dt.datetime.now()
    source_rows = count_tsv_rows(path)
    inserted = insert_rows(
        conn, table, iter_mapped(path, mapper, release_key), batch_size
    )
    finished = dt.datetime.now()
    file_hash = sha256_file(path)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO oddb_import_log
              (release_key, table_name, source_file, source_rows,
               inserted_rows, file_sha256, started_at, finished_at,
               status, message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                release_key, table, path.name, source_rows, inserted,
                file_hash, started, finished,
                "ok" if source_rows == inserted else "warning",
                None if source_rows == inserted
                else f"source_rows={source_rows}; inserted_rows={inserted}",
            ),
        )
    conn.commit()
    print(f"[OK] {table}: {inserted:,} rows <- {path.name}")
    return inserted


def discover(genetics, drug):
    g = genetics
    d = drug
    return {
        "disease": (find_one(g, ["Disease_v1_final_*.tsv"]), map_disease, "genetics"),
        "disease_alias": (
            find_one(g, ["Disease_Alias_v1_final_*.tsv"], required=False),
            map_disease_alias, "genetics"
        ),
        "gene": (find_one(g, ["Gene_v1_*.tsv"]), map_gene, "genetics"),
        "disease_gene_association": (
            find_one(g, ["Disease_Gene_Association_v1_final_*.tsv"]),
            map_dga, "genetics"
        ),
        "disease_gene_association_reclassified": (
            find_one(
                g, ["Disease_Gene_Association_reclassified_v1_*.tsv"],
                required=False
            ),
            map_dga_reclassified, "genetics"
        ),
        "disease_locus_association": (
            find_one(g, ["Disease_Locus_Association_v1_*.tsv"], required=False),
            map_dla, "genetics"
        ),
        "variant": (find_one(g, ["Variant_v1_*.tsv"]), map_variant, "genetics"),
        "gene_variant_association": (
            find_one(g, ["Gene_Variant_Association_v1_*.tsv"]),
            map_gva, "genetics"
        ),
        "disease_variant_association": (
            find_one(g, ["Disease_Variant_Association_v1_final_*.tsv"]),
            map_dva, "genetics"
        ),

        "drug": (
            find_one(d, ["Drug_v1_refined_*.tsv"]),
            map_drug, "drug"
        ),
        "drug_target_association": (
            find_one(d, ["Drug_Target_Association_v1_*.tsv"]),
            map_dta, "drug"
        ),
        "drug_form_relationship": (
            find_one(d, ["Drug_Form_Relationship_v1_refined_*.tsv"]),
            map_dfr, "drug"
        ),
        "clinical_report": (
            find_one(d, ["Clinical_Report_v1_*.tsv"]),
            map_cr, "drug"
        ),
        "disease_clinical_report_association": (
            find_one(d, ["Disease_Clinical_Report_Association_v1_*.tsv"]),
            map_dcr, "drug"
        ),
        "drug_clinical_report_association": (
            find_one(d, ["Drug_Clinical_Report_Association_v1_refined_*.tsv"]),
            map_drcr, "drug"
        ),
        "clinical_trial": (
            find_one(d, ["ClinicalTrial_v1_*.tsv"]),
            map_ct, "drug"
        ),
        "disease_clinical_trial_association": (
            find_one(d, ["Disease_ClinicalTrial_Association_v1_*.tsv"]),
            map_dct, "drug"
        ),
        "drug_clinical_trial_association": (
            find_one(d, ["Drug_ClinicalTrial_Association_v1_refined_*.tsv"]),
            map_drct, "drug"
        ),
        "disease_drug_association": (
            find_one(d, ["Disease_Drug_Association_v1_refined_*.tsv"]),
            map_dda, "drug"
        ),
        "disease_drug_evidence": (
            find_one(d, ["Disease_Drug_Evidence_v1_refined_*.tsv"]),
            map_dde, "drug"
        ),
        "disease_drug_aggregate_context": (
            find_one(
                d,
                ["Disease_Drug_Aggregate_Clinical_Context_v1_refined_*.tsv"]
            ),
            lambda r, sf, rel: map_context(r, sf, rel, False), "drug"
        ),
        "disease_drug_aggregate_context_demoted": (
            find_one(
                d,
                ["Disease_Drug_Aggregate_Context_Demoted_v1_refined_*.tsv"]
            ),
            lambda r, sf, rel: map_context(r, sf, rel, True), "drug"
        ),
        "disease_drug_target_overlap": (
            find_one(d, ["Disease_Drug_Target_Overlap_v1_refined_*.tsv"]),
            map_overlap, "drug"
        ),
        "disease_drug_target_overlap_summary": (
            find_one(
                d, ["Disease_Drug_Target_Overlap_Summary_v1_refined_*.tsv"]
            ),
            map_overlap_summary, "drug"
        ),
        "disease_drug_direct_without_target_overlap": (
            find_one(
                d,
                ["Disease_Drug_Direct_Evidence_Without_Target_Overlap_v1_refined_*.tsv"]
            ),
            map_no_overlap, "drug"
        ),
    }


IMPORT_ORDER = [
    "disease",
    "disease_alias",
    "gene",
    "disease_gene_association",
    "disease_gene_association_reclassified",
    "locus",
    "disease_locus_association",
    "variant",
    "gene_variant_association",
    "disease_variant_association",
    "drug",
    "drug_target_association",
    "drug_form_relationship",
    "clinical_report",
    "disease_clinical_report_association",
    "drug_clinical_report_association",
    "clinical_trial",
    "disease_clinical_trial_association",
    "drug_clinical_trial_association",
    "disease_drug_association",
    "disease_drug_evidence",
    "disease_drug_aggregate_context",
    "disease_drug_aggregate_context_demoted",
    "disease_drug_target_overlap",
    "disease_drug_target_overlap_summary",
    "disease_drug_direct_without_target_overlap",
]


def import_loci_derived(conn, path, release_key, batch_size):
    # Build unique locus rows from the Disease_Locus_Association source.
    seen = set()
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            x = map_locus(r, path, release_key)
            if x["locus_id"] in seen:
                continue
            seen.add(x["locus_id"])
            rows.append(x)
    inserted = insert_rows(conn, "locus", rows, batch_size)
    conn.commit()
    print(f"[OK] locus: {inserted:,} derived rows <- {path.name}")
    return inserted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    ap.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "oddb_v1"))
    ap.add_argument("--genetics-release", required=True)
    ap.add_argument("--drug-release", required=True)
    ap.add_argument("--truncate", action="store_true")
    ap.add_argument("--strict-current-counts", action="store_true")
    ap.add_argument("--batch-size", type=int, default=2000)
    args = ap.parse_args()

    genetics = Path(args.genetics_release).resolve()
    drugrel = Path(args.drug_release).resolve()

    if not genetics.is_dir():
        raise SystemExit(f"Genetics release not found: {genetics}")
    if not drugrel.is_dir():
        raise SystemExit(f"Drug release not found: {drugrel}")

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
        local_infile=True,
    )

    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")

        if args.truncate:
            with conn.cursor() as cur:
                cur.execute("SET FOREIGN_KEY_CHECKS=0")
                for table in TRUNCATE_ORDER:
                    cur.execute(f"TRUNCATE TABLE `{table}`")
                cur.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
            print("[OK] Existing ODDB v1 tables truncated.")

        with conn.cursor() as cur:
            genetics_key = insert_release(cur, genetics, "genetics_core")
            drug_key = insert_release(cur, drugrel, "drug_clinical_refined")
        conn.commit()

        discovered = discover(genetics, drugrel)

        # locus is derived from disease_locus_association if present
        dla_info = discovered.get("disease_locus_association")

        loaded_counts = {}

        for table in IMPORT_ORDER:
            if table == "locus":
                if dla_info and dla_info[0] is not None:
                    loaded_counts["locus"] = import_loci_derived(
                        conn, dla_info[0], genetics_key, args.batch_size
                    )
                continue

            path, mapper, which = discovered[table]
            if path is None:
                print(f"[SKIP] {table}: no frozen source file")
                continue

            release_key = genetics_key if which == "genetics" else drug_key

            if table == "disease_alias":
                loaded_counts[table] = import_disease_alias_file(
                    conn, path, release_key, args.batch_size
                )
                continue

            loaded_counts[table] = import_file(
                conn, table, path, mapper, release_key, args.batch_size
            )

        if args.strict_current_counts:
            mismatches = []
            with conn.cursor() as cur:
                for table, expected in CURRENT_EXPECTED.items():
                    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                    actual = int(cur.fetchone()[0])
                    if actual != expected:
                        mismatches.append((table, expected, actual))
            if mismatches:
                print("\nSTRICT COUNT CHECK FAILED:")
                for table, expected, actual in mismatches:
                    print(f"  {table}: expected {expected:,}; got {actual:,}")
                raise SystemExit(2)

        print("\nIMPORT COMPLETED SUCCESSFULLY.")
        print(f"Database: {args.database}")
        print(f"Genetics release: {genetics_key}")
        print(f"Drug/clinical release: {drug_key}")
        if args.strict_current_counts:
            print("Current-release row-count check: PASSED")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
