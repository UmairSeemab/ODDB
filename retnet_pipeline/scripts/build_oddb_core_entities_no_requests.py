#!/usr/bin/env python3
import argparse
import io
import re
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

HGNC_CURRENT_TSV = (
    "https://storage.googleapis.com/public-download-files/"
    "hgnc/tsv/tsv/hgnc_complete_set.txt"
)

def clean(x):
    return str(x or "").strip()

def norm_col(x):
    return re.sub(r"[^a-z0-9]+", "", str(x).lower())

def find_col(columns, candidates):
    lookup = {norm_col(c): c for c in columns}
    for cand in candidates:
        key = norm_col(cand)
        if key in lookup:
            return lookup[key]
    return None

def first_nonempty(series):
    for x in series:
        x = clean(x)
        if x:
            return x
    return ""

def unique_join(series, sep=" | "):
    vals, seen = [], set()
    for x in series:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            vals.append(x)
    return sep.join(vals)

def safe_hgnc_field(df, field):
    if field in df.columns:
        return df[field].fillna("").astype(str)
    return pd.Series([""] * len(df), index=df.index, dtype=str)

def download_text(url):
    req = Request(
        url,
        headers={"User-Agent": "ODDB-v1-HGNC-builder/1.0"}
    )
    with urlopen(req, timeout=120) as response:
        return response.read().decode("utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oddb", required=True)
    ap.add_argument("--associations", required=True)
    ap.add_argument("--gene-output", required=True)
    ap.add_argument("--disease-output", required=True)
    ap.add_argument("--report-output", required=True)
    ap.add_argument("--hgnc-cache", required=False)
    ap.add_argument("--hgnc-url", default=HGNC_CURRENT_TSV)
    args = ap.parse_args()

    oddb = pd.read_csv(args.oddb, sep="\t", dtype=str).fillna("")
    assoc = pd.read_csv(args.associations, sep="\t", dtype=str).fillna("")

    # ---------------- Disease master ----------------
    disease_id_col = find_col(
        oddb.columns, ["DiseaseID", "Disease_ID", "ODDB_DiseaseID"]
    )
    disease_name_col = find_col(
        oddb.columns, ["Ocular.disease", "Disease", "Disease_Name", "Ocular Disease"]
    )

    if disease_id_col is None or disease_name_col is None:
        raise SystemExit(
            "Could not identify DiseaseID and disease-name columns in cleaned ODDB file."
        )

    optional_disease_columns = {
        "Localization_Category": [
            "Localization_Category", "Disease.category", "Disease_Category",
            "Category", "Localization", "Anatomical_Localization",
            "Anatomical.Localization", "Eye_Location"
        ],
        "Disease_Description": [
            "Disease_Description", "Disease.Description", "Description",
            "DiseaseDescription"
        ],
        "Synonyms": [
            "Synonyms", "Disease_Synonyms", "Disease.Synonyms", "Aliases"
        ],
        "OMIM_ID": ["OMIM_ID", "OMIM", "OMIM.ID", "OMIM_Number"],
        "Orphanet_ID": ["Orphanet_ID", "Orphanet", "ORPHA", "ORPHA_ID"],
        "MONDO_ID": ["MONDO_ID", "MONDO", "Mondo_ID"],
    }

    resolved_optional = {
        out: find_col(oddb.columns, candidates)
        for out, candidates in optional_disease_columns.items()
    }

    disease_rows = []
    for disease_id, g in oddb.groupby(disease_id_col, dropna=False):
        disease_id = clean(disease_id)
        if not disease_id:
            continue

        names = [clean(x) for x in g[disease_name_col] if clean(x)]
        canonical_name = names[0] if names else ""
        unique_names = list(dict.fromkeys(names))

        row = {
            "DiseaseID": disease_id,
            "Disease_Name": canonical_name,
            "Disease_Name_Conflict": "Yes" if len(unique_names) > 1 else "No",
            "Alternative_Disease_Names_From_Legacy":
                " | ".join(unique_names[1:]) if len(unique_names) > 1 else "",
        }

        for out_name, source_col in resolved_optional.items():
            if source_col:
                row[out_name] = (
                    unique_join(g[source_col])
                    if out_name == "Synonyms"
                    else first_nonempty(g[source_col])
                )
            else:
                row[out_name] = ""

        disease_rows.append(row)

    disease = pd.DataFrame(disease_rows)

    assoc_gene_counts = (
        assoc.groupby("DiseaseID")
        .agg(
            Gene_Association_Count=("Association_ID", "nunique"),
            Unique_Gene_Count=("HGNC_ID", "nunique")
        )
        .reset_index()
    )

    disease = disease.merge(assoc_gene_counts, how="left", on="DiseaseID")
    disease["Gene_Association_Count"] = disease["Gene_Association_Count"].fillna(0).astype(int)
    disease["Unique_Gene_Count"] = disease["Unique_Gene_Count"].fillna(0).astype(int)
    disease["Has_Gene_Association"] = disease["Gene_Association_Count"].map(
        lambda x: "Yes" if x > 0 else "No"
    )
    disease["Source_Status"] = "ODDB legacy disease entity"

    disease = disease[
        [
            "DiseaseID",
            "Disease_Name",
            "Disease_Name_Conflict",
            "Alternative_Disease_Names_From_Legacy",
            "Localization_Category",
            "Disease_Description",
            "Synonyms",
            "OMIM_ID",
            "Orphanet_ID",
            "MONDO_ID",
            "Has_Gene_Association",
            "Gene_Association_Count",
            "Unique_Gene_Count",
            "Source_Status",
        ]
    ].sort_values(["DiseaseID"])

    # ---------------- HGNC current data ----------------
    if args.hgnc_cache and Path(args.hgnc_cache).exists():
        print(f"Reading cached HGNC complete set: {args.hgnc_cache}")
        hgnc = pd.read_csv(args.hgnc_cache, sep="\t", dtype=str).fillna("")
    else:
        print("Downloading current HGNC complete set...")
        hgnc_text = download_text(args.hgnc_url)
        hgnc = pd.read_csv(io.StringIO(hgnc_text), sep="\t", dtype=str).fillna("")
        if args.hgnc_cache:
            Path(args.hgnc_cache).parent.mkdir(parents=True, exist_ok=True)
            Path(args.hgnc_cache).write_text(hgnc_text, encoding="utf-8")
            print(f"HGNC cache written: {args.hgnc_cache}")

    if "hgnc_id" not in hgnc.columns:
        raise SystemExit("Downloaded HGNC file does not contain hgnc_id.")

    hgnc = hgnc.drop_duplicates("hgnc_id", keep="first").copy()

    # ---------------- Gene master ----------------
    counts = (
        assoc.groupby(["HGNC_ID", "GeneSymbol"])
        .agg(
            Disease_Association_Count=("DiseaseID", "nunique"),
            Association_Count=("Association_ID", "nunique")
        )
        .reset_index()
    )

    origins = (
        assoc.groupby("HGNC_ID")["Association_Origin"]
        .apply(unique_join)
        .reset_index(name="Association_Origins")
    )

    gene = counts.merge(origins, how="left", on="HGNC_ID")

    hg_fields = [
        "hgnc_id", "symbol", "name", "status", "locus_group", "locus_type",
        "location", "alias_symbol", "prev_symbol", "gene_group", "entrez_id",
        "ensembl_gene_id", "refseq_accession", "uniprot_ids", "omim_id",
        "date_approved_reserved", "date_symbol_changed", "date_name_changed",
        "date_modified",
    ]

    hsub = pd.DataFrame(index=hgnc.index)
    for field in hg_fields:
        hsub[field] = safe_hgnc_field(hgnc, field)

    gene = gene.merge(
        hsub, how="left", left_on="HGNC_ID", right_on="hgnc_id"
    )

    gene["HGNC_Record_Found"] = gene["hgnc_id"].map(
        lambda x: "Yes" if clean(x) else "No"
    )
    gene["GeneSymbol_Legacy_Association"] = gene["GeneSymbol"]
    gene["GeneSymbol"] = [
        clean(hg) if clean(hg) else clean(old)
        for hg, old in zip(gene["symbol"], gene["GeneSymbol"])
    ]

    gene["Gene_Name"] = gene["name"].map(clean)
    gene["HGNC_Status"] = gene["status"].map(clean)
    gene["Locus_Group"] = gene["locus_group"].map(clean)
    gene["Locus_Type"] = gene["locus_type"].map(clean)
    gene["Chromosomal_Location"] = gene["location"].map(clean)
    gene["Aliases"] = gene["alias_symbol"].map(clean)
    gene["Previous_Symbols"] = gene["prev_symbol"].map(clean)
    gene["Gene_Groups"] = gene["gene_group"].map(clean)
    gene["NCBI_Gene_ID"] = gene["entrez_id"].map(clean)
    gene["Ensembl_Gene_ID"] = gene["ensembl_gene_id"].map(clean)
    gene["RefSeq_Accession"] = gene["refseq_accession"].map(clean)
    gene["UniProt_IDs"] = gene["uniprot_ids"].map(clean)
    gene["OMIM_IDs"] = gene["omim_id"].map(clean)
    gene["HGNC_Date_Approved"] = gene["date_approved_reserved"].map(clean)
    gene["HGNC_Date_Symbol_Changed"] = gene["date_symbol_changed"].map(clean)
    gene["HGNC_Date_Name_Changed"] = gene["date_name_changed"].map(clean)
    gene["HGNC_Date_Modified"] = gene["date_modified"].map(clean)

    gene["Introduced_By_Verified_RetNet"] = gene["Association_Origins"].map(
        lambda x: "Yes" if clean(x) == "verified_retnet_discovery" else "No"
    )

    gene = gene[
        [
            "HGNC_ID", "GeneSymbol", "Gene_Name", "HGNC_Status",
            "Locus_Group", "Locus_Type", "Chromosomal_Location",
            "Aliases", "Previous_Symbols", "Gene_Groups",
            "NCBI_Gene_ID", "Ensembl_Gene_ID", "RefSeq_Accession",
            "UniProt_IDs", "OMIM_IDs",
            "Disease_Association_Count", "Association_Count",
            "Association_Origins", "Introduced_By_Verified_RetNet",
            "HGNC_Record_Found", "HGNC_Date_Approved",
            "HGNC_Date_Symbol_Changed", "HGNC_Date_Name_Changed",
            "HGNC_Date_Modified", "GeneSymbol_Legacy_Association",
        ]
    ].sort_values(["GeneSymbol", "HGNC_ID"])

    # ---------------- Validation/report ----------------
    gene_ids = set(gene["HGNC_ID"].map(clean))
    assoc_gene_ids = set(assoc["HGNC_ID"].map(clean))
    disease_ids = set(disease["DiseaseID"].map(clean))
    assoc_disease_ids = set(assoc["DiseaseID"].map(clean))

    missing_genes = assoc_gene_ids - gene_ids
    missing_diseases = assoc_disease_ids - disease_ids

    report = pd.DataFrame(
        [
            ["Disease_master_rows", len(disease)],
            ["Disease_master_unique_IDs", disease["DiseaseID"].nunique()],
            ["Diseases_with_gene_associations",
             int((disease["Has_Gene_Association"] == "Yes").sum())],
            ["Diseases_without_gene_associations",
             int((disease["Has_Gene_Association"] == "No").sum())],
            ["Disease_name_conflicts",
             int((disease["Disease_Name_Conflict"] == "Yes").sum())],
            ["Gene_master_rows", len(gene)],
            ["Gene_master_unique_HGNC_IDs", gene["HGNC_ID"].nunique()],
            ["Genes_missing_current_HGNC_record",
             int((gene["HGNC_Record_Found"] == "No").sum())],
            ["Genes_introduced_by_verified_RetNet_only",
             int((gene["Introduced_By_Verified_RetNet"] == "Yes").sum())],
            ["Association_rows", len(assoc)],
            ["Association_HGNC_IDs_missing_from_Gene_master", len(missing_genes)],
            ["Association_DiseaseIDs_missing_from_Disease_master", len(missing_diseases)],
        ],
        columns=["Metric", "Value"]
    )

    Path(args.gene_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.disease_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_output).parent.mkdir(parents=True, exist_ok=True)

    gene.to_csv(args.gene_output, sep="\t", index=False)
    disease.to_csv(args.disease_output, sep="\t", index=False)
    report.to_csv(args.report_output, sep="\t", index=False)

    print("ODDB CORE ENTITY BUILD")
    print(report.to_string(index=False))

    if missing_genes:
        print("\nERROR: association HGNC IDs missing from Gene master:")
        print(sorted(missing_genes))

    if missing_diseases:
        print("\nERROR: association DiseaseIDs missing from Disease master:")
        print(sorted(missing_diseases))

    if not missing_genes and not missing_diseases:
        print("\nCORE ENTITY VALIDATION PASSED.")

    print(f"\nGene master: {args.gene_output}")
    print(f"Disease master: {args.disease_output}")
    print(f"Report: {args.report_output}")

if __name__ == "__main__":
    main()
