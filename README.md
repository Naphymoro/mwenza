# Mwenza

Mwenza is a source-grounded research notebook inspired by the workflow of Google NotebookLM, with an original interface and an African research and learning focus.

## Current slice

- Notebook-style workspace with source selection
- Local text-source ingestion and browser persistence
- Grounded question answering with source labels
- Explicit refusal when the selected sources do not contain an answer
- Studio artifact cards for briefings, study guides, FAQs, timelines, mind maps, and audio-overview requests
- Responsive layout for desktop and mobile

This first slice is intentionally browser-only. PDF, URL, YouTube, Google Drive, embeddings, model inference, durable storage, and real audio generation should be connected behind the existing source, chat, and Studio boundaries in the next implementation pass.

## Run locally

Open `index.html` in a browser, or serve this directory with any static HTTP server.

## Product direction

Mwenza should preserve the central NotebookLM-like contract: users select a bounded source set, answers cite that set, and missing evidence is surfaced instead of invented. Planned production layers are an ingestion worker, document extraction/chunking, vector or hybrid retrieval, model gateway, artifact jobs, object storage, and notebook sharing permissions.
