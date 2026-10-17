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

Endpoints: `GET /health`, `GET /sources`, `POST /sources/upload`, `POST /query`, `GET /agents`, `GET /agents/runs`, `POST /agents/run`, `POST /workflows/run`, `GET /capabilities`, `GET /graph`, and `POST /golden-thread/check`.

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
