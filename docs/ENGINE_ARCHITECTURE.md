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

## Agent operating model

Mwenza agents are governed specialists, not unconstrained chat personas. Each
agent has a declared role, a small skill set, operating rules, and a visible
run trace. The first implementation uses deterministic retrieval so the
system can be tested without a model key. Future model adapters must preserve
the same contract: selected-source scope, least-privilege tools, evidence
citations, abstention, and a durable run record.

The initial roles are Librarian, Methodologist, Sceptic, Reproducer, Scout,
and Synthesiser. High-impact capabilities such as code execution, external
discovery, and reverse engineering must remain separate tools with explicit
permissions, provenance, and human approval.

## Golden Thread Engine

The methodology layer treats a thesis as a typed research-design graph rather than prose. `golden_thread.py` builds nodes for each design element and links them with lexical carry-over scores and methodology rules. The Methodologist agent holds the `golden-thread` skill and its `check_alignment` tool. Gap claims reuse the evidence contract: the gap is retrieved against selected sources and returned as candidate citations, never as a verdict. Model-assisted checks (semantic similarity, construct synonymy) can later replace the lexical scorer behind the same report contract.

## Claim–Citation Auditor

`citations.py` audits a draft sentence by sentence. Each citation is resolved to a source in scope, then the claim (with citation markers removed) is compared with every single sentence and adjacent sentence pair of that source. The best window is returned as a `Passage` with absolute offsets into the source, so the verdict always points at inspectable evidence. The Sceptic agent holds the `citation-auditor` skill and its `audit_citations` tool. Shared text handling (sentence splitting with abbreviation masking, stemming, stopwords) lives in `text.py` and is used by both methodology engines.
