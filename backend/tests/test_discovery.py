import json

import httpx
import pytest
from fastapi.testclient import TestClient

from mwenza_engine.discovery import DiscoveryConfig, DiscoveryError, LiteratureDiscovery

PAPERS = {"total": 2, "data": [
    {"paperId": "abc123", "title": "Distance and facility delivery in Kitui County", "year": 2019, "authors": [{"name": "M. Wanjiru"}, {"name": "J. Otieno"}], "venue": "BMC Pregnancy and Childbirth", "url": "https://example.org/abc123", "abstract": "Women living more than 5 kilometres from a facility were less likely to deliver with a skilled birth attendant.", "isOpenAccess": True, "tldr": {"text": "Distance lowers skilled birth attendance."}},
    {"paperId": "def456", "title": "", "year": None, "authors": []},
]}
SNIPPETS = {"data": [{"score": 0.83, "snippet": {"text": "Household decision-making autonomy was associated with higher odds of skilled birth attendance.", "section": "Results"}, "paper": {"corpusId": 998, "title": "Decision-making autonomy and maternal care", "authors": [{"name": "R. Achieng"}], "year": 2021}}]}


def sse(message: dict) -> str:
    return f": ping - keep-alive\n\nevent: message\ndata: {json.dumps(message)}\n\n"


class FakeAsta:
    """A streamable-HTTP MCP server double that records what it was sent."""

    def __init__(self, tool_results=None, rpc_error=False):
        self.calls = []
        self.tool_results = tool_results or {}
        self.rpc_error = rpc_error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((body.get("method"), dict(request.headers)))
        if body["method"] == "initialize":
            return httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "session-1"}, text=sse({"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}}))
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if self.rpc_error:
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse({"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32602, "message": "bad arguments"}}))
        result = self.tool_results[body["params"]["name"]]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse({"jsonrpc": "2.0", "id": body["id"], "result": result}))


def discovery(fake, api_key="test-key"):
    return LiteratureDiscovery(DiscoveryConfig(enabled=True, api_key=api_key), transport=httpx.MockTransport(fake))


def test_paper_search_speaks_mcp_and_normalises_results():
    fake = FakeAsta({"search_papers_by_relevance": {"content": [{"type": "text", "text": json.dumps(PAPERS)}], "isError": False}})
    papers = discovery(fake).search_papers("skilled birth attendance Kenya", limit=5, year_from=2015)
    assert [paper.title for paper in papers] == ["Distance and facility delivery in Kitui County"]
    paper = papers[0]
    assert paper.authors == ("M. Wanjiru", "J. Otieno") and paper.year == 2019 and paper.open_access is True
    assert paper.tldr == "Distance lowers skilled birth attendance."
    methods = [method for method, _ in fake.calls]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    tool_headers = fake.calls[2][1]
    assert tool_headers["x-api-key"] == "test-key" and tool_headers["mcp-session-id"] == "session-1"
    assert tool_headers["mcp-protocol-version"] == "2025-06-18"


def test_snippet_search_reads_structured_content():
    fake = FakeAsta({"snippet_search": {"structuredContent": SNIPPETS, "content": [], "isError": False}})
    snippets = discovery(fake, api_key=None).search_snippets("decision-making autonomy")
    assert snippets[0].section == "Results" and snippets[0].score == 0.83
    assert snippets[0].paper.title == "Decision-making autonomy and maternal care" and snippets[0].paper.paper_id == "998"
    assert "x-api-key" not in fake.calls[2][1]


def test_failures_become_clear_errors():
    tool_failure = FakeAsta({"search_papers_by_relevance": {"content": [{"type": "text", "text": "quota exceeded"}], "isError": True}})
    with pytest.raises(DiscoveryError, match="quota exceeded"):
        discovery(tool_failure).search_papers("anything at all")
    with pytest.raises(DiscoveryError, match="bad arguments"):
        discovery(FakeAsta(rpc_error=True)).search_papers("anything at all")

    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(DiscoveryError) as timeout:
        LiteratureDiscovery(DiscoveryConfig(enabled=True), transport=httpx.MockTransport(slow)).search_papers("anything at all")
    assert timeout.value.status == 504 and "ASTA_API_KEY" in str(timeout.value)
    with pytest.raises(DiscoveryError) as off:
        LiteratureDiscovery(DiscoveryConfig(enabled=False)).search_papers("anything at all")
    assert off.value.status == 503


def test_api_is_off_by_default_and_reports_licence(monkeypatch):
    from mwenza_engine import api

    client = TestClient(api.app)
    status = client.get("/discovery/status").json()
    assert status["enabled"] is False and "non-commercial" in status["licence"]["summary"]
    assert client.post("/discovery/papers", json={"query": "skilled birth attendance"}).status_code == 503
    fake = FakeAsta({"search_papers_by_relevance": {"content": [{"type": "text", "text": json.dumps(PAPERS)}], "isError": False}})
    monkeypatch.setattr(api, "discovery", discovery(fake))
    body = client.post("/discovery/papers", json={"query": "skilled birth attendance", "limit": 5}).json()
    assert body["results"][0]["paper_id"] == "abc123" and "Ai2" in body["attribution"]
    assert client.post("/discovery/papers", json={"query": "x"}).status_code == 422
    scout = next(agent for agent in client.get("/agents").json()["agents"] if agent["id"] == "scout")
    assert "search_literature" in scout["tools"]
    tool = next(item for item in client.get("/capabilities").json()["tools"] if item["id"] == "search_literature")
    assert tool["approval_required"] is True
