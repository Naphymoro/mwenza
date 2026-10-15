from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .pipeline import NotebookEngine

app = FastAPI(title="Mwenza Evidence Engine", version="0.1.0")
engine = NotebookEngine()


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    source_ids: set[str] | None = None


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "sources": len(engine.sources), "evidence_spans": len(engine.evidence), "graph_entities": len(engine.entities), "graph_relations": len(engine.relations)}


@app.get("/sources")
def sources() -> list[dict[str, object]]:
    return [{"id": item.id, "name": item.name, "status": item.status, "media_type": item.media_type, "metadata": item.metadata} for item in engine.sources.values()]


@app.post("/sources/upload")
async def upload_source(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "source.txt").suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(await file.read())
        temp_path = Path(handle.name)
    try:
        record = engine.ingest(temp_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
    return {"id": record.id, "name": record.name, "status": record.status, "metadata": record.metadata, "pages": len(record.pages)}


@app.post("/query")
def query(request: QueryRequest) -> dict[str, object]:
    answer = engine.query(request.question, request.source_ids)
    return {"text": answer.text, "grounded": answer.grounded, "abstained": answer.abstained, "reason": answer.reason, "citations": [citation.__dict__ for citation in answer.citations], "retrieval_scores": answer.retrieval_scores}
