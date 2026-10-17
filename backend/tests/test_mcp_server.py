import json

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from mwenza_engine.mcp_server import build_server
from test_citations import ACHIENG, DRAFT, EXPECTED, WANJIRU
from test_golden_thread import COHERENT
from test_open_discovery import FIRST_DOI, FakeOpenApis, discovery
from test_paradigm import SEEDED


def run(scenario):
    """Connect the official MCP client to Mwenza's server in memory and run one scenario."""
    server = build_server(discovery(FakeOpenApis()))

    async def main():
        async with Client(server) as client:
            return await scenario(client)

    return anyio.run(main)


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


def test_tools_are_listed_with_read_only_annotations():
    async def scenario(client):
        return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in run(scenario)}
    assert set(tools) == {"search_literature", "lookup_doi", "get_citations", "check_published_version", "check_golden_thread", "check_paradigm_fit", "navigate_methodology", "audit_citations"}
    assert all(tool.annotations.read_only_hint for tool in tools.values())
    assert tools["search_literature"].annotations.open_world_hint and not tools["audit_citations"].annotations.open_world_hint
    assert set(tools["search_literature"].input_schema["properties"]) == {"query", "scope", "limit", "year_from", "year_to"}


def test_server_instructions_carry_the_citation_rules():
    async def scenario(client):
        return client.instructions or ""

    instructions = run(scenario)
    assert "not peer reviewed" in instructions and "retracted" in instructions and "abstract_storable" in instructions


def test_search_literature_returns_compact_licensed_records():
    async def scenario(client):
        return payload(await client.call_tool("search_literature", {"query": "malaria transmission Africa", "scope": "preprints", "limit": 20}))

    body = run(scenario)
    assert body["results"] and all(work["preprint"] for work in body["results"])
    assert {"title", "doi", "abstract_storable", "fulltext_reuse", "server", "notes"} <= set(body["results"][0])
    assert "paper_id" not in body["results"][0] and "CC0" in body["attribution"]
    assert set(body["sources_status"]) == {"openalex", "crossref", "europepmc", "arxiv", "africarxiv"}


def test_doi_citations_and_published_version_tools():
    async def scenario(client):
        found = payload(await client.call_tool("lookup_doi", {"doi": f"https://doi.org/{FIRST_DOI}"}))
        cited = payload(await client.call_tool("get_citations", {"doi": FIRST_DOI}))
        published = payload(await client.call_tool("check_published_version", {"doi": "10.1101/2020.04.14.20065771"}))
        return found, cited, published

    found, cited, published = run(scenario)
    assert found["result"]["doi"] == FIRST_DOI
    assert len(cited["results"]) == 2 and cited["direction"] == "citing"
    assert published["published"]["published_doi"] == "10.1038/s41467-020-18450-4"


def test_tool_errors_are_reported_not_raised():
    async def scenario(client):
        symbols = await client.call_tool("search_literature", {"query": "## ** !!"})
        wrong_doi = await client.call_tool("check_published_version", {"doi": "10.21203/rs.3.rs-1/v1"})
        bad_scope = await client.call_tool("search_literature", {"query": "malaria", "scope": "everything"})
        return symbols, wrong_doi, bad_scope

    symbols, wrong_doi, bad_scope = run(scenario)
    assert symbols.is_error and "no searchable words" in symbols.content[0].text
    assert wrong_doi.is_error and "10.1101" in wrong_doi.content[0].text
    assert bad_scope.is_error


def test_methodology_tools_match_the_engine():
    async def scenario(client):
        design = {key: list(value) if isinstance(value, tuple) else value for key, value in COHERENT.__dict__.items()}
        thread = payload(await client.call_tool("check_golden_thread", {"design": design}))
        flawed = SEEDED["interpretivism with a quantitative survey"][0]
        method = payload(await client.call_tool("check_paradigm_fit", {"design": {key: list(value) if isinstance(value, tuple) else value for key, value in flawed.__dict__.items()}}))
        audit = payload(await client.call_tool("audit_citations", {
            "text": DRAFT,
            "sources": [{"name": "Wanjiru & Otieno 2019 - Distance and facility delivery", "text": WANJIRU}, {"name": "Achieng 2021 - Decision-making autonomy", "text": ACHIENG, "id": "achieng"}],
            "references": {"ref-1": "achieng"},
        }))
        return thread, method, audit

    thread, method, audit = run(scenario)
    assert thread["status"] == "aligned"
    assert method["status"] == "needs-revision" and any(issue["check"] == "paradigm-approach" for issue in method["issues"])
    verdicts = [sentence["citations"][0]["verdict"] if sentence["citations"] else (sentence["flags"][0] if sentence["flags"] else None) for sentence in audit["sentences"]]
    assert verdicts == EXPECTED


def test_navigator_tool_walks_the_tree():
    async def scenario(client):
        first = payload(await client.call_tool("navigate_methodology", {}))
        design = payload(await client.call_tool("navigate_methodology", {"answers": ["explore", "lived"]}))
        bad = await client.call_tool("navigate_methodology", {"answers": ["nonsense"]})
        return first, design, bad

    first, design, bad = run(scenario)
    assert not first["complete"] and first["next"]["id"] == "start"
    assert design["complete"] and design["design"]["key"] == "phenomenology"
    assert bad.is_error and "not an option" in bad.content[0].text


def test_data_sources_resource_lists_licences():
    async def scenario(client):
        return await client.read_resource("mwenza://data-sources")

    contents = run(scenario).contents[0]
    sources = json.loads(contents.text)
    assert {"openalex", "arxiv", "europepmc", "africarxiv"} <= set(sources) and "CC0" in sources["arxiv"]["licence"]


def test_request_urls_with_keys_are_not_logged():
    import logging

    build_server(discovery(FakeOpenApis()))
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
