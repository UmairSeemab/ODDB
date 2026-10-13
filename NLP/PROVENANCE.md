# PubMed/BioBERT text-mining code provenance

This directory preserves the historical PubMed/BioBERT extraction
utility from the earlier ODDB GitHub repository.

The script provides:
- PubMed retrieval through NCBI Entrez
- Disease, gene and chemical/drug entity extraction using a
  configurable token-classification model
- Rule-based extraction of study design and clinical trial phases
- JSONL and CSV exports

This is a standalone research utility.

Its inclusion does not establish that its outputs were incorporated
into the validated ODDB v1 scientific release. Any such use must be
supported by source-to-output provenance and validation records.

The default NER model, retrieval dates, database integration,
entity recognition performance and literature evidence curation
must be verified before making publication-level claims.

No private API credentials or generated PubMed datasets are included.
