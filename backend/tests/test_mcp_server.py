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
    assert set(tools) == {"search_literature", "lookup_doi", "get_citations", "check_published_version", "check_golden_thread", "check_paradigm_fit", "navigate_methodology", "audit_citations", "check_reported_statistics", "check_sample_size", "run_analysis", "rerun_analysis"}
    assert all(tool.annotations.read_only_hint for name, tool in tools.items() if name not in ("run_analysis", "rerun_analysis"))
    assert not tools["run_analysis"].annotations.read_only_hint and not tools["run_analysis"].annotations.open_world_hint
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
        thread = payload(await client.call_tool("check_golden_thread", {"design": design, "wording": "researcher's own words"}))
        flawed = SEEDED["interpretivism with a quantitative survey"][0]
        method = payload(await client.call_tool("check_paradigm_fit", {"design": {key: list(value) if isinstance(value, tuple) else value for key, value in flawed.__dict__.items()}, "wording": "researcher's own words"}))
        audit = payload(await client.call_tool("audit_citations", {
            "text": DRAFT,
            "sources": [{"name": "Wanjiru & Otieno 2019 - Distance and facility delivery", "text": WANJIRU}, {"name": "Achieng 2021 - Decision-making autonomy", "text": ACHIENG, "id": "achieng"}],
            "references": {"ref-1": "achieng"}, "wording": "researcher's own words",
        }))
        return thread, method, audit

    thread, method, audit = run(scenario)
    assert thread["status"] == "aligned"
    assert method["status"] == "needs-revision" and any(issue["check"] == "paradigm-approach" for issue in method["issues"])
    verdicts = [sentence["citations"][0]["verdict"] if sentence["citations"] else (sentence["flags"][0] if sentence["flags"] else None) for sentence in audit["sentences"]]
    assert verdicts == EXPECTED
    assert thread["input_wording"] == "researcher's own words" and "confirm_with_researcher" not in thread


def test_methodology_tools_refuse_empty_input_and_flag_paraphrase():
    async def scenario(client):
        empty = await client.call_tool("check_golden_thread", {"design": {}, "wording": "agent paraphrase"})
        no_wording = await client.call_tool("check_golden_thread", {"design": {"aim": "[SYNTHETIC] To explore teacher feedback"}})
        paraphrased = payload(await client.call_tool("check_paradigm_fit", {"design": {"paradigm": "interpretivism", "strategy": "case study"}, "wording": "agent paraphrase"}))
        no_sources = await client.call_tool("audit_citations", {"text": "Rainfall shapes yields (Wanjiru, 2019).", "sources": [], "wording": "researcher's own words"})
        return empty, no_wording, paraphrased, no_sources

    empty, no_wording, paraphrased, no_sources = run(scenario)
    assert empty.is_error and "Ask the researcher" in empty.content[0].text
    assert no_wording.is_error
    assert paraphrased["input_wording"] == "agent paraphrase" and "Confirm the paraphrase" in paraphrased["confirm_with_researcher"]
    assert no_sources.is_error


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


def test_reproducer_tools_recompute_and_refuse_bad_designs():
    async def scenario(client):
        stats = payload(await client.call_tool("check_reported_statistics", {"text": "[SYNTHETIC] Age did not predict delivery, t(120) = 1.20, p = .03.", "wording": "researcher's own words"}))
        size = payload(await client.call_tool("check_sample_size", {"design": "two-means", "parameters": {"difference": 5, "sd": 10}, "reported_n": 30, "wording": "agent paraphrase"}))
        bad = await client.call_tool("check_sample_size", {"design": "proportion", "parameters": {"p": 0.5}, "wording": "researcher's own words"})
        return stats, size, bad

    stats, size, bad = run(scenario)
    assert stats["status"] == "decision-errors" and stats["input_wording"] == "researcher's own words"
    assert size["verdict"] == "too-small" and size["computed_n"] == 64 and "confirm_with_researcher" in size
    assert bad.is_error and "Cannot compute" in bad.content[0].text
