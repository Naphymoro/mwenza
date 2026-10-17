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

## Provenance Ledger

`provenance.py` keeps an append-only log of `LedgerEvent`s. Each event's hash covers its fields and the previous event's hash, and snapshot text is bound by a SHA-256 `content_hash`, so `verify` detects edits to a saved ledger. Attribution follows each paragraph of the latest snapshot back through earlier snapshots by text similarity, then combines browser paste reports, the flags of checks tied to each snapshot, and verbatim six-word shingle matches against sources in scope. The Reproducer agent holds the `inspect_provenance` tool. The ledger has no user identity yet; binding events to authenticated accounts and signing the chain head are required before it can serve as institutional evidence.

## Literature discovery

`discovery.py` is the first external connector. It keeps the evidence contract: search results are returned for inspection, and only user-selected abstracts or passages become notebook sources, each carrying a citation header, its URL and the retrieval date. The Scout agent holds the `search_literature` tool, which is marked medium risk and approval-required, matching the rule that external discovery stays a separate, permissioned capability. The connector is disabled unless a deployment opts in, because the Asta corpus licence restricts use to academic, non-commercial research.

## Paradigm–Method Checker

`methodology.py` is the single catalogue of paradigms, strategies, sampling, data collection, analysis and quality criteria; both `golden_thread.py` and `paradigm.py` read from it, so a correction there changes both checks. `paradigm.py` evaluates the design layer by layer and treats departures from the catalogue as tensions to justify rather than errors, except where a design contradicts itself (for example a qualitative design with only statistical analysis, or deductive grounded theory). The Methodologist agent holds the `paradigm-method` skill and its `check_paradigm_fit` tool.

## Open discovery (Phase A)

`open_discovery.py` implements Phase A of `docs/analysis/DISCOVERY_ENGINE_DESIGN.md`: federated search over OpenAlex, Crossref and DOAJ with citation lookup through OpenCitations. Each adapter maps its API's records to one `OpenWork` shape, and the merge step keeps the most reusable abstract, so licence decisions are made once, in the engine, rather than in the browser. The source registry (`SOURCE_REGISTRY`) is the capability registry's record of each source's licence, attribution and rate limit. Phases B (local index) and C (licensed full text and passage search) build on the same `OpenWork` records.

## MCP server

`mcp_server.py` wraps open discovery and the three methodology checks as MCP tools using the official Python SDK (an optional dependency). Network-bound tools run in worker threads so one slow search does not block other sessions, discovery errors become MCP tool errors with their message, and responses use a compact record shape so agents receive licence, preprint and retraction information without internal fields. The server is tested in memory with the SDK's client and end to end over stdio and streamable HTTP, including with Mwenza's own MCP client in `discovery.py`.
