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

Endpoints: `GET /health`, `GET /sources`, `POST /sources/upload`, `POST /query`, `GET /agents`, `GET /agents/runs`, `POST /agents/run`, `POST /workflows/run`, `GET /capabilities`, and `GET /graph`.

The model gateway is provider-neutral and offline by default. Set
`MWENZA_MODEL_PROVIDER` and `MWENZA_MODEL_NAME` to advertise a configured
adapter; actual model calls must be implemented behind that boundary with
source citations, prompt-injection isolation, and run provenance preserved.
