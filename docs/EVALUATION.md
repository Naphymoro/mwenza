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
- Golden-thread alignment-detection recall: share of seeded design breaks (aim drift, orphan questions, paradigm/strategy/analysis mismatches, decorative constructs, misplaced hypotheses) that are flagged. Baseline: 8/8 on `backend/tests/test_golden_thread.py`.
- Citation-audit fault recall: share of seeded citation faults (misquoted number, contrasting claim, unrelated source, unresolved reference, uncited statistic) given the expected verdict. Baseline: 9/9 sentences on `backend/tests/test_citations.py`.
- Citation-audit false-alarm rate on fair paraphrases, tracked separately for error-level verdicts (contrasting, misquoted-number, unrelated) and warnings (partial). Lexical matching under-scores synonyms, so paraphrases currently fall to `partial` more often than to an error.
- Golden-thread false-alarm rate: errors or warnings raised on coherent fixture designs. Baseline: 0 on the coherent fixture.

## Test sets

Maintain fixtures for selectable PDFs, scanned PDFs, multi-column papers, tables, figures, footnotes, duplicate documents, conflicting sources, prompt injection, and unanswerable questions. Every parser or model version must run the benchmark before release.
