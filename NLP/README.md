# BioBERT PubMed Extractor for Ocular Diseases

This tool downloads PubMed abstracts on ocular diseases and uses **BioBERT** to extract information on **diseases, genes, drugs**, and **study types / clinical trial phases**.  
It outputs both **JSONL** and **CSV** formats for easy analysis.

---

## Features

- Query PubMed via NCBI Entrez
- Fetch MEDLINE records (title, abstract, metadata)
- Run **BioBERT NER** to detect:
  - Diseases  
  - Genes  
  - Drugs  
- Extract study design keywords (clinical trial, meta-analysis, etc.)
- Extract trial phases (Phase I–IV)
- Save results in JSONL and CSV

---

## Requirements

Install once:

```bash
pip install biopython transformers torch requests pandas tqdm
```
## Usage

1. Set your NCBI Entrez email

   Edit in the script or set as environment variable:

```bash
export ENTREZ_EMAIL="your.email@example.com"
```
Optional: set an NCBI API key for higher request limits.

2. Run the script

```bash
python biobert_pubmed_extractor.py
```

3. Outputs

Results are saved in biobert_pubmed_outputs/:

- pubmed_ocular_biobert.jsonl – one JSON record per article

- pubmed_ocular_biobert.csv – tabular version


## Configuration

You can override defaults with environment variables:

- PUBMED_QUERY – PubMed query string

- RETMAX – number of records to fetch (default 300)

- NER_MODEL – BioBERT model or fine-tuned checkpoint (default: kamalkraj/BioBERT-NER)

- OUT_DIR – output folder (default: biobert_pubmed_outputs)

Example:

```bash
PUBMED_QUERY="retinitis pigmentosa[Title]" RETMAX=100 python biobert_pubmed_extractor.py
```
