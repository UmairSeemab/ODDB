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

