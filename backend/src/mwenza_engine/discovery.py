from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

import httpx

ASTA_URL = "https://asta-tools.allen.ai/mcp/v1"
PROTOCOL_VERSION = "2025-06-18"
PAPER_FIELDS = "title,year,authors,venue,url,abstract,isOpenAccess,publicationDate,tldr"
ASTA_LICENCE = {
    "name": "Asta Scientific Corpus Tool License Agreement",
    "url": "https://allenai.org/asta-corpus-license",
    "summary": "Academic and non-commercial research use only. The API key may not be shared outside your organisation's authorised staff. Publications that use the tool must acknowledge Ai2 as its source.",
    "key_request_url": "https://share.hsforms.com/1L4hUh20oT3mu8iXJQMV77w3ioxm",
}
ATTRIBUTION = "Literature search by the Asta Scientific Corpus Tool from Ai2 (Allen Institute for AI)."


class DiscoveryError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Paper:
    paper_id: str
    title: str
    year: int | None
    authors: tuple[str, ...]
    venue: str
    url: str
    abstract: str
    open_access: bool | None
    tldr: str = ""


@dataclass(frozen=True)
class Snippet:
    text: str
    score: float | None
    section: str
    paper: Paper


@dataclass
class DiscoveryConfig:
    enabled: bool
    url: str = ASTA_URL
    api_key: str | None = None
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "DiscoveryConfig":
        return cls(
            enabled=os.environ.get("MWENZA_ASTA", "").lower() in {"1", "on", "true", "yes"},
            url=os.environ.get("MWENZA_ASTA_URL", ASTA_URL),
            api_key=os.environ.get("ASTA_API_KEY") or None,
            timeout=float(os.environ.get("MWENZA_ASTA_TIMEOUT", "60")),
        )


class McpHttpClient:
    """Minimal Model Context Protocol client for streamable-HTTP servers.

    It speaks JSON-RPC over POST, accepts either a JSON body or a
    server-sent event stream (ignoring keep-alive comments), and keeps the
    ``Mcp-Session-Id`` when a server issues one.
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        self.url = url
        self.client = httpx.Client(timeout=timeout, transport=transport, headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL_VERSION, **(headers or {})})
        self.session_id: str | None = None
        self.initialised = False
        self.next_id = 1

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers = {"Mcp-Session-Id": self.session_id} if self.session_id else {}
        try:
            response = self.client.post(self.url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise DiscoveryError("The literature service did not respond in time. Unauthenticated access can be very slow; configure ASTA_API_KEY.", 504) from exc
        except httpx.HTTPError as exc:
            raise DiscoveryError(f"Could not reach the literature service: {exc}", 502) from exc
        if response.status_code in {401, 403}:
            raise DiscoveryError("The literature service rejected the API key.", 502)
        if response.status_code == 429:
            raise DiscoveryError("The literature service rate limit was reached. Try again later.", 429)
        if response.status_code >= 400:
            raise DiscoveryError(f"The literature service returned HTTP {response.status_code}.", 502)
        self.session_id = response.headers.get("mcp-session-id", self.session_id)
        if "id" not in payload or response.status_code == 202 or not response.content:
            return None
        message = self._parse(response)
        if "error" in message:
            raise DiscoveryError(f"The literature service reported an error: {message['error'].get('message', 'unknown error')}", 502)
        return message.get("result", {})

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            messages = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:") and line[5:].strip()]
            replies = [message for message in messages if "result" in message or "error" in message]
            if not replies:
                raise DiscoveryError("The literature service closed the stream without a result.", 502)
            return replies[-1]
        return response.json()

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": self.next_id, "method": method, **({"params": params} if params is not None else {})}
        self.next_id += 1
        return self._post(payload) or {}

    def initialise(self) -> None:
        if self.initialised:
            return
        self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "mwenza-engine", "version": "0.1.0"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.initialised = True

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.initialise()
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = " ".join(item.get("text", "") for item in result.get("content", []))
            raise DiscoveryError(f"The literature tool '{name}' failed: {text[:300] or 'no detail'}", 502)
        if "structuredContent" in result:
            return result["structuredContent"]
        texts = [item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"]
        decoded = []
        for text in texts:
            try:
                decoded.append(json.loads(text))
            except json.JSONDecodeError:
                decoded.append(text)
        return decoded[0] if len(decoded) == 1 else decoded


def _records(payload: Any) -> list[dict[str, Any]]:
    """Unwrap the list of records from the shapes a tool result may take."""
    if isinstance(payload, list):
        records: list[dict[str, Any]] = []
        for entry in payload:
            records.extend([entry] if _looks_like_record(entry) else _records(entry))
        return records
    if isinstance(payload, dict):
        if _looks_like_record(payload):
            return [payload]
        for key in ("data", "result", "results", "papers", "snippets", "items"):
            if key in payload:
                return _records(payload[key])
    return []


def _looks_like_record(item: Any) -> bool:
    return isinstance(item, dict) and bool({"title", "paperId", "corpusId", "snippet", "paper"} & set(item))


def _paper(record: dict[str, Any]) -> Paper:
    authors = tuple(author.get("name", "") if isinstance(author, dict) else str(author) for author in record.get("authors") or [])
    tldr = record.get("tldr") or ""
    journal = record.get("journal")
    venue = record.get("venue") or (journal.get("name", "") if isinstance(journal, dict) else "")
    paper_id = str(record.get("paperId") or record.get("corpusId") or record.get("corpus_id") or record.get("url") or record.get("title", ""))
    year = record.get("year")
    return Paper(
        paper_id=paper_id,
        title=(record.get("title") or "").strip(),
        year=int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None,
        authors=tuple(name for name in authors if name),
        venue=venue or "",
        url=record.get("url") or (f"https://www.semanticscholar.org/paper/{record['paperId']}" if record.get("paperId") else ""),
        abstract=(record.get("abstract") or "").strip(),
        open_access=record.get("isOpenAccess"),
        tldr=(tldr.get("text", "") if isinstance(tldr, dict) else str(tldr)).strip(),
    )


def _snippet(record: dict[str, Any]) -> Snippet:
    snippet = record.get("snippet") if isinstance(record.get("snippet"), dict) else {}
    text = snippet.get("text") or (record["snippet"] if isinstance(record.get("snippet"), str) else record.get("text", ""))
    section = snippet.get("section") or snippet.get("snippetKind") or record.get("section", "")
    score = record.get("score")
    return Snippet(text=(text or "").strip(), score=float(score) if isinstance(score, (int, float)) else None, section=str(section or ""), paper=_paper(record.get("paper") or {}))


class LiteratureDiscovery:
    """Searches published literature through Ai2's Asta Scientific Corpus Tool.

    Off unless explicitly enabled, because the corpus licence limits use to
    academic, non-commercial research and each deployment must hold its own
    key. Results are returned for the user to inspect; nothing is added to a
    notebook without the user choosing it.
    """

    def __init__(self, config: DiscoveryConfig | None = None, transport: httpx.BaseTransport | None = None):
        self.config = config or DiscoveryConfig.from_env()
        self.transport = transport
        self._client: McpHttpClient | None = None

    def status(self) -> dict[str, Any]:
        return {"enabled": self.config.enabled, "provider": "asta", "url": self.config.url, "keyed": bool(self.config.api_key), "timeout_seconds": self.config.timeout, "licence": ASTA_LICENCE, "attribution": ATTRIBUTION, "enable_with": "Set MWENZA_ASTA=on (and ASTA_API_KEY) before starting the engine."}

    def _tools(self) -> McpHttpClient:
        if not self.config.enabled:
            raise DiscoveryError("Literature search is off. Set MWENZA_ASTA=on (and ASTA_API_KEY) to enable it.", 503)
        if self._client is None:
            self._client = McpHttpClient(self.config.url, {"x-api-key": self.config.api_key} if self.config.api_key else {}, self.config.timeout, self.transport)
        return self._client

    @staticmethod
    def _date_range(year_from: int | None, year_to: int | None) -> str:
        if not year_from and not year_to:
            return ""
        return f"{year_from or ''}-{year_to or ''}"

    def search_papers(self, query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
        payload = self._tools().call_tool("search_papers_by_relevance", {"keyword": query, "fields": PAPER_FIELDS, "limit": limit, "publication_date_range": self._date_range(year_from, year_to)})
        return [paper for paper in (_paper(record) for record in _records(payload)) if paper.title][:limit]

    def search_snippets(self, query: str, limit: int = 10) -> list[Snippet]:
        payload = self._tools().call_tool("snippet_search", {"query": query, "limit": limit})
        return [snippet for snippet in (_snippet(record) for record in _records(payload)) if snippet.text][:limit]


def serialise(items: list[Paper] | list[Snippet]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]
