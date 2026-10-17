"""Mwenza's MCP server: open literature discovery and the methodology checks
as tools any MCP client (Claude Code, Claude Desktop, other agents) can call.

Run over stdio for a local client, or streamable HTTP (localhost by default):

    python -m mwenza_engine.mcp_server
    python -m mwenza_engine.mcp_server --transport http --port 8766
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .citations import CitationAuditor
from .discovery import DiscoveryError
from .golden_thread import GoldenThreadChecker, ResearchDesign
from .ingest import extract_text_file
from .open_discovery import ATTRIBUTION, SOURCE_REGISTRY, OpenDiscovery, OpenWork
from .paradigm import MethodDesign, ParadigmMethodChecker

INSTRUCTIONS = """Mwenza searches openly licensed scholarly metadata (OpenAlex, Crossref, DOAJ, OpenCitations) and preprint servers (arXiv, Europe PMC, Crossref posted content including ChemRxiv and SSRN, AfricArXiv), and checks research designs and citations.

When you use results:
- Cite works from their DOI or URL, and say which source supplied them when it matters.
- Preprints (preprint=true) are not peer reviewed. Say so, and prefer the published version when published_url is given; published_source says how that link was established.
- Never present a retracted work (retracted=true) as evidence.
- Store or quote an abstract only when abstract_storable is true; otherwise link to the work. Works with link_only=true must be read on their host site.
- Results matched only in the full text (match="full text") may be less relevant.
- The methodology checks flag what to examine; they do not replace a supervisor's judgement, and they never rewrite the researcher's text.
Data: OpenAlex, DOAJ, OpenCitations and arXiv metadata are CC0; other licences are per record."""

ABSTRACT_CHARS = 1500


def compact(work: OpenWork) -> dict[str, Any]:
    """The fields an agent needs to judge and cite a work, without internal bookkeeping."""
    result: dict[str, Any] = {
        "title": work.title, "authors": list(work.authors[:8]) + (["et al."] if len(work.authors) > 8 else []), "year": work.year, "venue": work.venue,
        "doi": work.doi, "url": work.url, "sources": work.sources, "cited_by_count": work.cited_by_count, "match": work.match,
        "abstract": work.abstract[:ABSTRACT_CHARS] + ("…" if len(work.abstract) > ABSTRACT_CHARS else ""), "abstract_storable": work.abstract_storable, "abstract_licence": work.abstract_licence,
        "open_access": work.open_access, "oa_url": work.oa_url, "oa_licence": work.oa_licence, "fulltext_reuse": work.fulltext_reuse,
        "preprint": work.preprint, "server": work.server, "retracted": work.retracted, "link_only": work.link_only, "language": work.language, "notes": work.notes,
    }
    if work.published_url:
        result["published"] = {"doi": work.published_doi, "venue": work.published_venue, "url": work.published_url, "source": work.published_source}
    return result


class DesignInput(BaseModel):
    """A research design for the golden thread check. Lists hold one item per entry."""

    problem: str = ""
    gap: str = ""
    aim: str = ""
    objectives: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    paradigm: str = ""
    approach: str = Field(default="", description="quantitative, qualitative or mixed methods")
    strategy: str = Field(default="", description="for example survey, case study, phenomenology")
    theory: str = ""
    constructs: list[str] = Field(default_factory=list)
    data_collection: list[str] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    title: str = ""


class MethodInput(BaseModel):
    """The layers of a methodology for the paradigm-method check."""

    paradigm: str = ""
    approach: str = ""
    logic: str = Field(default="", description="deductive, inductive or abductive")
    strategy: str = ""
    time_horizon: str = Field(default="", description="cross-sectional or longitudinal")
    sampling: str = ""
    sample_size: str = Field(default="", description="the sample size and how it is justified")
    data_collection: list[str] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)
    quality: list[str] = Field(default_factory=list, description="validity, reliability or trustworthiness criteria")
    hypotheses: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    claims: str = ""
    title: str = ""


class SourceInput(BaseModel):
    name: str = Field(min_length=1, max_length=300, description="Include author surname and year so author-year citations can be matched, e.g. 'Wanjiru 2019 - Distance and delivery'")
    text: str = Field(min_length=1, max_length=500_000)
    id: str = Field(default="", max_length=120, description="Optional id; use it in references to link numbered citations such as [1]")


def build_server(discovery: OpenDiscovery | None = None) -> MCPServer:
    # httpx logs full request URLs at INFO, and the OpenAlex key travels in the URL.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    engine = discovery or OpenDiscovery()
    server = MCPServer(name="mwenza", title="Mwenza research tools", instructions=INSTRUCTIONS, version="0.1.0", website_url="https://github.com/Naphymoro/mwenza")
    remote = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)
    local = ToolAnnotations(read_only_hint=True, open_world_hint=False, idempotent_hint=True)

    async def call(function, *args):
        try:
            return await anyio.to_thread.run_sync(lambda: function(*args))
        except DiscoveryError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(title="Search literature", annotations=remote)
    async def search_literature(
        query: Annotated[str, Field(min_length=3, max_length=500, description="Keywords; quotes for phrases, AND/OR/NOT allowed. A DOI is looked up directly.")],
        scope: Annotated[Literal["all", "peer-reviewed", "preprints"], Field(description="Which kinds of work to include")] = "all",
        limit: Annotated[int, Field(ge=1, le=25)] = 10,
        year_from: Annotated[int | None, Field(ge=1800, le=2100)] = None,
        year_to: Annotated[int | None, Field(ge=1800, le=2100)] = None,
    ) -> dict[str, Any]:
        """Search published papers and preprints across open scholarly sources, merged and de-duplicated, with licence, preprint and retraction information for each result."""
        works, status = await call(engine.search, query, limit, year_from, year_to, scope)
        return {"results": [compact(work) for work in works], "sources_status": status, "attribution": ATTRIBUTION}

    @server.tool(title="Look up a DOI", annotations=remote)
    async def lookup_doi(doi: Annotated[str, Field(min_length=6, max_length=300, description="A DOI or doi.org link")]) -> dict[str, Any]:
        """Return the record for one DOI from OpenAlex, falling back to Crossref."""
        works, _ = await call(engine.search, doi, 1)
        return {"result": compact(works[0]), "attribution": ATTRIBUTION}

    @server.tool(title="Get citations", annotations=remote)
    async def get_citations(
        doi: Annotated[str, Field(min_length=6, max_length=300)],
        direction: Annotated[Literal["citing", "references"], Field(description="citing: works that cite this DOI; references: works it cites")] = "citing",
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict[str, Any]:
        """Open citation links from OpenCitations, with each linked work described by OpenAlex."""
        works = await call(engine.citations, doi, direction, limit)
        return {"results": [compact(work) for work in works], "direction": direction, "attribution": SOURCE_REGISTRY["opencitations"].attribution}

    @server.tool(title="Check for a published version", annotations=remote)
    async def check_published_version(doi: Annotated[str, Field(min_length=6, max_length=300, description="A bioRxiv or medRxiv DOI (10.1101/...)")]) -> dict[str, Any]:
        """Ask the bioRxiv/medRxiv API whether a preprint has been published; published is null when it has not."""
        return {"doi": doi, "published": await call(engine.published_version, doi)}

    @server.tool(title="Check golden thread", annotations=local)
    def check_golden_thread(design: DesignInput) -> dict[str, Any]:
        """Check that a research design's problem, gap, aim, objectives, questions, theory, design and analysis hold together; returns linked elements, issues with teaching notes and a status."""
        return GoldenThreadChecker().check(ResearchDesign.from_dict(design.model_dump())).to_dict()

    @server.tool(title="Check paradigm-method fit", annotations=local)
    def check_paradigm_fit(design: MethodInput) -> dict[str, Any]:
        """Check that approach to theory, strategy, time horizon, sampling, data collection, analysis and quality criteria follow from the paradigm; conflicts include coherent alternatives."""
        return ParadigmMethodChecker().check(MethodDesign.from_dict(design.model_dump())).to_dict()

    @server.tool(title="Audit citations", annotations=local)
    def audit_citations(
        text: Annotated[str, Field(min_length=1, max_length=200_000, description="Draft text with citations such as (Ouma, 2021), Ouma (2021) or [1]")],
        sources: Annotated[list[SourceInput], Field(max_length=100, description="The cited sources, with their text")],
        references: Annotated[dict[str, str], Field(description="Optional links from citation keys (e.g. 'ref-1', 'ouma-2021') to source ids")] = {},
    ) -> dict[str, Any]:
        """Check each cited sentence against the source it cites: supported, partial, possible contrast, number not in source, unrelated or unresolved; uncited factual claims are flagged."""
        records = {}
        for index, item in enumerate(sources, 1):
            source_id = item.id or f"source-{index}"
            record = extract_text_file(Path("source.txt"), source_id, item.text.encode("utf-8"))
            record.name = item.name
            records[source_id] = record
        return CitationAuditor().audit(text, records, references).to_dict()

    @server.resource("mwenza://data-sources", name="data-sources", title="Data sources and licences", mime_type="application/json")
    def data_sources() -> str:
        """Each source Mwenza searches, with its licence, attribution and rate limit."""
        return json.dumps({key: info.__dict__ for key, info in SOURCE_REGISTRY.items()}, indent=1)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Mwenza's MCP server.")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP only. Keep 127.0.0.1 unless the server sits behind authentication.")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
