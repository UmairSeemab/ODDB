#!/usr/bin/env python3
from pathlib import Path
import json
import re
import sys

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
RELEASES_ROOT = PROJECT_ROOT / "retnet_pipeline" / "releases"
CONFIG_DIR = APP_ROOT / "config"
OUT = CONFIG_DIR / "release_catalog.json"

RELEASES = [
    {
        "dir": "ODDB_v1_genetics_core_2026-09-29",
        "group": "genetics",
        "release_name": "ODDB v1 genetics core",
        "release_date": "2026-09-29",
    },
    {
        "dir": "ODDB_v1_drug_clinical_refined_2026-09-30",
        "group": "clinical",
        "release_name": "ODDB v1 drug & clinical refined",
        "release_date": "2026-09-30",
    },
]

COUNTS = {
    "disease": 162,
    "gene": 1249,
    "disease_gene_association": 1631,
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
}

META = {
    "disease": ("Disease", "Canonical ocular disease entities."),
    "gene": ("Gene", "Canonical HGNC-aligned gene entities."),
    "disease_gene_association": ("Disease–Gene Association", "Canonical disease–gene associations."),
    "locus": ("Locus", "Structural/non-gene loci retained separately from genes."),
    "disease_locus_association": ("Disease–Locus Association", "Disease associations to structural/non-gene loci."),
    "variant": ("Variant", "Canonical variant entities."),
    "gene_variant_association": ("Gene–Variant Association", "Canonical gene–variant relationships."),
    "disease_variant_association": ("Disease–Variant Association", "Curated disease–variant relationships; not inferred solely from gene membership."),
    "drug": ("Drug", "Canonical drug entities with source-derived development-stage fields."),
    "drug_form_relationship": ("Drug Form Relationship", "Explicit relationships between parent drugs and salts/forms."),
    "drug_target_association": ("Drug–Target Association", "Molecular drug–target pharmacology relationships."),
    "disease_drug_association": ("Disease–Drug Association", "Direct disease-specific therapeutic evidence relationships."),
    "disease_drug_evidence": ("Disease–Drug Evidence", "Evidence records supporting disease–drug relationships."),
    "clinical_report": ("Clinical Report", "Canonical clinical evidence report entities."),
    "disease_clinical_report_association": ("Disease–Clinical Report Association", "Many-to-many disease links to clinical reports."),
    "drug_clinical_report_association": ("Drug–Clinical Report Association", "Many-to-many drug links to clinical reports."),
    "clinical_trial": ("Clinical Trial", "Canonical clinical trial entities."),
    "disease_clinical_trial_association": ("Disease–Clinical Trial Association", "Many-to-many disease links to clinical trials."),
    "drug_clinical_trial_association": ("Drug–Clinical Trial Association", "Many-to-many drug links to clinical trials."),
}

ALIASES = [
    ("disease_clinical_report_association", ["diseaseclinicalreportassociation","diseaseclinicalreport","diseaseclinical_reportassociation"]),
    ("drug_clinical_report_association", ["drugclinicalreportassociation","drugclinicalreport","drugclinical_reportassociation"]),
    ("disease_clinical_trial_association", ["diseaseclinicaltrialassociation","diseaseclinicaltrial","diseaseclinical_trialassociation"]),
    ("drug_clinical_trial_association", ["drugclinicaltrialassociation","drugclinicaltrial","drugclinical_trialassociation"]),
    ("disease_variant_association", ["diseasevariantassociation"]),
    ("gene_variant_association", ["genevariantassociation"]),
    ("disease_gene_association", ["diseasegeneassociation"]),
    ("disease_locus_association", ["diseaselocusassociation"]),
    ("drug_form_relationship", ["drugformrelationship"]),
    ("drug_target_association", ["drugtargetassociation"]),
    ("disease_drug_association", ["diseasedrugassociation"]),
    ("disease_drug_evidence", ["diseasedrugevidence"]),
    ("clinical_report", ["clinicalreport"]),
    ("clinical_trial", ["clinicaltrial"]),
    ("variant", ["variant"]),
    ("locus", ["locus"]),
    ("disease", ["disease"]),
    ("gene", ["gene"]),
    ("drug", ["drug"]),
]

ALLOWED_SUFFIXES = {".tsv", ".csv", ".json", ".xlsx", ".xls"}

def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())

def detect_table(path: Path):
    n = normalize(path.stem)
    for table, aliases in ALIASES:
        for alias in aliases:
            if alias in n:
                return table
    return None

def label_for(path: Path, table):
    if table in META:
        return META[table][0]
    stem = re.sub(r"[_-]+", " ", path.stem).strip()
    return stem[:1].upper() + stem[1:] if stem else path.name

def description_for(table):
    return META.get(table, ("", "Frozen ODDB v1 release file."))[1]

def format_for(path: Path):
    return path.suffix.lower().lstrip(".") or "file"

def safe_id(group: str, release_dir: str, filename: str):
    base = f"{group}-{release_dir}-{filename}".lower()
    base = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-")
    return base[:180]

def collect():
    files = []

    for spec in RELEASES:
        release_dir = RELEASES_ROOT / spec["dir"]
        if not release_dir.is_dir():
            print(f"WARNING: release directory not found: {release_dir}", file=sys.stderr)
            continue

        # Frozen releases may contain subdirectories. Recursively catalogue
        # supported release files while keeping the release directories immutable.
        for path in sorted(p for p in release_dir.rglob("*") if p.is_file()):
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if any(part.startswith(".") for part in path.relative_to(release_dir).parts):
                continue

            table = detect_table(path)
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            release_rel = path.relative_to(release_dir).as_posix()

            files.append({
                "id": safe_id(spec["group"], spec["dir"], release_rel),
                "group": spec["group"],
                "release_name": spec["release_name"],
                "release_date": spec["release_date"],
                "filename": path.name,
                "relative_path": rel,
                "format": format_for(path),
                "size_bytes": path.stat().st_size,
                "db_table": table,
                "row_count": COUNTS.get(table) if table else None,
                "label": label_for(path, table),
                "description": description_for(table),
            })

    files.sort(key=lambda x: (x["group"], x["label"].lower(), x["filename"].lower()))
    return files

def main():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    files = collect()

    payload = {
        "release": {
            "name": "ODDB v1",
            "genetics_core": "2026-09-29",
            "drug_clinical_refined": "2026-09-30",
            "frozen_release_policy": True,
        },
        "counts": {
            "disease": 162,
            "gene": 1249,
            "variant": 707315,
            "drug": 805,
            "clinical_trial": 1164,
            "clinical_report": 1291,
        },
        "files": files,
    }

    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("ODDB release catalog rebuilt.")
    print("Catalog:", OUT.relative_to(APP_ROOT))
    print("Files:", len(files))
    for f in files:
        print(f" - [{f['group']}] {f['filename']}")

if __name__ == "__main__":
    main()
