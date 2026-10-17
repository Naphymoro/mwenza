from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .golden_thread import ResearchDesign
from .pipeline import NotebookEngine
from .model_gateway import ModelGateway
from .tools import tool_catalogue

app = FastAPI(title="Mwenza Evidence Engine", version="0.1.0")
# The browser workspace is served separately during development, so allow
# local origins by default; deployments set MWENZA_CORS_ORIGIN_REGEX.
app.add_middleware(CORSMiddleware, allow_origin_regex=os.environ.get("MWENZA_CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?"), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
engine = NotebookEngine()
model_gateway = ModelGateway()


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    source_ids: set[str] | None = None


class AgentRunRequest(BaseModel):
    agent_id: str = Field(min_length=2, max_length=80)
    objective: str = Field(min_length=2, max_length=4000)
    source_ids: set[str] | None = None


class WorkflowRunRequest(BaseModel):
    workflow_id: str = Field(min_length=2, max_length=80)
    objective: str = Field(min_length=2, max_length=4000)
    source_ids: set[str] | None = None


Items = list[str]


class GoldenThreadRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    problem: str = Field(default="", max_length=4000)
    gap: str = Field(default="", max_length=4000)
    aim: str = Field(default="", max_length=2000)
    objectives: Items = Field(default_factory=list, max_length=20)
    questions: Items = Field(default_factory=list, max_length=20)
    hypotheses: Items = Field(default_factory=list, max_length=20)
    paradigm: str = Field(default="", max_length=300)
    approach: str = Field(default="", max_length=300)
    strategy: str = Field(default="", max_length=500)
    theory: str = Field(default="", max_length=500)
    constructs: Items = Field(default_factory=list, max_length=30)
    data_collection: Items = Field(default_factory=list, max_length=20)
    analysis: Items = Field(default_factory=list, max_length=20)
    findings: Items = Field(default_factory=list, max_length=40)
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


@app.get("/agents")
def agents() -> dict[str, object]:
    return engine.agents.catalogue()


@app.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {"tools": tool_catalogue(), "model_gateway": model_gateway.status().__dict__}


@app.get("/graph")
def graph() -> dict[str, object]:
    return {"entities": [item.__dict__ for item in engine.entities], "relations": [item.__dict__ for item in engine.relations], "warning": "Relations are candidate co-occurrences unless explicitly human-validated."}


@app.get("/agents/runs")
def agent_runs() -> list[dict[str, object]]:
    return [engine.agents.serialise_run(run) for run in engine.agents.runs.values()]


@app.post("/agents/run")
def run_agent(request: AgentRunRequest) -> dict[str, object]:
    try:
        run = engine.agents.run(request.agent_id, request.objective, request.source_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return engine.agents.serialise_run(run)


@app.post("/workflows/run")
def run_workflow(request: WorkflowRunRequest) -> dict[str, object]:
    try:
        return engine.agents.workflow(request.workflow_id, request.objective, request.source_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/golden-thread/check")
def check_golden_thread(request: GoldenThreadRequest) -> dict[str, object]:
    design = ResearchDesign.from_dict(request.model_dump(exclude={"source_ids"}))
    return engine.check_golden_thread(design, request.source_ids).to_dict()
