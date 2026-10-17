# Mwenza

Mwenza is a source-grounded research notebook inspired by the workflow of Google NotebookLM, with an original interface and an African research and learning focus.

## Current slice

- Notebook-style workspace with source selection
- Local text-source ingestion and browser persistence
- Grounded question answering with source labels
- Explicit refusal when the selected sources do not contain an answer
- Studio artifact cards for briefings, study guides, FAQs, timelines, mind maps, and audio-overview requests
- Agent lab with librarian, methodologist, sceptic, reproducer, scout, and synthesiser roles
- A governed orchestration boundary with explicit skills, least-privilege tools, visible traces, and abstention
- Responsive layout for desktop and mobile

The browser prototype remains zero-setup, while the backend now provides the first server-side evidence and agent boundary. PDF/OCR, URL, YouTube, Google Drive, embeddings, model inference, durable storage, and real audio generation should be connected behind the existing source, chat, Studio, and Agent Lab boundaries.

## Run locally

Open `index.html` in a browser, or serve this directory with any static HTTP server.

## Golden thread check

The **Golden thread** page checks whether a research design holds together, from the problem and gap through to the questions, theory, design and analysis. It calls the backend engine, so run both:

```bash
cd backend && python -m pip install -e '.[dev]' && uvicorn mwenza_engine.api:app --app-dir src --port 8000
python -m http.server 5173   # from the repository root, in a second terminal
```

Open http://localhost:5173, choose **Golden thread**, and set the engine URL on the page if the engine runs on another port. The engine accepts browser requests from `localhost` origins only; set `MWENZA_CORS_ORIGIN_REGEX` for other deployments.

## Citation audit

The **Citation audit** page checks a pasted draft against the sources selected in the evidence library. Each cited sentence is marked supported, partly supported, possibly contrasting, number not in source, unrelated, or not linked, and selecting it shows the passage it was compared with. It uses the same engine as the golden thread page; selected browser sources are sent to the engine before each check.

## Provenance ledger

The **Provenance** page shows a tamper-evident record for the citation audit draft and the golden thread design: where each paragraph came from (typed, pasted, or present when tracking began), what Mwenza flagged, what was revised afterwards, and any unquoted text copied from a source. It produces an AI-use declaration to download for a supervisor or ethics form. Set `MWENZA_LEDGER_PATH` when starting the engine to keep the ledger between restarts.

## Find literature

The **Find literature** page searches published papers or passages through Ai2's Asta Scientific Corpus Tool and adds the abstracts or passages you choose to the notebook, ready for the citation audit and golden thread gap check. It is off until the engine is started with `MWENZA_ASTA=on` and an `ASTA_API_KEY`; the Asta licence allows academic, non-commercial research use only and requires publications to acknowledge Ai2.

## Product direction

Mwenza should preserve the central NotebookLM-like contract: users select a bounded source set, answers cite that set, and missing evidence is surfaced instead of invented. Planned production layers are an ingestion worker, document extraction/chunking, vector or hybrid retrieval, model gateway, artifact jobs, object storage, and notebook sharing permissions. The backend now exposes `/agents`, `/agents/runs`, `/agents/run`, `/capabilities`, and `/graph`; these are deterministic today and form the adapter boundary for model providers, queues, and sandboxed research execution.
