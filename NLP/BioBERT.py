#!/usr/bin/env python3
# Step by step: Download PubMed data and run BioBERT NER for ocular diseases
# Install once:
#   pip install biopython transformers torch requests pandas tqdm

# ---------------------------
# Step 0. Imports and config
# ---------------------------
import os
import re
import json
import time
from typing import List, Dict, Any
from collections import defaultdict

from Bio import Entrez, Medline         # PubMed E-utilities
import pandas as pd                     # Save tables
from tqdm import tqdm                   # Progress bars

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, TokenClassificationPipeline

# User editable configuration
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "you@example.com")   # Set your email
ENTREZ_API_KEY = os.getenv("ENTREZ_API_KEY")                  # Optional NCBI API key

# PubMed query focused on ocular diseases
PUBMED_QUERY = os.getenv(
    "PUBMED_QUERY",
    "(ocular diseases[MeSH Terms]) OR (retina OR retinal OR uveitis OR glaucoma OR macular degeneration)"
)

RETMAX = int(os.getenv("RETMAX", "300"))            # How many PubMed records to fetch
EFETCH_BATCH = int(os.getenv("EFETCH_BATCH", "100"))# Batch size for efetch
INFER_CHARS = int(os.getenv("INFER_CHARS", "4000")) # Max characters per NER chunk

# Choose a BioBERT NER checkpoint. Replace with your fine tuned model path for best results
NER_MODEL = os.getenv("NER_MODEL", "kamalkraj/BioBERT-NER")

# Output directory
OUT_DIR = os.getenv("OUT_DIR", "biobert_pubmed_outputs")
os.makedirs(OUT_DIR, exist_ok=True)


# --------------------------------------
# Step 1. Helper to search PubMed PMIDs
# --------------------------------------
def search_pmids(query: str, retmax: int) -> List[str]:
    """
    Sends a query to PubMed. Returns a list of PMIDs.
    """
    Entrez.email = ENTREZ_EMAIL
    if ENTREZ_API_KEY:
        Entrez.api_key = ENTREZ_API_KEY
    handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax, sort="relevance")
    rec = Entrez.read(handle)
    handle.close()
    return rec.get("IdList", [])


# ------------------------------------------------------
# Step 2. Fetch MEDLINE records for a list of PubMed IDs
# ------------------------------------------------------
def fetch_medline_records(pmids: List[str], batch: int) -> List[Dict[str, Any]]:
    """
    Fetches MEDLINE format for PMIDs in batches. Returns a list of parsed records.
    """
    Entrez.email = ENTREZ_EMAIL
    if ENTREZ_API_KEY:
        Entrez.api_key = ENTREZ_API_KEY

    all_recs = []
    for i in tqdm(range(0, len(pmids), batch), desc="Fetching MEDLINE"):
        chunk = pmids[i:i + batch]
        handle = Entrez.efetch(db="pubmed", id=",".join(chunk), rettype="medline", retmode="text")
        recs = list(Medline.parse(handle))
        handle.close()
        all_recs.extend(recs)
        time.sleep(0.34)   # Be polite to NCBI servers
    return all_recs


# ------------------------------------------------------
# Step 3. Build text to send into the NER model
# ------------------------------------------------------
def join_abstract(record: Dict[str, Any]) -> str:
    """
    Returns the abstract string. Handles list or string formats.
    """
    ab = record.get("AB", "")
    if isinstance(ab, list):
        return " ".join(ab)
    return ab or ""


def build_context(record: Dict[str, Any]) -> str:
    """
    Concatenates title and abstract for NER input.
    """
    title = record.get("TI", "") or ""
    abstract = join_abstract(record)
    parts = []
    if title.strip():
        parts.append(title.strip())
    if abstract.strip():
        parts.append(abstract.strip())
    return ". ".join(parts)


# -----------------------------------------------
# Step 4. Load BioBERT NER as a HF pipeline
# -----------------------------------------------
def load_biobert_ner(model_name: str) -> TokenClassificationPipeline:
    """
    Loads tokenizer and model. Builds a token classification pipeline.
    Uses GPU when available.
    """
    print(f"Loading NER model {model_name}")
    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModelForTokenClassification.from_pretrained(model_name)
    device = 0 if torch.cuda.is_available() else -1
    return TokenClassificationPipeline(
        model=mdl,
        tokenizer=tok,
        aggregation_strategy="simple",
        device=device
    )


# -----------------------------------------------------
# Step 5. Label normalization and study info patterns
# -----------------------------------------------------
CANON_MAP = {
    "DISEASE": "Disease",
    "DIAGNOSIS": "Disease",
    "PROBLEM": "Disease",
    "CONDITION": "Disease",
    "GENE": "Gene",
    "GENE_OR_GENE_PRODUCT": "Gene",
    "DNA": "Gene",
    "RNA": "Gene",
    "CHEMICAL": "Drug",
    "DRUG": "Drug",
    "CHEMICALSUBSTANCE": "Drug"
}

def canonical_label(label: str) -> str:
    """
    Maps model label names to one of Disease, Gene, Drug, or Other.
    """
    lab = label.upper().replace("-", "").replace("_", "")
    for k, v in CANON_MAP.items():
        if lab == k or k in lab:
            return v
    return "Other"

# Study design and clinical trial phase patterns
STUDY_TYPE_PATTERNS = [
    r"\brandomi[sz]ed controlled trial\b",
    r"\bclinical trial\b",
    r"\bmeta-analysis\b",
    r"\bsystematic review\b",
    r"\bcohort study\b",
    r"\bcase[- ]control study\b",
    r"\bcross[- ]sectional study\b",
    r"\bprospective study\b",
    r"\bretrospective study\b",
    r"\bcase series\b",
    r"\bcase report\b"
]

TRIAL_PHASE_PATTERNS = [
    r"\bphase I\b",
    r"\bphase II\b",
    r"\bphase III\b",
    r"\bphase IV\b"
]

def find_keywords(text: str, patterns) -> List[str]:
    """
    Returns matched study keywords. Case insensitive search.
    """
    found = set()
    low = text.lower()
    for pat in patterns:
        for m in re.finditer(pat, low, flags=re.IGNORECASE):
            found.add(m.group(0))
    return sorted(found)


# -------------------------------------------------
# Step 6. NER over one long document with chunking
# -------------------------------------------------
def ner_document(pipe: TokenClassificationPipeline, text: str, max_chars: int) -> Dict[str, List[str]]:
    """
    Applies NER to a long text using simple character chunking.
    Aggregates and deduplicates entities.
    """
    if not text:
        return {"Disease": [], "Gene": [], "Drug": []}

    # Chunk by characters to avoid truncation
    chunks = []
    s = 0
    while s < len(text):
        e = min(s + max_chars, len(text))
        cut = text.rfind(".", s, e)
        if cut == -1 or cut <= s:
            cut = e
        chunks.append(text[s:cut])
        s = cut + 1

    buckets = defaultdict(list)
    for ch in chunks:
        if not ch.strip():
            continue
        outputs = pipe(ch)
        for r in outputs:
            word = r.get("word", "").strip()
            label = r.get("entity_group", r.get("entity", ""))
            group = canonical_label(label)
            if group in {"Disease", "Gene", "Drug"} and word:
                buckets[group].append(word)

    # Deduplicate while preserving order
    for k in list(buckets.keys()):
        seen = set()
        ordered = []
        for w in buckets[k]:
            wl = w.lower()
            if wl in seen:
                continue
            seen.add(wl)
            ordered.append(w)
        buckets[k] = ordered

    for k in ["Disease", "Gene", "Drug"]:
        buckets.setdefault(k, [])

    return buckets


# ----------------------------------------------------------------
# Step 7. Analyze all records. Extract entities and study signals
# ----------------------------------------------------------------
def analyze_records(pipe: TokenClassificationPipeline, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Runs NER and keyword matching per MEDLINE record.
    Collects metadata and returns a list of result dicts.
    """
    rows = []
    for r in tqdm(records, desc="Analyzing records"):
        pmid = r.get("PMID", "")
        title = r.get("TI", "") or ""
        journal = r.get("JT", "") or r.get("TA", "") or ""
        year = ""
        dp = r.get("DP", "")
        if isinstance(dp, str):
            m = re.match(r"(\d{4})", dp)
            if m:
                year = m.group(1)

        context = build_context(r)
        ents = ner_document(pipe, context, INFER_CHARS)
        study_types = find_keywords(context, STUDY_TYPE_PATTERNS)
        trial_phases = find_keywords(context, TRIAL_PHASE_PATTERNS)

        rows.append({
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "year": year,
            "diseases": ents["Disease"],
            "genes": ents["Gene"],
            "drugs": ents["Drug"],
            "study_types": study_types,
            "trial_phases": trial_phases,
            "abstract": join_abstract(r)
        })
    return rows


# --------------------------------------------
# Step 8. Save the results to JSONL and CSV
# --------------------------------------------
def save_outputs(rows: List[Dict[str, Any]], out_dir: str) -> None:
    """
    Persists results to a JSONL file and a CSV table.
    """
    jsonl_path = os.path.join(out_dir, "pubmed_ocular_biobert.jsonl")
    csv_path = os.path.join(out_dir, "pubmed_ocular_biobert.csv")

    with open(jsonl_path, "w", encoding="utf8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"Wrote {len(rows)} rows")
    print(f"JSONL  {jsonl_path}")
    print(f"CSV    {csv_path}")


# --------------------------------------------
# Step 9. Glue it together in main function
# --------------------------------------------
def main():
    # Search PubMed for PMIDs
    print("Step 1. Search PubMed")
    pmids = search_pmids(PUBMED_QUERY, RETMAX)
    if not pmids:
        print("No PMIDs found")
        return
    print(f"Found {len(pmids)} PMIDs")

    # Fetch MEDLINE records
    print("Step 2. Fetch MEDLINE")
    records = fetch_medline_records(pmids, EFETCH_BATCH)
    print(f"Fetched {len(records)} records")

    # Load BioBERT NER
    print("Step 3. Load BioBERT NER")
    pipe = load_biobert_ner(NER_MODEL)

    # Run extraction
    print("Step 4. Extract entities and study info")
    rows = analyze_records(pipe, records)

    # Save outputs
    print("Step 5. Save outputs")
    save_outputs(rows, OUT_DIR)

    print("Done")


# --------------------------------------------
# Step 10. Script entry point
# --------------------------------------------
if __name__ == "__main__":
    main()

