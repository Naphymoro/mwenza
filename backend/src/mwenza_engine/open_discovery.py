from __future__ import annotations

import copy
import html
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import quote

import httpx

from .discovery import DiscoveryError

CACHE_SECONDS = 24 * 3600
CACHE_SIZE = 512
REUSABLE_LICENCES = {"cc-by", "cc-by-sa", "cc0", "public-domain", "pd"}
RESTRICTED_LICENCES = ("cc-by-nc", "cc-by-nd")
LINK_ONLY_HOSTS = ("ajol.info",)
OPENALEX_SELECT = "id,doi,display_name,publication_year,authorships,primary_location,best_oa_location,open_access,abstract_inverted_index,cited_by_count,type,is_retracted,is_paratext,language"
FALLBACK_BELOW = 3
RETRIES = 2
SOURCE_WEIGHTS = {"openalex": 1.0, "doaj": 0.8, "crossref": 0.6}
CROSSREF_TYPES = ("journal-article", "proceedings-article", "book-chapter", "posted-content", "dissertation", "report")
FRONT_MATTER = re.compile(r"^(news in brief|in brief|editorial|editor'?s note|erratum|errata|correction|corrigendum|retraction notice|notice of retraction|front matter|back matter|table of contents|contents|index|issue information|masthead|letters?|book reviews?|announcements?)$", re.IGNORECASE)
DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


@dataclass(frozen=True)
class SourceInfo:
    key: str
    name: str
    licence: str
    commercial_use: bool
    attribution: str
    terms_url: str
    rate_limit: str


SOURCE_REGISTRY: dict[str, SourceInfo] = {
    "openalex": SourceInfo("openalex", "OpenAlex", "CC0 (\"all data is CC0\")", True, "Data from OpenAlex (CC0).", "https://help.openalex.org/api-reference/authentication.md",
                           "Without a key, a daily budget of 1,000 credits (about 100 searches at 10 credits each); a free key raises it 10×; heavier use is pay-as-you-go."),
    "crossref": SourceInfo("crossref", "Crossref", "Metadata usable \"for any purpose\"; some abstracts may be publisher-copyrighted", True, "Metadata from Crossref.", "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
                           "No sign-up; identify with a contact email for the polite pool. Limits are advertised in x-rate-limit headers."),
    "doaj": SourceInfo("doaj", "DOAJ", "Metadata CC0", True, "Metadata from the Directory of Open Access Journals (CC0).", "https://doaj.org/terms/", "2 requests per second, bursts of up to 5."),
    "opencitations": SourceInfo("opencitations", "OpenCitations", "CC0", True, "Citation data from OpenCitations (CC0).", "https://opencitations.net/about", "Not stated on the pages checked; requests are spaced and cached."),
}
ATTRIBUTION = "Open metadata from OpenAlex (CC0), Crossref, DOAJ (CC0) and OpenCitations (CC0)."


@dataclass
class OpenWork:
    paper_id: str
    doi: str
    title: str
    year: int | None
    authors: tuple[str, ...]
    venue: str
    url: str
    abstract: str = ""
    abstract_source: str = ""
    abstract_storable: bool = False
    abstract_licence: str = ""
    open_access: bool | None = None
    oa_url: str = ""
    oa_licence: str = ""
    fulltext_reuse: str = "unknown"
    cited_by_count: int | None = None
    link_only: bool = False
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tldr: str = ""
    retracted: bool = False
    language: str = ""
    match: str = "title or abstract"


@dataclass(frozen=True)
class OpenDiscoveryConfig:
    openalex_key: str | None = None
    contact_email: str | None = None
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "OpenDiscoveryConfig":
        return cls(os.environ.get("MWENZA_OPENALEX_KEY") or None, os.environ.get("MWENZA_CONTACT_EMAIL") or None, float(os.environ.get("MWENZA_DISCOVERY_TIMEOUT", "20")))


def normalise_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", value.strip(), flags=re.IGNORECASE).lower()


def _clean(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _title_key(title: str, year: int | None) -> str:
    return f"title:{re.sub(r'[^a-z0-9]+', ' ', title.lower()).strip()}:{year or ''}"


def _surname(authors: tuple[str, ...]) -> str:
    return authors[0].split()[-1].lower() if authors and authors[0].split() else ""


def find_doi(text: str) -> str:
    match = DOI_PATTERN.search(text or "")
    return normalise_doi(match.group(1).rstrip(".,;)]")) if match else ""


def clean_query(text: str) -> str:
    """Make free text safe for OpenAlex and Crossref.

    Wildcards are dropped (OpenAlex rejects them in stemmed search), commas,
    pipes and semicolons become spaces (in OpenAlex filters they separate
    filters or mean OR), and symbols such as emoji or # are removed. Words,
    quotes, apostrophes, hyphens, brackets and AND/OR/NOT are kept.
    """
    text = re.sub(r"[*?]", "", text or "")
    text = re.sub(r"[,|;\t\n\r]+", " ", text)
    text = re.sub(r"[^\w\s\"'’()&%:./-]", " ", text)
    if text.count('"') % 2:
        text = text.replace('"', " ")
    return re.sub(r"\s+", " ", text).strip()


def clean_doaj_query(text: str) -> str:
    """DOAJ passes queries to Elasticsearch, whose syntax breaks on most punctuation."""
    text = re.sub(r"[^\w\s\"'’-]", " ", clean_query(text))
    return re.sub(r"\s+", " ", text).strip()


def fulltext_reuse(licence: str | None) -> str:
    """Classify an open-access licence for storing full text: yes, restricted, no or unknown."""
    value = (licence or "").lower()
    if not value:
        return "unknown"
    if value in REUSABLE_LICENCES:
        return "yes"
    if value.startswith(RESTRICTED_LICENCES):
        return "restricted"
    return "no"


def _abstract_from_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words = sorted((position, word) for word, positions in index.items() for position in positions)
    return " ".join(word for _, word in words)


def _year(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None


class TTLCache:
    def __init__(self, seconds: float = CACHE_SECONDS, size: int = CACHE_SIZE, clock: Callable[[], float] = time.monotonic):
        self.seconds, self.size, self.clock = seconds, size, clock
        self.items: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: tuple) -> Any:
        with self.lock:
            entry = self.items.get(key)
            if entry is None or self.clock() - entry[0] > self.seconds:
                self.items.pop(key, None)
                return None
            self.items.move_to_end(key)
            return entry[1]

    def put(self, key: tuple, value: Any) -> None:
        with self.lock:
            self.items[key] = (self.clock(), value)
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)


class Pacer:
    """Keeps requests to one service at least ``interval`` seconds apart."""

    def __init__(self, interval: float):
        self.interval, self.last, self.lock = interval, 0.0, threading.Lock()

    def wait(self) -> None:
        with self.lock:
            delay = self.last + self.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


class OpenDiscovery:
    """Federated literature search over openly licensed scholarly metadata.

    OpenAlex, Crossref and DOAJ are queried in parallel, merged by DOI (or
    title and year), ranked by reciprocal-rank fusion, and every record says
    which source supplied it and under which licence each stored field may be
    reused. A source that fails is reported, not hidden; results from the
    others still return.
    """

    def __init__(self, config: OpenDiscoveryConfig | None = None, transport: httpx.BaseTransport | None = None, pace: bool = True):
        self.config = config or OpenDiscoveryConfig.from_env()
        agent = "Mwenza/0.1 (research notebook" + (f"; mailto:{self.config.contact_email}" if self.config.contact_email else "") + ")"
        self.client = httpx.Client(timeout=self.config.timeout, transport=transport, headers={"User-Agent": agent}, follow_redirects=True)
        self.cache = TTLCache()
        self.pacers = {"openalex": Pacer(0.1 if pace else 0), "crossref": Pacer(0.4 if pace else 0), "doaj": Pacer(0.5 if pace else 0), "opencitations": Pacer(0.5 if pace else 0)}
        self.openalex_remaining: int | None = None
        self.sleep = time.sleep

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "provider": "open",
            "sources": {key: asdict(info) for key, info in SOURCE_REGISTRY.items()},
            "openalex_key": bool(self.config.openalex_key),
            "contact_email": bool(self.config.contact_email),
            "openalex_credits_remaining": self.openalex_remaining,
            "attribution": ATTRIBUTION,
            "configure_with": "Optional: MWENZA_OPENALEX_KEY (free OpenAlex key, 10× the daily budget) and MWENZA_CONTACT_EMAIL (identifies Mwenza to Crossref and OpenAlex).",
        }

    def _get(self, source: str, url: str, params: dict[str, Any], allow_missing: bool = False) -> Any:
        """GET with pacing and retries: server errors and timeouts are retried with backoff,
        and a 429 with a short Retry-After is retried once."""
        name = SOURCE_REGISTRY[source].name
        clean = {key: value for key, value in params.items() if value not in (None, "")}
        for attempt in range(RETRIES + 1):
            self.pacers[source].wait()
            try:
                response = self.client.get(url, params=clean)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < RETRIES:
                    self.sleep(0.5 * (attempt + 1))
                    continue
                raise DiscoveryError(f"{name} did not respond in time." if isinstance(exc, httpx.TimeoutException) else f"Could not reach {name}: {exc}", 504 if isinstance(exc, httpx.TimeoutException) else 502) from exc
            if source == "openalex" and response.headers.get("x-ratelimit-remaining", "").isdigit():
                self.openalex_remaining = int(response.headers["x-ratelimit-remaining"])
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "")
                budget_spent = source == "openalex" and response.headers.get("x-ratelimit-remaining") == "0"
                if not budget_spent and retry_after.isdigit() and int(retry_after) <= 5 and attempt < RETRIES:
                    self.sleep(int(retry_after))
                    continue
                if budget_spent:
                    reset = response.headers.get("x-ratelimit-reset", "")
                    when = f" It resets in about {max(1, round(int(reset) / 3600))} hour(s)." if reset.isdigit() else ""
                    hint = " A free key (MWENZA_OPENALEX_KEY) gives ten times the budget." if not self.config.openalex_key else ""
                    raise DiscoveryError(f"OpenAlex's daily budget for this engine is used up.{when}{hint}", 429)
                raise DiscoveryError(f"{name} is limiting requests; try again shortly.", 429)
            if response.status_code in {401, 403} and source == "openalex" and self.config.openalex_key:
                raise DiscoveryError("OpenAlex rejected the configured MWENZA_OPENALEX_KEY.", 502)
            if response.status_code == 404 and allow_missing:
                return None
            if response.status_code >= 500 and attempt < RETRIES:
                self.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                detail = ""
                try:
                    detail = str(response.json().get("message", ""))[:160]
                except ValueError:
                    pass
                raise DiscoveryError(f"{name} returned HTTP {response.status_code}{': ' + detail if detail else ''}.", 502)
            return response.json()
        raise DiscoveryError(f"{name} did not answer after {RETRIES + 1} attempts.", 502)

    def _cached(self, key: tuple, fetch: Callable[[], Any]) -> Any:
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        value = fetch()
        self.cache.put(key, value)
        return value

    def _openalex_params(self, **params: Any) -> dict[str, Any]:
        return {**params, "api_key": self.config.openalex_key, "mailto": self.config.contact_email}

    def _search_openalex(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list[OpenWork]:
        """Search titles and abstracts first; widen to OpenAlex's full-text search only when that finds too little."""
        years = [item for item in (f"from_publication_date:{year_from}-01-01" if year_from else "", f"to_publication_date:{year_to}-12-31" if year_to else "") if item]
        focused = self._get("openalex", "https://api.openalex.org/works", self._openalex_params(filter=",".join([f"title_and_abstract.search:{query}", "is_paratext:false", *years]), select=OPENALEX_SELECT, **{"per-page": limit}))
        works = [self._from_openalex(item) for item in focused.get("results", [])]
        if len(works) < min(FALLBACK_BELOW, limit):
            broad = self._get("openalex", "https://api.openalex.org/works", self._openalex_params(search=query, filter=",".join(["is_paratext:false", *years]), select=OPENALEX_SELECT, **{"per-page": limit}))
            known = {work.paper_id for work in works}
            for item in broad.get("results", []):
                work = self._from_openalex(item)
                if work.paper_id not in known:
                    work.match = "full text"
                    works.append(work)
        return works

    def _lookup_doi(self, doi: str) -> list[OpenWork]:
        item = self._get("openalex", f"https://api.openalex.org/works/doi:{doi}", self._openalex_params(select=OPENALEX_SELECT), allow_missing=True)
        if item:
            return [self._from_openalex(item)]
        record = self._get("crossref", f"https://api.crossref.org/works/{quote(doi, safe='/')}", {"mailto": self.config.contact_email}, allow_missing=True)
        return [self._from_crossref(record["message"])] if record and record.get("message") else []

    def _search_crossref(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list[OpenWork]:
        filters = ",".join(item for item in (*(f"type:{kind}" for kind in CROSSREF_TYPES), f"from-pub-date:{year_from}" if year_from else "", f"until-pub-date:{year_to}" if year_to else "") if item)
        payload = self._get("crossref", "https://api.crossref.org/works", {"query.bibliographic": query, "rows": limit, "filter": filters, "mailto": self.config.contact_email, "select": "DOI,title,author,issued,container-title,abstract,URL,is-referenced-by-count,type"})
        return [self._from_crossref(item) for item in payload.get("message", {}).get("items", [])]

    def _search_doaj(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list[OpenWork]:
        text = clean_doaj_query(query)
        if year_from or year_to:
            text += f" AND bibjson.year:[{year_from or 1000} TO {year_to or 2100}]"
        payload = self._get("doaj", f"https://doaj.org/api/search/articles/{quote(text, safe='')}", {"pageSize": limit})
        return [self._from_doaj(item) for item in payload.get("results", [])]

    @staticmethod
    def _from_openalex(item: dict[str, Any]) -> OpenWork:
        primary = item.get("primary_location") or {}
        best = item.get("best_oa_location") or {}
        access = item.get("open_access") or {}
        doi = normalise_doi(item.get("doi"))
        landing = primary.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else item.get("id", ""))
        abstract = _abstract_from_index(item.get("abstract_inverted_index"))
        work = OpenWork(
            paper_id=doi or item.get("id", ""), doi=doi, title=_clean(item.get("display_name") or item.get("title")), year=_year(item.get("publication_year")),
            authors=tuple(entry.get("author", {}).get("display_name", "") for entry in item.get("authorships") or [] if entry.get("author", {}).get("display_name")),
            venue=((primary.get("source") or {}).get("display_name") or ""), url=landing, abstract=abstract, abstract_source="openalex" if abstract else "",
            abstract_storable=bool(abstract), abstract_licence="CC0 as distributed by OpenAlex" if abstract else "",
            open_access=access.get("is_oa"), oa_url=best.get("pdf_url") or best.get("landing_page_url") or access.get("oa_url") or "", oa_licence=best.get("license") or "",
            fulltext_reuse=fulltext_reuse(best.get("license")) if access.get("is_oa") else "no", cited_by_count=item.get("cited_by_count"), sources=["openalex"],
            retracted=bool(item.get("is_retracted")), language=item.get("language") or "",
        )
        return work

    @staticmethod
    def _from_crossref(item: dict[str, Any]) -> OpenWork:
        doi = normalise_doi(item.get("DOI"))
        authors = tuple(" ".join(part for part in (author.get("given"), author.get("family")) if part) or author.get("name", "") for author in item.get("author") or [])
        issued = ((item.get("issued") or {}).get("date-parts") or [[None]])[0]
        abstract = _clean(item.get("abstract"))
        return OpenWork(
            paper_id=doi, doi=doi, title=_clean((item.get("title") or [""])[0]), year=_year(issued[0] if issued else None), authors=tuple(name for name in authors if name),
            venue=_clean((item.get("container-title") or [""])[0]), url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
            abstract=abstract, abstract_source="crossref" if abstract else "", abstract_storable=False, abstract_licence="May be under publisher copyright (Crossref)" if abstract else "",
            cited_by_count=item.get("is-referenced-by-count"), sources=["crossref"],
        )

    @staticmethod
    def _from_doaj(item: dict[str, Any]) -> OpenWork:
        bib = item.get("bibjson") or {}
        doi = normalise_doi(next((entry.get("id") for entry in bib.get("identifier") or [] if entry.get("type") == "doi"), ""))
        fulltext = next((link.get("url") for link in bib.get("link") or [] if link.get("type") == "fulltext"), "")
        abstract = _clean(bib.get("abstract"))
        return OpenWork(
            paper_id=doi or f"doaj:{item.get('id', '')}", doi=doi, title=_clean(bib.get("title")), year=_year(bib.get("year")),
            authors=tuple(author.get("name", "") for author in bib.get("author") or [] if author.get("name")), venue=(bib.get("journal") or {}).get("title", ""),
            url=f"https://doi.org/{doi}" if doi else fulltext, abstract=abstract, abstract_source="doaj" if abstract else "", abstract_storable=bool(abstract),
            abstract_licence="CC0 (DOAJ metadata)" if abstract else "", open_access=True, oa_url=fulltext, sources=["doaj"],
        )

    @staticmethod
    def _merge(target: OpenWork, other: OpenWork) -> None:
        target.sources = sorted(set(target.sources) | set(other.sources))
        target.title = target.title or other.title
        target.year = target.year or other.year
        target.venue = target.venue or other.venue
        if len(other.authors) > len(target.authors):
            target.authors = other.authors
        if other.abstract and (not target.abstract or (other.abstract_storable and not target.abstract_storable)):
            target.abstract, target.abstract_source, target.abstract_storable, target.abstract_licence = other.abstract, other.abstract_source, other.abstract_storable, other.abstract_licence
        if target.open_access is None:
            target.open_access = other.open_access
        target.oa_url = target.oa_url or other.oa_url
        if not target.oa_licence and other.oa_licence:
            target.oa_licence, target.fulltext_reuse = other.oa_licence, other.fulltext_reuse
        target.cited_by_count = max((value for value in (target.cited_by_count, other.cited_by_count) if value is not None), default=None)
        target.retracted = target.retracted or other.retracted
        target.language = target.language or other.language
        if other.match == "title or abstract":
            target.match = "title or abstract"

    @staticmethod
    def _finish(work: OpenWork) -> OpenWork:
        if any(host in url for url in (work.url, work.oa_url) for host in LINK_ONLY_HOSTS):
            work.link_only = True
            work.abstract_storable = False
            work.fulltext_reuse = "no"
            work.notes.append("Hosted on AJOL, whose terms do not permit reusing abstracts or full text. Read it on AJOL and cite it; Mwenza stores only the reference.")
        if work.abstract and not work.abstract_storable and not work.link_only:
            work.notes.append("The abstract may be under publisher copyright, so only the reference can be added.")
        if work.retracted:
            work.notes.insert(0, "This work has been retracted. Do not cite it as evidence; if you discuss it, say that it was retracted.")
        if work.match == "full text":
            work.notes.append("Matched only in the full text, not the title or abstract, so it may be less relevant.")
        if work.fulltext_reuse == "restricted":
            work.notes.append(f"Open access under {work.oa_licence.upper()}: reuse is limited (non-commercial or no derivatives).")
        return work

    def search(self, query: str, limit: int = 10, year_from: int | None = None, year_to: int | None = None) -> tuple[list[OpenWork], dict[str, str]]:
        doi = find_doi(query)
        remainder = re.sub(r"(https?://(dx\.)?doi\.org/|doi:)", " ", DOI_PATTERN.sub(" ", query), flags=re.IGNORECASE)
        if doi and len(clean_query(remainder)) < 3:
            works = self._cached(("doi", doi), lambda: self._lookup_doi(doi))
            if not works:
                raise DiscoveryError(f"No record was found for DOI {doi} in OpenAlex or Crossref.", 404)
            return [self._finish(work) for work in copy.deepcopy(works)], {"openalex": "ok (DOI lookup)"}
        query = clean_query(query)
        if len(query) < 3:
            raise DiscoveryError("The search has no searchable words after removing symbols and wildcards.", 422)
        searches = {"openalex": self._search_openalex, "crossref": self._search_crossref, "doaj": self._search_doaj}
        results: dict[str, list[OpenWork]] = {}
        status: dict[str, str] = {}

        def run(name: str) -> None:
            try:
                found = self._cached((name, query.lower(), limit, year_from, year_to), lambda: searches[name](query, limit, year_from, year_to))
                results[name] = copy.deepcopy(found)
                status[name] = "ok"
            except DiscoveryError as exc:
                status[name] = f"error: {exc}"

        with ThreadPoolExecutor(max_workers=len(searches)) as pool:
            list(pool.map(run, searches))
        if not results:
            raise DiscoveryError("No open source answered: " + "; ".join(f"{SOURCE_REGISTRY[name].name} {message}" for name, message in status.items()), 502)
        merged: dict[str, OpenWork] = {}
        scores: dict[str, float] = {}
        for name in searches:
            for rank, work in enumerate(results.get(name, [])):
                if not work.title or FRONT_MATTER.match(work.title.strip(" .:")):
                    continue
                key = work.doi or _title_key(work.title, work.year)
                if key in merged:
                    self._merge(merged[key], work)
                else:
                    merged[key] = work
                scores[key] = scores.get(key, 0.0) + SOURCE_WEIGHTS[name] / (60 + rank)
        ranked: list[OpenWork] = []
        for key in sorted(merged, key=lambda key: scores[key], reverse=True):
            work = merged[key]
            twin = next((kept for kept in ranked if self._same_work(kept, work)), None)
            if twin is None:
                ranked.append(work)
                continue
            self._merge(twin, work)
            if work.doi and work.doi != twin.doi:
                twin.notes.append(f"Also registered under DOI {work.doi}" + (f" ({work.year})." if work.year and work.year != twin.year else "."))
        return [self._finish(work) for work in ranked[:limit]], status

    @staticmethod
    def _same_work(left: OpenWork, right: OpenWork) -> bool:
        """Same normalised title, years at most one apart, and the same first author where both are known."""
        if _title_key(left.title, None) != _title_key(right.title, None):
            return False
        if left.year and right.year and abs(left.year - right.year) > 1:
            return False
        first, second = _surname(left.authors), _surname(right.authors)
        return not first or not second or first == second

    def citations(self, doi: str, direction: str = "citing", limit: int = 20) -> list[OpenWork]:
        """Works citing ``doi`` (``citing``) or cited by it (``references``), from OpenCitations, described with OpenAlex metadata."""
        doi = normalise_doi(doi)
        if not doi:
            raise DiscoveryError("A DOI is needed to look up citations.", 422)
        endpoint = "citations" if direction == "citing" else "references"
        links = self._cached(("opencitations", endpoint, doi), lambda: self._get("opencitations", f"https://api.opencitations.net/index/v2/{endpoint}/doi:{doi}", {}))
        side = "citing" if direction == "citing" else "cited"
        dois = []
        for link in links:
            match = re.search(r"doi:(\S+)", link.get(side, ""))
            if match and normalise_doi(match.group(1)) not in dois:
                dois.append(normalise_doi(match.group(1)))
        dois = [value for value in dois if "," not in value and "|" not in value][:limit]
        if not dois:
            return []
        payload = self._cached(("openalex", "dois", tuple(dois)), lambda: self._get("openalex", "https://api.openalex.org/works", self._openalex_params(filter="doi:" + "|".join(dois), **{"per-page": len(dois)})))
        described = {work.doi: work for work in (self._from_openalex(item) for item in payload.get("results", []))}
        works = []
        for value in dois:
            work = described.get(value) or OpenWork(paper_id=value, doi=value, title="", year=None, authors=(), venue="", url=f"https://doi.org/{value}", notes=["Not described in OpenAlex; open the DOI to see it."])
            work.sources = sorted(set(work.sources) | {"opencitations"})
            works.append(self._finish(work))
        return works


def serialise(works: list[OpenWork]) -> list[dict[str, Any]]:
    return [asdict(work) for work in works]
