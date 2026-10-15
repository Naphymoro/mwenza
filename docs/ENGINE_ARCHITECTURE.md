# Mwenza engine architecture

## Evidence contract

The atomic unit of knowledge is an `EvidenceSpan`. It contains the source ID, page, character range, extracted text, extraction method, confidence, and parser version. Retrieval, graph facts, citations, and answers must point back to this contract.

## Processing stages

1. Validate the upload and compute a SHA-256 checksum.
2. Extract page-aware text with PyMuPDF.
3. Send pages with no selectable text to the optional OCR adapter.
4. Store the original source and immutable extraction metadata.
5. Chunk evidence without discarding source offsets.
6. Index evidence using lexical retrieval and, later, a versioned embedding index.
7. Extract candidate entities and relationships with confidence and provenance.
8. Retrieve and rerank evidence for a question.
9. Produce an extractive or model-assisted answer only from retrieved evidence.
10. Attach citations and abstain when evidence is insufficient.

## Production decisions still required

- Durable object storage and PostgreSQL schema.
- Tenant and notebook permissions.
- Queue implementation for OCR, embeddings, graph extraction, and audio jobs.
- Embedding provider and reranker benchmark.
- Human review workflow for entity resolution and graph edges.
- PDF table, figure, and reading-order benchmark.
- Prompt-injection isolation for untrusted source content.
