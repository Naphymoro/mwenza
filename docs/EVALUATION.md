# Mwenza evaluation plan

The engine should not be considered research-grade until it is measured on a versioned benchmark.

## Required metrics

- OCR character error rate by document type.
- Page and section extraction accuracy.
- Table extraction accuracy.
- Retrieval recall@5 and recall@20.
- Citation precision: cited spans actually support the claim.
- Citation recall: required supporting spans were retrieved.
- Claim-level groundedness.
- Abstention precision and recall.
- Entity-linking precision, recall, and ambiguous-match rate.
- Relation precision, recall, and provenance coverage.
- End-to-end latency and job failure/retry rate.

## Test sets

Maintain fixtures for selectable PDFs, scanned PDFs, multi-column papers, tables, figures, footnotes, duplicate documents, conflicting sources, prompt injection, and unanswerable questions. Every parser or model version must run the benchmark before release.
