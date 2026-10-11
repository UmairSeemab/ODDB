#!/usr/bin/env python3
"""
Build the ODDB v1 Open Targets drug-target layer from Open Targets Platform 26.09.

Inputs
------
- canonical ODDB Gene_v1 table
- normalized legacy Drug_v1 table

Downloads (pinned Open Targets release)
--------------------------------------
- drug_mechanism_of_action
- clinical_target
- drug_molecule

Outputs
-------
1) Expanded Drug_v1
   - preserves existing ODDB Drug_ID values
   - enriches matched legacy drugs
   - adds new Open Targets/ChEMBL drugs that target ODDB genes

2) Drug_Target_Association_v1
   - molecular/pharmacological target evidence only
   - built from Open Targets drug_mechanism_of_action

3) OpenTargets_Clinical_Target_Context_v1
   - drug-target clinical context from Open Targets clinical_target
   - NOT treated as a Disease_Drug_Association

4) QC reports + source manifest

Important scientific rule
-------------------------
A Drug_Target_Association does NOT imply that the drug treats every disease
associated with the target gene.

Requires:
    pandas
    pyarrow
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import time
from collections import defaultdict
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pandas as pd
import pyarrow.parquet as pq


UA = "ODDB-v1-OpenTargets-integration/1.0"


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def clean(x):
    return str(x or "").strip()


def norm_text(x):
    x = clean(x).lower()
    x = re.sub(r"\s+", " ", x)
    return x


def split_multi(x):
    x = clean(x)
    if not x:
        return []
    return [p.strip() for p in re.split(r"\s*[|;,]\s*", x) if p.strip()]


def uniq(values):
    out, seen = [], set()
    for x in values:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def uniq_join(values):
    return " | ".join(uniq(values))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_text(url, timeout=120, retries=6):
    """Fetch directory listings with retry/backoff."""
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")

        except Exception as exc:
            last_error = exc

            if attempt == retries:
                break

            wait = min(5 * attempt, 30)

            print(
                f"Temporary network error while reading {url}\n"
                f"  attempt {attempt}/{retries}: {exc}\n"
                f"  retrying after {wait}s..."
            )

            time.sleep(wait)

    raise RuntimeError(
        f"Could not read URL after {retries} attempts: {url}\n"
        f"Last error: {last_error}"
    )


def download(url, path, timeout=900, retries=6):
    """
    Download safely with retry/backoff.

    Existing completed files are reused when the pipeline is rerun.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Reuse completed downloads
    if path.exists() and path.stat().st_size > 0:
        return

    tmp = Path(str(path) + ".part")
    last_error = None

    for attempt in range(1, retries + 1):

        try:
            if tmp.exists():
                tmp.unlink()

            req = Request(url, headers={"User-Agent": UA})

            with urlopen(req, timeout=timeout) as r, open(tmp, "wb") as out:
                shutil.copyfileobj(
                    r,
                    out,
                    length=1024 * 1024
                )

            if not tmp.exists() or tmp.stat().st_size == 0:
                raise RuntimeError("Downloaded file is empty")

            tmp.replace(path)
            return

        except Exception as exc:
            last_error = exc

            if tmp.exists():
                tmp.unlink()

            if attempt == retries:
                break

            wait = min(10 * attempt, 60)

            print(
                f"Temporary network/download error for {url}\n"
                f"  attempt {attempt}/{retries}: {exc}\n"
                f"  retrying after {wait}s..."
            )

            time.sleep(wait)

    raise RuntimeError(
        f"Could not download after {retries} attempts: {url}\n"
        f"Last error: {last_error}"
    )


def hrefs_from_listing(url):
    html = fetch_text(url)

    hrefs = []

    for m in re.finditer(
        r'href=["\']([^"\']+)["\']',
        html,
        flags=re.I
    ):
        href = unescape(m.group(1)).strip()

        if not href:
            continue

        if href in {"../", "./", "/"}:
            continue

        if href.startswith("?") or href.startswith("#"):
            continue

        hrefs.append(href)

    return hrefs


def discover_parquet_urls(dataset_url):
    """
    Inspect only the flat Open Targets dataset directory.

    Open Targets 26.09 exposes the parquet parts we need directly
    inside each dataset directory. Do NOT recursively follow links.
    """

    hrefs = hrefs_from_listing(dataset_url)

    urls = []

    for href in hrefs:

        clean_href = href.split("?", 1)[0]

        filename = (
            clean_href
            .rstrip("/")
            .split("/")[-1]
        )

        if filename.lower().endswith(".parquet"):
            urls.append(
                urljoin(dataset_url, clean_href)
            )

    urls = sorted(set(urls))

    if not urls:
        raise RuntimeError(
            "No direct parquet files found in:\n"
            f"{dataset_url}\n"
            "The Open Targets release layout may have changed."
        )

    return urls


def stable_hash(prefix, key):
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def new_drug_id(chembl_id):
    return stable_hash("ODDB-DRUG", f"CHEMBL|{clean(chembl_id).upper()}")


def target_assoc_id(drug_id, hgnc_id, action_type, mechanism):
    key = "|".join([
        clean(drug_id),
        clean(hgnc_id),
        clean(action_type).upper(),
        clean(mechanism),
    ])
    return stable_hash("ODDB-DTA", key)


def clinical_target_id(drug_id, hgnc_id, source_id):
    key = "|".join([clean(drug_id), clean(hgnc_id), clean(source_id)])
    return stable_hash("ODDB-DTC", key)


def _json_safe(value):
    """
    Convert nested pandas / NumPy / Arrow objects into ordinary
    Python objects that json.dumps() can serialize.
    """
    if value is None:
        return None

    # NumPy ndarray and similar array-like objects
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass

    # NumPy scalar values
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(k): _json_safe(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(v)
            for v in value
        ]

    # pandas / NumPy missing values
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (str, int, float, bool)):
        return value

    # Preserve unexpected values as text rather than failing
    return str(value)


def json_text(value):
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True
    )


def find_col(df, candidates, required=False):
    norm_map = {
        re.sub(r"[^a-z0-9]+", "", c.lower()): c
        for c in df.columns
    }
    for cand in candidates:
        key = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if key in norm_map:
            return norm_map[key]
    if required:
        raise SystemExit(
            f"Could not find required column among {candidates}. "
            f"Available: {list(df.columns)}"
        )
    return None


# ---------------------------------------------------------------------
# ODDB gene map
# ---------------------------------------------------------------------
def build_gene_map(gene_path):
    genes = pd.read_csv(gene_path, sep="\t", dtype=str).fillna("")

    ensembl_col = find_col(
        genes,
        ["Ensembl_ID", "Ensembl", "Ensembl_Gene_ID", "EnsemblGeneID"],
        required=True,
    )
    hgnc_col = find_col(genes, ["HGNC_ID", "HGNC ID"], required=True)
    symbol_col = find_col(
        genes, ["GeneSymbol", "Gene_Symbol", "Symbol"], required=True
    )

    ensembl_map = {}
    duplicate_ensembl = defaultdict(list)

    for _, row in genes.iterrows():
        hgnc = clean(row[hgnc_col])
        symbol = clean(row[symbol_col])

        for ens in split_multi(row[ensembl_col]):
            ens = ens.split(".", 1)[0].strip()
            if not ens.startswith("ENSG"):
                continue

            record = {"HGNC_ID": hgnc, "GeneSymbol": symbol}
            if ens in ensembl_map and ensembl_map[ens] != record:
                duplicate_ensembl[ens].append(record)
            else:
                ensembl_map[ens] = record

    if duplicate_ensembl:
        raise SystemExit(
            "Duplicate/conflicting Ensembl gene mappings detected in Gene_v1: "
            + ", ".join(sorted(duplicate_ensembl)[:20])
        )

    return genes, ensembl_map, ensembl_col


# ---------------------------------------------------------------------
# Source download / filtering
# ---------------------------------------------------------------------
def download_dataset_parts(base, dataset, raw_dir):
    url = f"{base}{dataset}/"
    urls = discover_parquet_urls(url)

    if not urls:
        raise SystemExit(f"No parquet files found under {url}")

    local_dir = Path(raw_dir) / dataset
    local_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []

    for i, src_url in enumerate(urls, 1):
        filename = src_url.split("?", 1)[0].rstrip("/").split("/")[-1]
        local = local_dir / filename
        print(f"[{dataset}] {i}/{len(urls)} {filename}")
        download(src_url, local)

        downloaded.append({
            "url": src_url,
            "path": str(local),
            "bytes": local.stat().st_size,
            "sha256": sha256_file(local),
        })

    return downloaded


def process_mechanism(files, ensembl_map):
    rows = []
    source_rows = 0
    matched_source_rows = 0

    for f in files:
        table = pq.read_table(f["path"])
        df = table.to_pandas()

        source_rows += len(df)

        for _, r in df.iterrows():
            targets = r.get("targets")
            chembls = r.get("chemblIds")

            targets = [] if targets is None else list(targets)
            chembls = [] if chembls is None else list(chembls)

            matched_targets = [
                t for t in targets if clean(t) in ensembl_map
            ]
            if not matched_targets:
                continue

            matched_source_rows += 1

            refs = r.get("references")
            if refs is None:
                refs = []
            elif hasattr(refs, "tolist"):
                refs = refs.tolist()

            mechanism = clean(r.get("mechanismOfAction"))
            action = clean(r.get("actionType"))
            target_name = clean(r.get("targetName"))
            target_type = clean(r.get("targetType"))

            source_key = hashlib.sha1(
                json_text({
                    "mechanismOfAction": mechanism,
                    "actionType": action,
                    "chemblIds": sorted(map(clean, chembls)),
                    "targets": sorted(map(clean, targets)),
                    "targetName": target_name,
                    "targetType": target_type,
                }).encode("utf-8")
            ).hexdigest()

            # The Open Targets record applies the mechanism to the listed
            # drug(s) and target(s); explode to explicit drug-target records.
            for chembl in chembls:
                chembl = clean(chembl)
                if not chembl:
                    continue

                for ens in matched_targets:
                    gm = ensembl_map[clean(ens)]

                    rows.append({
                        "OpenTargets_MOA_Record_ID": source_key,
                        "OpenTargets_Drug_ID": chembl,
                        "Ensembl_Gene_ID": clean(ens),
                        "HGNC_ID": gm["HGNC_ID"],
                        "GeneSymbol": gm["GeneSymbol"],
                        "Mechanism_of_Action": mechanism,
                        "Action_Type": action,
                        "OpenTargets_Target_Name": target_name,
                        "OpenTargets_Target_Type": target_type,
                        "Direct_Target_Interpretation":
                            "direct_single_protein"
                            if target_type.lower() == "single protein"
                            else "target_group_or_complex_context",
                        "References_JSON": json_text(refs),
                    })

    return pd.DataFrame(rows), source_rows, matched_source_rows


def process_clinical_target(files, ensembl_map):
    rows = []
    source_rows = 0

    for f in files:
        table = pq.read_table(f["path"])
        df = table.to_pandas()
        source_rows += len(df)

        for _, r in df.iterrows():
            ens = clean(r.get("targetId"))
            if ens not in ensembl_map:
                continue

            gm = ensembl_map[ens]

            diseases = r.get("diseases")
            if diseases is None:
                diseases = []
            elif hasattr(diseases, "tolist"):
                diseases = diseases.tolist()

            reports = r.get("clinicalReportIds")
            if reports is None:
                reports = []
            elif hasattr(reports, "tolist"):
                reports = reports.tolist()

            rows.append({
                "OpenTargets_Clinical_Target_ID": clean(r.get("id")),
                "OpenTargets_Drug_ID": clean(r.get("drugId")),
                "Ensembl_Gene_ID": ens,
                "HGNC_ID": gm["HGNC_ID"],
                "GeneSymbol": gm["GeneSymbol"],
                "Diseases_JSON": json_text(diseases),
                "Clinical_Report_IDs_JSON": json_text(reports),
                "Maximum_Clinical_Stage": clean(r.get("maxClinicalStage")),
            })

    return pd.DataFrame(rows), source_rows


def process_drug_molecules(files, wanted_chembl):
    rows = []
    source_rows = 0

    for f in files:
        table = pq.read_table(f["path"])
        df = table.to_pandas()
        source_rows += len(df)

        sub = df[df["id"].astype(str).isin(wanted_chembl)]

        for _, r in sub.iterrows():
            synonyms = r.get("synonyms")
            if synonyms is None:
                synonyms = []
            elif hasattr(synonyms, "tolist"):
                synonyms = synonyms.tolist()

            trades = r.get("tradeNames")
            if trades is None:
                trades = []
            elif hasattr(trades, "tolist"):
                trades = trades.tolist()

            xrefs = r.get("crossReferences")
            if xrefs is None:
                xrefs = []
            elif hasattr(xrefs, "tolist"):
                xrefs = xrefs.tolist()

            children = r.get("childChemblIds")
            if children is None:
                children = []
            elif hasattr(children, "tolist"):
                children = children.tolist()

            drugbank_ids = []
            for xr in xrefs:
                if not isinstance(xr, dict):
                    continue
                if clean(xr.get("source")).lower() == "drugbank":
                    ids = xr.get("ids") or []
                    drugbank_ids.extend(clean(x) for x in ids if clean(x))

            synonym_labels = []
            for s in synonyms:
                if isinstance(s, dict):
                    lab = clean(s.get("label"))
                    if lab:
                        synonym_labels.append(lab)

            trade_labels = []
            for s in trades:
                if isinstance(s, dict):
                    lab = clean(s.get("label"))
                    if lab:
                        trade_labels.append(lab)

            rows.append({
                "OpenTargets_Drug_ID": clean(r.get("id")),
                "Name": clean(r.get("name")),
                "InChIKey": clean(r.get("inchiKey")),
                "Canonical_SMILES": clean(r.get("canonicalSmiles")),
                "Drug_Type": clean(r.get("drugType")),
                "Parent_ID": clean(r.get("parentId")),
                "Maximum_Clinical_Stage": clean(r.get("maximumClinicalStage")),
                "Description": clean(r.get("description")),
                "DrugBank_IDs": uniq_join(drugbank_ids),
                "Synonyms": uniq_join(synonym_labels),
                "Trade_Names": uniq_join(trade_labels),
                "Child_ChEMBL_IDs": uniq_join(children),
                "Cross_References_JSON": json_text(xrefs),
            })

    out = pd.DataFrame(rows)

    if len(out):
        out = out.drop_duplicates("OpenTargets_Drug_ID")

    return out, source_rows


# ---------------------------------------------------------------------
# Reconcile Open Targets drugs to ODDB Drug master
# ---------------------------------------------------------------------
def build_existing_drug_indexes(drugs):
    idx = {
        "chembl": defaultdict(set),
        "inchikey": defaultdict(set),
        "drugbank": defaultdict(set),
        "name": defaultdict(set),
    }

    for _, r in drugs.iterrows():
        did = clean(r.get("Drug_ID"))
        if not did:
            continue

        for c in split_multi(r.get("ChEMBL_ID", "")):
            idx["chembl"][c.upper()].add(did)
        for c in split_multi(r.get("ChEMBL_ID_Alternative", "")):
            idx["chembl"][c.upper()].add(did)

        ik = clean(r.get("Standard_InChIKey", "")).upper()
        if ik:
            idx["inchikey"][ik].add(did)

        for dbid in split_multi(r.get("DrugBank_ID", "")):
            idx["drugbank"][dbid.upper()].add(did)

        names = [
            r.get("Preferred_Name", ""),
            r.get("Normalized_Name", ""),
            r.get("Alternative_Names_From_Legacy", ""),
        ]

        for value in names:
            for n in split_multi(value):
                nn = norm_text(n)
                if nn:
                    idx["name"][nn].add(did)

    return idx


def reconcile_drugs(existing_path, molecules, wanted_chembl, release):
    drugs = pd.read_csv(existing_path, sep="\t", dtype=str).fillna("")

    for col in [
        "ChEMBL_ID_Alternative",
        "OpenTargets_Drug_IDs",
        "OpenTargets_Name",
        "OpenTargets_Drug_Type",
        "OpenTargets_Parent_ID",
        "OpenTargets_Maximum_Clinical_Stage",
        "OpenTargets_Description",
        "OpenTargets_Synonyms",
        "OpenTargets_Trade_Names",
        "OpenTargets_Cross_References_JSON",
        "OpenTargets_Source_Release",
        "OpenTargets_Match_Method",
    ]:
        if col not in drugs.columns:
            drugs[col] = ""

    idx = build_existing_drug_indexes(drugs)

    molecule_map = {
        clean(r["OpenTargets_Drug_ID"]): r
        for _, r in molecules.iterrows()
    }

    chembl_to_oddb = {}
    match_rows = []
    conflict_rows = []
    new_rows = []

    existing_by_id = {
        clean(r["Drug_ID"]): i for i, r in drugs.iterrows()
    }

    for chembl in sorted(wanted_chembl):
        mol = molecule_map.get(chembl)

        if mol is None:
            # Preserve target evidence even if drug_molecule metadata is absent.
            did = new_drug_id(chembl)
            chembl_to_oddb[chembl] = did
            new_rows.append({
                "Drug_ID": did,
                "Preferred_Name": chembl,
                "Normalized_Name": norm_text(chembl),
                "Alternative_Names_From_Legacy": "",
                "Standard_InChIKey": "",
                "PubChem_CID": "",
                "DrugBank_ID": "",
                "ChEMBL_ID": chembl,
                "Drug_Entity_Type": "unknown",
                "Identity_Basis": "chembl",
                "Identifier_Curation_Status": "opentargets_chembl_only",
                "Legacy_Disease_Count": "0",
                "Legacy_Source_Row_Count": "0",
                "Source": f"Open Targets {release}",
                "ChEMBL_ID_Alternative": "",
                "OpenTargets_Drug_IDs": chembl,
                "OpenTargets_Name": "",
                "OpenTargets_Drug_Type": "",
                "OpenTargets_Parent_ID": "",
                "OpenTargets_Maximum_Clinical_Stage": "",
                "OpenTargets_Description": "",
                "OpenTargets_Synonyms": "",
                "OpenTargets_Trade_Names": "",
                "OpenTargets_Cross_References_JSON": "",
                "OpenTargets_Source_Release": release,
                "OpenTargets_Match_Method": "new_chembl_only",
            })
            match_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "ODDB_Drug_ID": did,
                "Match_Method": "new_chembl_only",
                "OpenTargets_Name": "",
            })
            continue

        candidates_by_method = {}

        # 1. ChEMBL exact
        hits = set(idx["chembl"].get(chembl.upper(), set()))
        if hits:
            candidates_by_method["chembl_exact"] = hits

        # 2. InChIKey exact
        ik = clean(mol.get("InChIKey")).upper()
        hits = set(idx["inchikey"].get(ik, set())) if ik else set()
        if hits:
            candidates_by_method["inchikey_exact"] = hits

        # 3. DrugBank exact
        db_hits = set()
        for dbid in split_multi(mol.get("DrugBank_IDs", "")):
            db_hits |= idx["drugbank"].get(dbid.upper(), set())
        if db_hits:
            candidates_by_method["drugbank_exact"] = db_hits

        # 4. Name/synonym exact
        name_hits = set()
        names = [
            mol.get("Name", ""),
            mol.get("Synonyms", ""),
            mol.get("Trade_Names", ""),
        ]
        for value in names:
            for n in split_multi(value):
                nn = norm_text(n)
                if nn:
                    name_hits |= idx["name"].get(nn, set())
        if name_hits:
            candidates_by_method["name_exact"] = name_hits

        # Use strongest available method. If high-confidence methods conflict,
        # do not merge automatically.
        priority = [
            "chembl_exact",
            "inchikey_exact",
            "drugbank_exact",
            "name_exact",
        ]

        chosen = None
        chosen_method = None

        high_conf_union = set()
        for method in ["chembl_exact", "inchikey_exact", "drugbank_exact"]:
            high_conf_union |= candidates_by_method.get(method, set())

        if len(high_conf_union) == 1:
            chosen = next(iter(high_conf_union))
            chosen_method = next(
                m for m in priority
                if chosen in candidates_by_method.get(m, set())
            )
        elif len(high_conf_union) > 1:
            conflict_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "OpenTargets_Name": clean(mol.get("Name")),
                "Conflict_Type": "high_confidence_identity_conflict",
                "Candidate_ODDB_Drug_IDs": " | ".join(sorted(high_conf_union)),
                "Candidate_Methods_JSON": json_text({
                    k: sorted(v) for k, v in candidates_by_method.items()
                }),
            })
        elif len(name_hits) == 1:
            chosen = next(iter(name_hits))
            chosen_method = "name_exact"
        elif len(name_hits) > 1:
            conflict_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "OpenTargets_Name": clean(mol.get("Name")),
                "Conflict_Type": "ambiguous_name_match",
                "Candidate_ODDB_Drug_IDs": " | ".join(sorted(name_hits)),
                "Candidate_Methods_JSON": json_text({
                    k: sorted(v) for k, v in candidates_by_method.items()
                }),
            })

        if chosen is None:
            # New Open Targets drug entity.
            did = new_drug_id(chembl)

            # Avoid accidental collision with legacy IDs.
            if did in existing_by_id:
                raise SystemExit(
                    f"New Open Targets Drug_ID collided with existing Drug_ID: {did}"
                )

            new_rows.append({
                "Drug_ID": did,
                "Preferred_Name": clean(mol.get("Name")) or chembl,
                "Normalized_Name": norm_text(
                    clean(mol.get("Name")) or chembl
                ),
                "Alternative_Names_From_Legacy": "",
                "Standard_InChIKey": clean(mol.get("InChIKey")),
                "PubChem_CID": "",
                "DrugBank_ID": clean(mol.get("DrugBank_IDs")),
                "ChEMBL_ID": chembl,
                "Drug_Entity_Type": clean(mol.get("Drug_Type")) or "unknown",
                "Identity_Basis": "chembl",
                "Identifier_Curation_Status":
                    "opentargets_chembl_verified",
                "Legacy_Disease_Count": "0",
                "Legacy_Source_Row_Count": "0",
                "Source": f"Open Targets {release} / ChEMBL",
                "ChEMBL_ID_Alternative": "",
                "OpenTargets_Drug_IDs": chembl,
                "OpenTargets_Name": clean(mol.get("Name")),
                "OpenTargets_Drug_Type": clean(mol.get("Drug_Type")),
                "OpenTargets_Parent_ID": clean(mol.get("Parent_ID")),
                "OpenTargets_Maximum_Clinical_Stage":
                    clean(mol.get("Maximum_Clinical_Stage")),
                "OpenTargets_Description": clean(mol.get("Description")),
                "OpenTargets_Synonyms": clean(mol.get("Synonyms")),
                "OpenTargets_Trade_Names": clean(mol.get("Trade_Names")),
                "OpenTargets_Cross_References_JSON":
                    clean(mol.get("Cross_References_JSON")),
                "OpenTargets_Source_Release": release,
                "OpenTargets_Match_Method": "new_chembl_entity",
            })

            chembl_to_oddb[chembl] = did
            match_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "ODDB_Drug_ID": did,
                "Match_Method": "new_chembl_entity",
                "OpenTargets_Name": clean(mol.get("Name")),
            })
            continue

        # Existing drug match: preserve ODDB ID and enrich metadata.
        chembl_to_oddb[chembl] = chosen
        row_idx = existing_by_id[chosen]

        current_chembl = split_multi(drugs.at[row_idx, "ChEMBL_ID"])
        current_alt = split_multi(drugs.at[row_idx, "ChEMBL_ID_Alternative"])

        if chembl not in current_chembl and chembl not in current_alt:
            if not current_chembl:
                drugs.at[row_idx, "ChEMBL_ID"] = chembl
            else:
                drugs.at[row_idx, "ChEMBL_ID_Alternative"] = uniq_join(
                    current_alt + [chembl]
                )

        # Fill missing identity fields only; never silently overwrite conflict.
        existing_ik = clean(drugs.at[row_idx, "Standard_InChIKey"])
        ot_ik = clean(mol.get("InChIKey"))
        if not existing_ik and ot_ik:
            drugs.at[row_idx, "Standard_InChIKey"] = ot_ik
        elif existing_ik and ot_ik and existing_ik.upper() != ot_ik.upper():
            conflict_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "OpenTargets_Name": clean(mol.get("Name")),
                "Conflict_Type": "inchikey_value_conflict_after_match",
                "Candidate_ODDB_Drug_IDs": chosen,
                "Candidate_Methods_JSON": json_text({
                    "oddb": existing_ik,
                    "opentargets": ot_ik,
                }),
            })

        existing_db = set(split_multi(drugs.at[row_idx, "DrugBank_ID"]))
        ot_db = set(split_multi(mol.get("DrugBank_IDs", "")))
        if not existing_db and ot_db:
            drugs.at[row_idx, "DrugBank_ID"] = uniq_join(sorted(ot_db))
        elif existing_db and ot_db and existing_db.isdisjoint(ot_db):
            conflict_rows.append({
                "OpenTargets_Drug_ID": chembl,
                "OpenTargets_Name": clean(mol.get("Name")),
                "Conflict_Type": "drugbank_value_conflict_after_match",
                "Candidate_ODDB_Drug_IDs": chosen,
                "Candidate_Methods_JSON": json_text({
                    "oddb": sorted(existing_db),
                    "opentargets": sorted(ot_db),
                }),
            })

        drugs.at[row_idx, "OpenTargets_Drug_IDs"] = uniq_join(
            split_multi(drugs.at[row_idx, "OpenTargets_Drug_IDs"])
            + [chembl]
        )
        drugs.at[row_idx, "OpenTargets_Name"] = clean(mol.get("Name"))
        drugs.at[row_idx, "OpenTargets_Drug_Type"] = clean(mol.get("Drug_Type"))
        drugs.at[row_idx, "OpenTargets_Parent_ID"] = clean(mol.get("Parent_ID"))
        drugs.at[row_idx, "OpenTargets_Maximum_Clinical_Stage"] = clean(
            mol.get("Maximum_Clinical_Stage")
        )
        drugs.at[row_idx, "OpenTargets_Description"] = clean(
            mol.get("Description")
        )
        drugs.at[row_idx, "OpenTargets_Synonyms"] = clean(
            mol.get("Synonyms")
        )
        drugs.at[row_idx, "OpenTargets_Trade_Names"] = clean(
            mol.get("Trade_Names")
        )
        drugs.at[row_idx, "OpenTargets_Cross_References_JSON"] = clean(
            mol.get("Cross_References_JSON")
        )
        drugs.at[row_idx, "OpenTargets_Source_Release"] = release
        drugs.at[row_idx, "OpenTargets_Match_Method"] = chosen_method

        match_rows.append({
            "OpenTargets_Drug_ID": chembl,
            "ODDB_Drug_ID": chosen,
            "Match_Method": chosen_method,
            "OpenTargets_Name": clean(mol.get("Name")),
        })

    if new_rows:
        drugs = pd.concat(
            [drugs, pd.DataFrame(new_rows)],
            ignore_index=True,
            sort=False
        ).fillna("")

    # Final Drug_ID uniqueness.
    if drugs["Drug_ID"].duplicated().any():
        raise SystemExit("Duplicate Drug_ID created during Open Targets expansion.")

    return (
        drugs,
        chembl_to_oddb,
        pd.DataFrame(match_rows),
        pd.DataFrame(
            conflict_rows,
            columns=[
                "OpenTargets_Drug_ID",
                "OpenTargets_Name",
                "Conflict_Type",
                "Candidate_ODDB_Drug_IDs",
                "Candidate_Methods_JSON",
            ]
        )
    )


# ---------------------------------------------------------------------
# Build canonical target/context tables
# ---------------------------------------------------------------------
def build_target_associations(moa, chembl_to_oddb, release):
    rows = []

    for _, r in moa.iterrows():
        chembl = clean(r["OpenTargets_Drug_ID"])
        drug_id = chembl_to_oddb.get(chembl)
        if not drug_id:
            continue

        rows.append({
            "Drug_Target_Association_ID": target_assoc_id(
                drug_id,
                r["HGNC_ID"],
                r["Action_Type"],
                r["Mechanism_of_Action"],
            ),
            "Drug_ID": drug_id,
            "OpenTargets_Drug_ID": chembl,
            "ChEMBL_ID": chembl,
            "HGNC_ID": clean(r["HGNC_ID"]),
            "GeneSymbol": clean(r["GeneSymbol"]),
            "Ensembl_Gene_ID": clean(r["Ensembl_Gene_ID"]),
            "Mechanism_of_Action": clean(r["Mechanism_of_Action"]),
            "Action_Type": clean(r["Action_Type"]),
            "Target_Name": clean(r["OpenTargets_Target_Name"]),
            "Target_Type": clean(r["OpenTargets_Target_Type"]),
            "Direct_Target_Interpretation":
                clean(r["Direct_Target_Interpretation"]),
            "Evidence_Type": "drug_mechanism_of_action",
            "References_JSON": clean(r["References_JSON"]),
            "OpenTargets_MOA_Record_ID":
                clean(r["OpenTargets_MOA_Record_ID"]),
            "Source": "Open Targets / ChEMBL",
            "Source_Release": release,
            "Curation_Note":
                "Molecular target evidence only; does not imply therapeutic "
                "efficacy for diseases associated with this gene.",
        })

    out = pd.DataFrame(rows)

    if len(out):
        # Same drug-target-mechanism/action can occur in multiple source rows.
        out = (
            out.sort_values("Drug_Target_Association_ID")
            .drop_duplicates("Drug_Target_Association_ID", keep="first")
        )

    return out


def build_clinical_context(clinical, chembl_to_oddb, release):
    rows = []

    for _, r in clinical.iterrows():
        chembl = clean(r["OpenTargets_Drug_ID"])
        drug_id = chembl_to_oddb.get(chembl)
        if not drug_id:
            continue

        rows.append({
            "Drug_Target_Clinical_Context_ID": clinical_target_id(
                drug_id,
                r["HGNC_ID"],
                r["OpenTargets_Clinical_Target_ID"],
            ),
            "Drug_ID": drug_id,
            "OpenTargets_Drug_ID": chembl,
            "HGNC_ID": clean(r["HGNC_ID"]),
            "GeneSymbol": clean(r["GeneSymbol"]),
            "Ensembl_Gene_ID": clean(r["Ensembl_Gene_ID"]),
            "OpenTargets_Clinical_Target_ID":
                clean(r["OpenTargets_Clinical_Target_ID"]),
            "Maximum_Clinical_Stage":
                clean(r["Maximum_Clinical_Stage"]),
            "Diseases_JSON": clean(r["Diseases_JSON"]),
            "Clinical_Report_IDs_JSON":
                clean(r["Clinical_Report_IDs_JSON"]),
            "Source": "Open Targets clinical_target",
            "Source_Release": release,
            "Curation_Note":
                "Clinical drug-target context. Disease associations are "
                "preserved as source context and are not automatically "
                "promoted to ODDB Disease_Drug_Association.",
        })

    out = pd.DataFrame(rows)
    if len(out):
        out = out.drop_duplicates(
            "Drug_Target_Clinical_Context_ID", keep="first"
        )

    return out


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genes", required=True)
    ap.add_argument("--drugs", required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--drug-output", required=True)
    ap.add_argument("--target-output", required=True)
    ap.add_argument("--clinical-context-output", required=True)
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--release", default="26.09")
    args = ap.parse_args()

    base = (
        f"https://ftp.ebi.ac.uk/pub/databases/opentargets/"
        f"platform/{args.release}/output/"
    )

    raw_dir = Path(args.raw_dir)
    report_dir = Path(args.report_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    _, ensembl_map, ensembl_col = build_gene_map(args.genes)
    print("ODDB genes with usable Ensembl IDs:", len(ensembl_map))
    print("Gene Ensembl column:", ensembl_col)

    # Download pinned raw datasets.
    manifests = {}
    for dataset in [
        "drug_mechanism_of_action",
        "clinical_target",
        "drug_molecule",
    ]:
        print("\nDownloading/checking:", dataset)
        manifests[dataset] = download_dataset_parts(
            base, dataset, raw_dir
        )

    # Filter MOA.
    print("\nFiltering drug_mechanism_of_action to ODDB genes...")
    moa, moa_source_rows, moa_matched_source_rows = process_mechanism(
        manifests["drug_mechanism_of_action"], ensembl_map
    )

    if moa.empty:
        raise SystemExit(
            "No Open Targets mechanism-of-action rows matched ODDB genes."
        )

    # Filter clinical_target.
    print("\nFiltering clinical_target to ODDB genes...")
    clinical, clinical_source_rows = process_clinical_target(
        manifests["clinical_target"], ensembl_map
    )

    wanted_chembl = set(moa["OpenTargets_Drug_ID"].astype(str))
    if len(clinical):
        wanted_chembl |= set(
            clinical["OpenTargets_Drug_ID"].astype(str)
        )
    wanted_chembl = {x for x in wanted_chembl if clean(x)}

    print("Unique Open Targets/ChEMBL drugs after gene filter:",
          len(wanted_chembl))

    # Extract molecule metadata.
    print("\nFiltering drug_molecule to relevant drugs...")
    molecules, molecule_source_rows = process_drug_molecules(
        manifests["drug_molecule"], wanted_chembl
    )

    # Reconcile / expand Drug master.
    print("\nReconciling Open Targets drugs with ODDB Drug_v1...")
    (
        drug_master,
        chembl_to_oddb,
        match_report,
        conflict_report
    ) = reconcile_drugs(
        args.drugs,
        molecules,
        wanted_chembl,
        args.release,
    )

    # Build canonical molecular target table.
    dta = build_target_associations(
        moa, chembl_to_oddb, args.release
    )

    # Preserve clinical target data separately.
    clinical_context = build_clinical_context(
        clinical, chembl_to_oddb, args.release
    )

    # Foreign-key checks.
    valid_drugs = set(drug_master["Drug_ID"])
    valid_hgnc = set(r["HGNC_ID"] for r in ensembl_map.values())

    problems = []

    if len(dta):
        if dta["Drug_Target_Association_ID"].duplicated().any():
            problems.append("duplicate Drug_Target_Association_ID")
        if (~dta["Drug_ID"].isin(valid_drugs)).any():
            problems.append("Drug_Target_Association invalid Drug_ID FK")
        if (~dta["HGNC_ID"].isin(valid_hgnc)).any():
            problems.append("Drug_Target_Association invalid HGNC_ID FK")

    if len(clinical_context):
        if clinical_context[
            "Drug_Target_Clinical_Context_ID"
        ].duplicated().any():
            problems.append(
                "duplicate Drug_Target_Clinical_Context_ID"
            )
        if (~clinical_context["Drug_ID"].isin(valid_drugs)).any():
            problems.append("Clinical context invalid Drug_ID FK")
        if (~clinical_context["HGNC_ID"].isin(valid_hgnc)).any():
            problems.append("Clinical context invalid HGNC_ID FK")

    # Outputs.
    for p in [
        args.drug_output,
        args.target_output,
        args.clinical_context_output,
    ]:
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    drug_master.to_csv(args.drug_output, sep="\t", index=False)
    dta.to_csv(args.target_output, sep="\t", index=False)
    clinical_context.to_csv(
        args.clinical_context_output, sep="\t", index=False
    )

    moa.to_csv(
        report_dir / "opentargets_moa_oddb_gene_staging.tsv",
        sep="\t", index=False
    )
    clinical.to_csv(
        report_dir / "opentargets_clinical_target_oddb_gene_staging.tsv",
        sep="\t", index=False
    )
    molecules.to_csv(
        report_dir / "opentargets_drug_molecule_staging.tsv",
        sep="\t", index=False
    )
    match_report.to_csv(
        report_dir / "opentargets_drug_reconciliation.tsv",
        sep="\t", index=False
    )
    conflict_report.to_csv(
        report_dir / "opentargets_drug_reconciliation_conflicts.tsv",
        sep="\t", index=False
    )

    summary = pd.DataFrame([
        ["ODDB_Ensembl_genes_input", len(ensembl_map)],
        ["OpenTargets_MOA_source_rows", moa_source_rows],
        ["OpenTargets_MOA_source_rows_matching_ODDB_genes",
         moa_matched_source_rows],
        ["Exploded_MOA_drug_target_rows", len(moa)],
        ["Canonical_Drug_Target_Association_rows", len(dta)],
        ["Unique_ODDB_genes_with_drug_targets",
         dta["HGNC_ID"].nunique() if len(dta) else 0],
        ["Unique_drugs_targeting_ODDB_genes",
         dta["Drug_ID"].nunique() if len(dta) else 0],
        ["Clinical_target_source_rows", clinical_source_rows],
        ["Clinical_target_rows_matching_ODDB_genes", len(clinical)],
        ["Clinical_target_context_rows", len(clinical_context)],
        ["Drug_molecule_source_rows", molecule_source_rows],
        ["Relevant_OpenTargets_drugs", len(wanted_chembl)],
        ["OpenTargets_drugs_with_molecule_metadata", len(molecules)],
        ["Expanded_Drug_master_rows", len(drug_master)],
        ["Matched_to_existing_ODDB_drugs",
         int((match_report["Match_Method"].isin(
             ["chembl_exact", "inchikey_exact", "drugbank_exact", "name_exact"]
         )).sum()) if len(match_report) else 0],
        ["New_OpenTargets_drugs_added",
         int((match_report["Match_Method"].isin(
             ["new_chembl_entity", "new_chembl_only"]
         )).sum()) if len(match_report) else 0],
        ["Drug_reconciliation_conflict_rows", len(conflict_report)],
        ["Validation_problem_count", len(problems)],
    ], columns=["Metric", "Value"])

    summary.to_csv(
        report_dir / "opentargets_integration_summary.tsv",
        sep="\t", index=False
    )

    pd.DataFrame({"Problem": problems}).to_csv(
        report_dir / "opentargets_integration_problems.tsv",
        sep="\t", index=False
    )

    manifest = {
        "source": "Open Targets Platform",
        "release": args.release,
        "base_url": base,
        "datasets": manifests,
        "oddb_gene_file": str(args.genes),
        "input_drug_file": str(args.drugs),
        "outputs": {
            "drug_master": str(args.drug_output),
            "drug_target_association": str(args.target_output),
            "clinical_target_context": str(args.clinical_context_output),
        },
    }

    (raw_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nODDB OPEN TARGETS 26.09 INTEGRATION")
    print(summary.to_string(index=False))

    if problems:
        print("\nVALIDATION NEEDS REVIEW:")
        for p in problems:
            print("-", p)
    else:
        print("\nVALIDATION PASSED.")

    print(f"\nExpanded Drug master: {args.drug_output}")
    print(f"Drug-target table: {args.target_output}")
    print(f"Clinical target context: {args.clinical_context_output}")
    print(f"Reports: {report_dir}")
    print(f"Raw source manifest: {raw_dir / 'source_manifest.json'}")

    print(
        "\nDrug-target records describe molecular pharmacology only; "
        "they are not automatically interpreted as disease treatments."
    )


if __name__ == "__main__":
    main()
