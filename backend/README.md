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

Endpoints: `GET /health`, `GET /sources`, `POST /sources/upload`, `POST /query`, `GET /agents`, `GET /agents/runs`, `POST /agents/run`, `POST /workflows/run`, `GET /capabilities`, `GET /graph`, `POST /sources/text`, `POST /golden-thread/check`, `POST /citations/audit`, `POST /paradigm/check`, `GET /provenance/{document_id}`, `GET /discovery/status`, `POST /discovery/papers`, `POST /discovery/snippets`, `POST /discovery/citations`, and `POST /discovery/published-version`.

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

## Open literature discovery (default)

`open_discovery.py` searches openly licensed scholarly metadata and is the default provider for `POST /discovery/papers` (`"provider": "open"`); Asta remains available as `"provider": "asta"` where enabled. It needs no account.

- **Sources:** OpenAlex (CC0), Crossref (metadata usable for any purpose) and DOAJ (CC0 metadata) are queried in parallel, merged by DOI and then by title and year, and ranked by reciprocal-rank fusion. `POST /discovery/citations` returns works citing a DOI, or cited by it, from OpenCitations (CC0), described with OpenAlex metadata.
- **Licence per field:** every result lists the sources that supplied it, whether its abstract may be stored (OpenAlex and DOAJ abstracts yes; Crossref abstracts no, as they may be under publisher copyright), the open-access licence, and whether full text could be reused (`yes`, `restricted` for NC/ND licences, `no`, `unknown`). Works hosted on AJOL are marked link-only, because AJOL does not permit reusing its abstracts or full text.
- **Resilience:** a source that fails is reported in `sources_status` while the others still answer. Server errors and timeouts are retried twice with backoff, a 429 with a short `Retry-After` is retried once, and an exhausted OpenAlex budget or rejected key returns a clear message (with the hours until reset). Responses are cached for 24 hours and requests to each service are spaced.
- **OpenAlex search behaviour** (tested against the live API): queries are cleaned first, because OpenAlex rejects wildcards and treats commas and `|` as filter syntax; words, quotes, brackets, apostrophes, accents and AND/OR/NOT are kept. Titles and abstracts are searched first (`title_and_abstract.search`, excluding front matter); if that finds fewer than three works, OpenAlex's broader full-text search fills in and those works are labelled "matched only in the full text". A pasted DOI is looked up directly (no search credits), falling back to Crossref. Retracted works are flagged, non-English works carry their language, and front-matter items (news, editorials, errata) are dropped.
- **Ranking:** results are fused with OpenAlex weighted highest (OpenAlex 1.0, DOAJ 0.8, Crossref 0.6), Crossref is limited to research output types, and the same work under two DOIs (same title, years at most one apart, same first author) is listed once with a note.
- **Limits:** without a key, OpenAlex allows about 100 searches a day (1,000 credits at 10 per search); set `MWENZA_OPENALEX_KEY` to a free key for ten times that. Set `MWENZA_CONTACT_EMAIL` to identify the engine to Crossref and OpenAlex; no contact address is sent unless it is configured.
- **Provenance:** pass `document_id` to record each search in the ledger; the Provenance page shows these under "Literature searches".

Source licences and rate limits are listed in `GET /capabilities` under `data_sources`. Test fixtures in `tests/fixtures/open_discovery/` are trimmed copies of real responses (OpenAlex, DOAJ and OpenCitations data are CC0; the Crossref abstract was replaced with placeholder text).

### Preprints (Phase A+)

`preprints.py` adds preprint servers to open discovery. `POST /discovery/papers` takes `"scope": "all" | "peer-reviewed" | "preprints"`.

| Source | Route | Notes |
| --- | --- | --- |
| arXiv | Its own API | Metadata CC0. One request every three seconds and one connection at a time, as arXiv's terms require. The published DOI and journal reference are reported by authors and labelled as such. |
| Europe PMC preprints | `SRC:PPR` search | About 30 life-science servers (bioRxiv, medRxiv, Research Square and others). Licence per record; published versions come from Europe PMC's title and first-author match. |
| Crossref posted content | `type:posted-content` | ChemRxiv (whose own API sits behind a bot check), SSRN, Research Square and others. Published versions come from the server-registered `is-preprint-of` relation. |
| AfricArXiv | Zenodo community and Crossref prefix 10.31730 (OSF) | Licence per record; the OSF prefix attribution is inferred. |
| OpenAlex | `type:preprint` | Preprints already indexed by OpenAlex. |
| bioRxiv / medRxiv API | `POST /discovery/published-version` | On request, finds the published version of a 10.1101 preprint. |

Every preprint carries `preprint`, a standardised `server` name and, where known, `published_doi`, `published_venue`, `published_url` and `published_source` (how the link was established). When a preprint and its published version both appear, only the published version is listed, with a note. Abstracts are stored only under an open licence (arXiv metadata CC0; CC BY or CC0 for other servers). Preprints scope drops anything not marked as a preprint and peer-reviewed scope drops anything that is. arXiv and Crossref requests run one at a time, and Crossref 429s are retried after a pause.
