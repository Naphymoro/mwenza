# Mwenza evidence engine

This backend is the first auditable engine slice behind the browser prototype.

## Pipeline

`upload → checksum → extract → OCR fallback → page evidence → lexical retrieval → citation-backed answer`

The graph extractor is intentionally conservative. It creates candidate entities and co-occurrence edges with low confidence and exact provenance; it does not claim that co-occurrence means causation or a verified semantic relationship.

## PDF handling

- Selectable-text PDFs are parsed with PyMuPDF, retaining page numbers and extraction method.
- Empty pages are sent to the optional Tesseract/Pillow OCR adapter when installed.
- If no text or OCR is available, the source is marked `ocr_required` rather than silently indexed as empty.

## Run

```bash
python -m pip install -e '.[dev,ocr]'
uvicorn mwenza_engine.api:app --app-dir src --reload
```

Endpoints: `GET /health`, `GET /sources`, `POST /sources/upload`, `POST /query`, `GET /agents`, `GET /agents/runs`, `POST /agents/run`, `POST /workflows/run`, `GET /capabilities`, `GET /graph`, `POST /sources/text`, `POST /golden-thread/check`, `POST /citations/audit`, `POST /paradigm/check`, `GET /provenance/{document_id}`, `GET /discovery/status`, `POST /discovery/papers`, and `POST /discovery/snippets`.

The model gateway is provider-neutral and offline by default. Set
`MWENZA_MODEL_PROVIDER` and `MWENZA_MODEL_NAME` to advertise a configured
adapter; actual model calls must be implemented behind that boundary with
source citations, prompt-injection isolation, and run provenance preserved.

## Golden Thread Engine

`POST /golden-thread/check` takes a research design (problem, gap, aim, objectives, questions, hypotheses, paradigm, approach, strategy, theory and constructs, data collection, analysis, and optional findings) and returns a typed alignment graph with nodes, scored links and issues.

Checks are deterministic, so no model key is needed:

- **Chain:** problem → gap → aim → objectives carry key terms forward.
- **Objective–question:** every question answers an objective, and every objective has a question.
- **Hypotheses:** each hypothesis tests a question; hypotheses are flagged in qualitative designs.
- **Question–approach:** exploratory wording ("how do…experience") vs confirmatory wording ("effect", "relationship") must fit the approach.
- **Paradigm–approach and strategy–approach:** e.g. interpretivism with a quantitative survey is an error.
- **Approach–analysis:** quantitative designs need statistical tests, qualitative designs need interpretive analysis, and mixed designs need both.
- **Theory–constructs:** each construct must appear in a question, hypothesis or instrument; otherwise the theory is decorative.
- **Findings–questions:** every question is answered by a finding.
- **Gap evidence:** with `source_ids`, the gap is retrieved against the selected sources and candidate passages are returned for human review.

Each issue carries `teach` (the methodological principle) and `ask` (a Socratic question). The engine never rewrites the student's text. Links with too little text are reported as `unknown` rather than guessed. `status` (`aligned`, `review`, `needs-revision`) is the verdict; `alignment_score` is only the share of judged links that are aligned.

## Claim–Citation Auditor

`POST /citations/audit` takes a draft (`text`), the sources in scope (`source_ids`) and optional `references` that link citation keys to sources (for example `{"ref-3": "src-…"}` or `{"ouma-2021": "src-…"}`). It returns every sentence with its offsets and, for each citation, a verdict and the passage it was compared against.

- **Citations recognised:** parenthetical author–year `(Ouma & Kiprop, 2021; Smith et al., 2019)`, narrative `Ouma (2021)`, and numbered `[3]`, `[2–4]`.
- **Resolution:** author–year citations are matched automatically when exactly one source in scope contains the surname and year in its name or opening text. Ambiguous or numbered citations stay `unresolved` until linked through `references`; the engine never guesses.
- **Verdicts:** `supported`, `partial`, `contrasting` (the claim and passage point in opposite directions once negations and words such as higher/lower are multiplied through), `misquoted-number` (a percentage, decimal or count in the claim is absent from the best passage), `unrelated`, `unresolved`, and `unknown` (too little text). Uncited sentences that read as factual claims are flagged `needs-citation`.

`POST /sources/text` ingests pasted text under a caller-supplied id, so the browser workspace can push its sources before an audit or a golden thread gap check. Re-sending an id replaces that source.

## Provenance Ledger

When `/golden-thread/check` or `/citations/audit` is called with a `document_id`, the engine appends two events to an append-only, hash-chained ledger: a `text-snapshot` of the submitted text (with any `pasted_segments` the browser reports) and an `ai-check` recording what Mwenza flagged. Set `MWENZA_LEDGER_PATH` to persist the ledger as JSONL; otherwise it lives in memory.

`GET /provenance/{document_id}` (optionally with `source_ids`) returns:

- **Integrity:** whether every event matches its hash and the chain is unbroken. The ledger is tamper-evident, not tamper-proof.
- **Paragraph attribution** for the latest version: typed in Mwenza, pasted (origin not recorded), partly pasted, or present when tracking began; the feedback Mwenza raised on it, whether it was revised afterwards, and whether issues remain open in the latest check.
- **Verbatim matches:** runs of 10 or more words identical to a source in scope, marked quoted or unquoted.
- **Declaration:** a Markdown AI-use statement built only from recorded facts, with its limits stated.

## Literature discovery (Ai2 Asta)

The engine can search published literature through Ai2's [Asta Scientific Corpus Tool](https://allenai.org/asta/resources/mcp), an MCP server over the Semantic Scholar corpus. `discovery.py` contains a small streamable-HTTP MCP client (JSON-RPC over POST, server-sent events, session ids) and normalises `search_papers_by_relevance` and `snippet_search` results.

It is **off by default**. The [Asta licence](https://allenai.org/asta-corpus-license) permits academic and non-commercial research only, forbids sharing the key outside your organisation's authorised staff, and requires publications that use the tool to acknowledge Ai2. Each deployment enables it with its own key:

```bash
MWENZA_ASTA=on ASTA_API_KEY=your-key uvicorn mwenza_engine.api:app --app-dir src
```

`MWENZA_ASTA_URL` and `MWENZA_ASTA_TIMEOUT` (seconds, default 60) override the endpoint and timeout. Without a key, Asta accepts connections but tool calls can take minutes. Nothing is added to a notebook automatically: the browser adds an abstract or passage only when the user chooses it.

OpenScholar is not connected. It has no hosted API: its [repository](https://github.com/AkariAsai/OpenScholar) provides a command-line pipeline whose local index needs very large memory, and its retriever endpoint is announced as planned. The connector boundary is ready for it once that endpoint exists.

## Paradigm–Method Checker

`POST /paradigm/check` checks each layer of a methodology against the stated paradigm, following the layers of the widely taught "research onion": paradigm, approach to theory (deductive, inductive, abductive), methodological choice, strategy, time horizon, sampling and sample-size justification, data collection, analysis, and quality criteria. It also checks that hypotheses state a relationship and that their constructs are measured, that questions about change are not answered with cross-sectional data, and that qualitative or purposively sampled designs do not claim statistical generalisation.

Each layer gets a status (`coherent`, `tension`, `conflict`, `missing`, `unrecognised`), and inferred values say where they came from. Conflicts list coherent alternatives in both directions (keep the paradigm and change the method, or keep the method and reconsider the paradigm). The response includes a teaching profile of the paradigm's ontology, epistemology and axiology. The catalogue in `methodology.py` covers positivism, post-positivism, critical realism, interpretivism/constructivism, pragmatism, critical/transformative and Afrocentric/Indigenous paradigms (including Ubuntu); the golden thread check uses the same catalogue. Pass a `document_id` to record the check in the provenance ledger.
