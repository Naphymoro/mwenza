from __future__ import annotations

import os
import tempfile
from pathlib import Path

import json

from fastapi import FastAPI, File, HTTPException, Path as PathParam, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Literal

from pydantic import BaseModel, Field

from .deerflow_agent import AgentError, DeerFlowAgent
from .discovery import DiscoveryError, LiteratureDiscovery, serialise
from .open_discovery import SOURCE_REGISTRY, OpenDiscovery, serialise as serialise_open
from .golden_thread import ResearchDesign
from .navigator import NavigatorError, catalogue as navigator_catalogue, recommend as navigator_recommend
from .paradigm import MethodDesign
from .reproducer import SampleSizeError, check_reported_statistics, check_sample_size
from .pipeline import NotebookEngine
from .model_gateway import ModelGateway
from .tools import tool_catalogue

app = FastAPI(title="Mwenza Evidence Engine", version="0.1.0")
# The browser workspace is served separately during development, so allow
# local origins by default; deployments set MWENZA_CORS_ORIGIN_REGEX.
app.add_middleware(CORSMiddleware, allow_origin_regex=os.environ.get("MWENZA_CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?"), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
engine = NotebookEngine(os.environ.get("MWENZA_LEDGER_PATH"))
DOCUMENT_ID = r"^[\w.-]{1,120}$"
model_gateway = ModelGateway()
discovery = LiteratureDiscovery()
open_discovery = OpenDiscovery()
research_agent = DeerFlowAgent.from_env()


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


class StatisticsCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class SampleSizeRequest(BaseModel):
    design: Literal["proportion", "two-proportions", "two-means", "correlation"]
    parameters: dict[str, float | int | bool]
    reported_n: int | None = Field(default=None, ge=1)


class AttachedFile(BaseModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+$")
    size: int = Field(default=0, ge=0)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")
    private: bool = False
    files: list[AttachedFile] = Field(default_factory=list, max_length=20)


Items = list[str]


class DiscoveryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)
    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)
    provider: Literal["open", "asta"] = "open"
    scope: Literal["all", "peer-reviewed", "preprints"] = "all"
    document_id: str | None = Field(default=None, pattern=DOCUMENT_ID)


class NavigatorRequest(BaseModel):
    answers: list[str] = Field(default_factory=list, max_length=10)


class PublishedVersionRequest(BaseModel):
    doi: str = Field(min_length=6, max_length=300)


class CitationLookupRequest(BaseModel):
    doi: str = Field(min_length=6, max_length=300)
    direction: Literal["citing", "references"] = "citing"
    limit: int = Field(default=20, ge=1, le=50)


class ProvenanceFields(BaseModel):
    document_id: str | None = Field(default=None, pattern=DOCUMENT_ID)
    pasted_segments: list[str] = Field(default_factory=list, max_length=200)


class TextSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2_000_000)
    source_id: str | None = Field(default=None, pattern=r"^[\w.-]{1,120}$")


class ParadigmRequest(ProvenanceFields):
    title: str = Field(default="", max_length=300)
    paradigm: str = Field(default="", max_length=300)
    approach: str = Field(default="", max_length=300)
    logic: str = Field(default="", max_length=300)
    strategy: str = Field(default="", max_length=500)
    time_horizon: str = Field(default="", max_length=300)
    sampling: str = Field(default="", max_length=1000)
    sample_size: str = Field(default="", max_length=1000)
    data_collection: Items = Field(default_factory=list, max_length=20)
    analysis: Items = Field(default_factory=list, max_length=20)
    quality: Items = Field(default_factory=list, max_length=20)
    hypotheses: Items = Field(default_factory=list, max_length=20)
    questions: Items = Field(default_factory=list, max_length=20)
    claims: str = Field(default="", max_length=2000)


class CitationAuditRequest(ProvenanceFields):
    text: str = Field(min_length=1, max_length=200_000)
    source_ids: set[str] | None = None
    references: dict[str, str] = Field(default_factory=dict, max_length=500)


class GoldenThreadRequest(ProvenanceFields):
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


@app.post("/sources/text")
def add_text_source(request: TextSourceRequest) -> dict[str, object]:
    record = engine.ingest_text(request.name, request.text, request.source_id)
    return {"id": record.id, "name": record.name, "status": record.status, "pages": len(record.pages)}


@app.post("/query")
def query(request: QueryRequest) -> dict[str, object]:
    answer = engine.query(request.question, request.source_ids)
    return {"text": answer.text, "grounded": answer.grounded, "abstained": answer.abstained, "reason": answer.reason, "citations": [citation.__dict__ for citation in answer.citations], "retrieval_scores": answer.retrieval_scores}


@app.get("/agents")
def agents() -> dict[str, object]:
    return engine.agents.catalogue()


@app.get("/capabilities")
def capabilities() -> dict[str, object]:
    return {"tools": tool_catalogue(), "data_sources": {key: info.__dict__ for key, info in SOURCE_REGISTRY.items()}, "model_gateway": model_gateway.status().__dict__}


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
    design = ResearchDesign.from_dict(request.model_dump(exclude={"source_ids", "document_id", "pasted_segments"}))
    report = engine.check_golden_thread(design, request.source_ids)
    if request.document_id:
        engine.record_golden_thread(request.document_id, design, report, request.pasted_segments)
    return report.to_dict()


@app.post("/citations/audit")
def audit_citations(request: CitationAuditRequest) -> dict[str, object]:
    report = engine.audit_citations(request.text, request.source_ids, request.references)
    if request.document_id:
        engine.record_citation_audit(request.document_id, request.text, report, request.pasted_segments)
    return report.to_dict()


@app.get("/provenance/{document_id}")
def provenance(document_id: str = PathParam(pattern=DOCUMENT_ID), source_ids: list[str] | None = Query(default=None)) -> dict[str, object]:
    return engine.provenance_report(document_id, set(source_ids) if source_ids else None)


@app.get("/discovery/status")
def discovery_status() -> dict[str, object]:
    return {"default_provider": "open", "providers": {"open": open_discovery.status(), "asta": discovery.status()}}


def _discover(search) -> object:
    try:
        return search()
    except DiscoveryError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


def _record_search(request: DiscoveryRequest, kind: str, count: int, sources: dict[str, str] | None = None) -> None:
    if request.document_id:
        years = f", {request.year_from or '…'}–{request.year_to or '…'}" if request.year_from or request.year_to else ""
        engine.ledger.append(request.document_id, "discovery-search", "student", f"Searched {kind} via {request.provider}: \"{request.query}\"{years} ({count} results)", {"query": request.query, "provider": request.provider, "kind": kind, "results": count, "sources": sources or {}})


@app.post("/discovery/papers")
def discover_papers(request: DiscoveryRequest) -> dict[str, object]:
    if request.provider == "asta":
        results = serialise(_discover(lambda: discovery.search_papers(request.query, request.limit, request.year_from, request.year_to)))
        _record_search(request, "papers", len(results))
        return {"results": results, "attribution": discovery.status()["attribution"], "provider": "asta", "sources_status": {"asta": "ok"}}
    works, status = _discover(lambda: open_discovery.search(request.query, request.limit, request.year_from, request.year_to, request.scope))
    _record_search(request, "papers" if request.scope == "all" else request.scope, len(works), status)
    return {"results": serialise_open(works), "attribution": open_discovery.status()["attribution"], "provider": "open", "scope": request.scope, "sources_status": status}


@app.post("/discovery/snippets")
def discover_snippets(request: DiscoveryRequest) -> dict[str, object]:
    if request.provider != "asta":
        raise HTTPException(status_code=501, detail="Passage search over open full text arrives in Phase C. Use the Asta provider if it is enabled for this engine.")
    results = serialise(_discover(lambda: discovery.search_snippets(request.query, request.limit)))
    _record_search(request, "passages", len(results))
    return {"results": results, "attribution": discovery.status()["attribution"], "provider": "asta"}


@app.post("/discovery/published-version")
def discover_published_version(request: PublishedVersionRequest) -> dict[str, object]:
    found = _discover(lambda: open_discovery.published_version(request.doi))
    return {"doi": request.doi, "published": found, "attribution": SOURCE_REGISTRY["biorxiv"].attribution}


@app.post("/discovery/citations")
def discover_citations(request: CitationLookupRequest) -> dict[str, object]:
    works = _discover(lambda: open_discovery.citations(request.doi, request.direction, request.limit))
    return {"results": serialise_open(works), "direction": request.direction, "attribution": SOURCE_REGISTRY["opencitations"].attribution + " " + SOURCE_REGISTRY["openalex"].attribution}


@app.post("/paradigm/check")
def check_paradigm(request: ParadigmRequest) -> dict[str, object]:
    design = MethodDesign.from_dict(request.model_dump(exclude={"document_id", "pasted_segments"}))
    report = engine.check_paradigm(design)
    if request.document_id:
        engine.record_paradigm(request.document_id, design, report, request.pasted_segments)
    return report.to_dict()


@app.get("/navigator")
def navigator() -> dict[str, object]:
    return navigator_catalogue()


@app.post("/navigator/recommend")
def navigator_recommendation(request: NavigatorRequest) -> dict[str, object]:
    try:
        return navigator_recommend(request.answers)
    except NavigatorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/agent/status")
def agent_status() -> dict[str, object]:
    """Whether the research chat runs on the DeerFlow agent; without it the page answers from local sources only."""
    return research_agent.status() if research_agent else {"enabled": False}


@app.post("/agent/chat")
async def agent_chat(request: AgentChatRequest) -> StreamingResponse:
    """One student turn with the research agent, as Server-Sent Events: thread, step, notice, reply, error."""
    if research_agent is None:
        raise HTTPException(status_code=503, detail="The research agent is not configured. Set MWENZA_DEERFLOW_URL and MWENZA_DEERFLOW_TOKEN.")
    agent = research_agent

    async def events():
        async for event in agent.chat(request.message, request.thread_id, request.private, [item.model_dump() for item in request.files]):
            name = event.pop("event")
            yield f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/reproducer/statistics")
def reproducer_statistics(request: StatisticsCheckRequest) -> dict[str, object]:
    return check_reported_statistics(request.text)


@app.post("/reproducer/sample-size")
def reproducer_sample_size(request: SampleSizeRequest) -> dict[str, object]:
    try:
        return check_sample_size(request.design, request.parameters, request.reported_n)
    except SampleSizeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


MAX_AGENT_UPLOAD = 50 * 1024 * 1024


@app.post("/agent/upload")
async def agent_upload(file: UploadFile = File(...), thread_id: str | None = Query(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$"), private: bool = Query(default=False)) -> dict[str, object]:
    """Attach a data file to the research chat; the agent and the sandbox read it from the chat's uploads."""
    if research_agent is None:
        raise HTTPException(status_code=503, detail="The research agent is not configured.")
    content = await file.read(MAX_AGENT_UPLOAD + 1)
    if len(content) > MAX_AGENT_UPLOAD:
        raise HTTPException(status_code=413, detail="The file is larger than 50 MB.")
    try:
        return await research_agent.upload(file.filename or "upload", content, thread_id, private)
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
