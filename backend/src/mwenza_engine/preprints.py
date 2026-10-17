"""Preprint connectors for open discovery: arXiv, Europe PMC preprints,
Crossref posted content and AfricArXiv (Zenodo and OSF).

Each adapter maps its service's records to ``OpenWork`` with ``preprint``
set, the server named, and any published version recorded together with how
that link was established, because those links differ in reliability.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .discovery import DiscoveryError

if TYPE_CHECKING:
    from .open_discovery import OpenWork

ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
AFRICARXIV_PREFIX = "10.31730"
# DOI prefixes of well-known preprint servers, used to name the server of a Crossref record.
PREFIX_SERVERS = {
    "10.1101": "bioRxiv / medRxiv", "10.21203": "Research Square", "10.26434": "ChemRxiv", "10.2139": "SSRN", "10.31219": "OSF Preprints",
    "10.31234": "PsyArXiv", "10.31235": "SocArXiv", "10.20944": "Preprints.org", "10.22541": "Authorea", "10.48550": "arXiv",
    AFRICARXIV_PREFIX: "AfricArXiv (OSF)", "10.5194": "Copernicus (EGUsphere)", "10.21955": "Gates Open Research",
}
REUSABLE_TEXT = {"cc-by", "cc-by-sa", "cc0", "public-domain", "pd"}


def licence_code(value: str | None) -> str:
    """Normalise licence strings ("cc by", "CC-BY-4.0", a Creative Commons URL) to codes such as cc-by or cc-by-nc-nd."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "publicdomain/zero" in text or text.startswith("cc0") or text == "cc-zero":
        return "cc0"
    match = re.search(r"licenses/([a-z-]+)/", text)
    if match:
        return "cc-" + match.group(1)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-\d+(\.\d+)?$", "", text)
    return text if text.startswith("cc") else text


def _prefix(doi: str) -> str:
    return doi.split("/", 1)[0] if "/" in doi else ""


def arxiv_query(query: str, year_from: int | None, year_to: int | None) -> str:
    """Build an arXiv search_query: every phrase and word must appear (AND), across all fields."""
    phrases = re.findall(r'"([^"]+)"', query)
    rest = re.sub(r'"[^"]*"', " ", query)
    words = [word for word in re.findall(r"[\w-]+", rest) if word.upper() not in {"AND", "OR", "NOT"}]
    terms = [f'all:"{phrase.strip()}"' for phrase in phrases if phrase.strip()] + [f"all:{word}" for word in words]
    if year_from or year_to:
        terms.append(f"submittedDate:[{year_from or 1991}01010000 TO {year_to or 2100}12312359]")
    return " AND ".join(terms)


def epmc_query(query: str, year_from: int | None, year_to: int | None) -> str:
    text = re.sub(r"[^\w\s\"'’()-]", " ", query)
    if text.count('"') % 2:
        text = text.replace('"', " ")
    text = re.sub(r"\s+", " ", text).strip()
    parts = [f"({text})", "SRC:PPR"]
    if year_from or year_to:
        parts.append(f"PUB_YEAR:[{year_from or 1900} TO {year_to or 2100}]")
    return " AND ".join(parts)


class PreprintSources:
    """Mixed into ``OpenDiscovery``; relies on its ``_get``, ``_finish``-free mappers and ``config``."""

    def _search_arxiv(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list["OpenWork"]:
        search = arxiv_query(query, year_from, year_to)
        if not search:
            return []
        text = self._get("arxiv", "https://export.arxiv.org/api/query", {"search_query": search, "sortBy": "relevance", "max_results": limit}, as_text=True)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise DiscoveryError("arXiv returned a response that could not be read.", 502) from exc
        works = []
        for entry in root.findall("a:entry", ATOM):
            entry_id = (entry.findtext("a:id", "", ATOM) or "").strip()
            if "/api/errors" in entry_id:
                raise DiscoveryError(f"arXiv rejected the query: {' '.join((entry.findtext('a:summary', '', ATOM) or '').split())[:160]}", 502)
            works.append(self._from_arxiv(entry))
        return works

    def _from_arxiv(self, entry: ET.Element) -> "OpenWork":
        from .open_discovery import OpenWork, _clean, _year, normalise_doi

        abs_url = (entry.findtext("a:id", "", ATOM) or "").strip()
        arxiv_id = re.sub(r"v\d+$", "", abs_url.rsplit("/abs/", 1)[-1])
        links = {(link.get("title") or link.get("rel")): link.get("href", "") for link in entry.findall("a:link", ATOM)}
        published_doi = normalise_doi(entry.findtext("arxiv:doi", "", ATOM))
        journal = " ".join((entry.findtext("arxiv:journal_ref", "", ATOM) or "").split())
        abstract = " ".join((entry.findtext("a:summary", "", ATOM) or "").split())
        work = OpenWork(
            paper_id=f"arxiv:{arxiv_id}", doi=f"10.48550/arxiv.{arxiv_id}".lower(), title=_clean(entry.findtext("a:title", "", ATOM)),
            year=_year((entry.findtext("a:published", "", ATOM) or "")[:4]), authors=tuple(" ".join((author.findtext("a:name", "", ATOM) or "").split()) for author in entry.findall("a:author", ATOM)),
            venue="arXiv", url=f"https://arxiv.org/abs/{arxiv_id}", abstract=abstract, abstract_source="arxiv" if abstract else "", abstract_storable=bool(abstract),
            abstract_licence="CC0 (arXiv metadata)" if abstract else "", open_access=True, oa_url=links.get("pdf", ""), fulltext_reuse="unknown", sources=["arxiv"],
            preprint=True, server="arXiv",
        )
        if published_doi or journal:
            work.published_doi, work.published_venue = published_doi, journal
            work.published_url = f"https://doi.org/{published_doi}" if published_doi else ""
            work.published_source = "reported by the authors on arXiv"
        return work

    def _search_europepmc(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list["OpenWork"]:
        payload = self._get("europepmc", "https://www.ebi.ac.uk/europepmc/webservices/rest/search", {"query": epmc_query(query, year_from, year_to), "format": "json", "resultType": "core", "pageSize": limit})
        return [self._from_europepmc(item) for item in (payload.get("resultList") or {}).get("result", [])]

    def _from_europepmc(self, item: dict[str, Any]) -> "OpenWork":
        from .open_discovery import OpenWork, _clean, _year, fulltext_reuse, normalise_doi

        doi = normalise_doi(item.get("doi"))
        licence = licence_code(item.get("license"))
        abstract = _clean(item.get("abstractText"))
        storable = bool(abstract) and licence in REUSABLE_TEXT
        authors = tuple(author.get("fullName", "") for author in (item.get("authorList") or {}).get("author", []) if author.get("fullName")) or tuple(name.strip() for name in (item.get("authorString") or "").rstrip(".").split(",") if name.strip())
        server = (item.get("bookOrReportDetails") or {}).get("publisher") or PREFIX_SERVERS.get(_prefix(doi), "Preprint server")
        work = OpenWork(
            paper_id=doi or f"ppr:{item.get('id', '')}", doi=doi, title=_clean(item.get("title")), year=_year(item.get("pubYear")), authors=authors, venue=server,
            url=f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/PPR/{item.get('id', '')}", abstract=abstract, abstract_source="europepmc" if abstract else "",
            abstract_storable=storable, abstract_licence=(f"{licence.upper()} (preprint licence via Europe PMC)" if storable else f"Preprint licence {licence.upper() or 'not stated'}: abstract not stored") if abstract else "",
            open_access=item.get("isOpenAccess") == "Y" or bool(licence), oa_licence=licence, fulltext_reuse=fulltext_reuse(licence) if licence else "unknown",
            cited_by_count=item.get("citedByCount"), sources=["europepmc"], preprint=True, server=server,
        )
        for link in (item.get("commentCorrectionList") or {}).get("commentCorrection", []):
            if link.get("type") == "Preprint of":
                work.published_venue = " ".join((link.get("reference") or "").split())
                work.published_url = f"https://europepmc.org/article/{link.get('source', 'MED')}/{link.get('id', '')}"
                work.published_source = "Europe PMC (matched on title and first author)"
                break
        return work

    def _search_crossref_preprints(self, query: str, limit: int, year_from: int | None, year_to: int | None, prefix: str = "") -> list["OpenWork"]:
        filters = ",".join(item for item in ("type:posted-content", f"prefix:{prefix}" if prefix else "", f"from-pub-date:{year_from}" if year_from else "", f"until-pub-date:{year_to}" if year_to else "") if item)
        payload = self._get("crossref", "https://api.crossref.org/works", {"query.bibliographic": query, "rows": limit, "filter": filters, "mailto": self.config.contact_email, "select": "DOI,title,author,issued,container-title,abstract,URL,is-referenced-by-count,type,publisher,license,relation"})
        return [self._from_crossref_preprint(item) for item in payload.get("message", {}).get("items", [])]

    def _from_crossref_preprint(self, item: dict[str, Any]) -> "OpenWork":
        from .open_discovery import fulltext_reuse, normalise_doi

        work = self._from_crossref(item)
        work.preprint = True
        work.server = PREFIX_SERVERS.get(_prefix(work.doi), item.get("publisher") or "Preprint server")
        work.venue = work.server
        licences = [licence_code(entry.get("URL")) for entry in item.get("license") or []]
        if licences:
            work.oa_licence = licences[0]
            work.fulltext_reuse = fulltext_reuse(licences[0])
            work.open_access = True
        published = ((item.get("relation") or {}).get("is-preprint-of") or [{}])[0]
        if published.get("id-type", "doi") == "doi" and published.get("id"):
            work.published_doi = normalise_doi(published["id"])
            work.published_url = f"https://doi.org/{work.published_doi}"
            work.published_source = "Crossref (registered by the preprint server)"
        return work

    def _search_africarxiv(self, query: str, limit: int, year_from: int | None, year_to: int | None) -> list["OpenWork"]:
        from .open_discovery import clean_doaj_query

        text = clean_doaj_query(query)
        if year_from or year_to:
            text += f" AND publication_date:[{year_from or 1900}-01-01 TO {year_to or 2100}-12-31]"
        zenodo = self._get("zenodo", "https://zenodo.org/api/records", {"communities": "africarxiv", "q": text, "type": "publication", "size": limit})
        works = [self._from_zenodo(item) for item in (zenodo.get("hits") or {}).get("hits", [])]
        return works + self._search_crossref_preprints(query, limit, year_from, year_to, prefix=AFRICARXIV_PREFIX)

    def _from_zenodo(self, item: dict[str, Any]) -> "OpenWork":
        from .open_discovery import OpenWork, _clean, _year, fulltext_reuse, normalise_doi

        meta = item.get("metadata") or {}
        doi = normalise_doi(item.get("doi") or meta.get("doi"))
        licence = licence_code((meta.get("license") or {}).get("id"))
        abstract = _clean(meta.get("description"))
        storable = bool(abstract) and licence in REUSABLE_TEXT
        authors = tuple(" ".join(reversed([part.strip() for part in creator.get("name", "").split(",", 1)])) for creator in meta.get("creators") or [] if creator.get("name"))
        return OpenWork(
            paper_id=doi or f"zenodo:{item.get('id', '')}", doi=doi, title=_clean(meta.get("title")), year=_year((meta.get("publication_date") or "")[:4]), authors=authors,
            venue="AfricArXiv (Zenodo)", url=f"https://doi.org/{doi}" if doi else (item.get("links") or {}).get("self_html", ""), abstract=abstract,
            abstract_source="zenodo" if abstract else "", abstract_storable=storable,
            abstract_licence=(f"{licence.upper()} (record licence on Zenodo)" if storable else f"Record licence {licence.upper() or 'not stated'}: abstract not stored") if abstract else "",
            open_access=True, oa_url=(item.get("links") or {}).get("self_html", ""), oa_licence=licence, fulltext_reuse=fulltext_reuse(licence) if licence else "unknown",
            sources=["africarxiv"], preprint=True, server="AfricArXiv (Zenodo)",
        )

    def published_version(self, doi: str) -> dict[str, str] | None:
        """Ask the bioRxiv/medRxiv API whether a 10.1101 preprint has been published; None when it has not (or the DOI is not theirs)."""
        from .open_discovery import normalise_doi

        doi = normalise_doi(doi)
        if not doi.startswith("10.1101/"):
            raise DiscoveryError("Published-version lookup is available for bioRxiv and medRxiv DOIs (10.1101/...).", 422)
        for server in ("biorxiv", "medrxiv"):
            payload = self._cached(("biorxiv-pubs", server, doi), lambda server=server: self._get("biorxiv", f"https://api.biorxiv.org/pubs/{server}/{quote(doi, safe='/')}", {}))
            for record in payload.get("collection") or []:
                if record.get("published_doi"):
                    published = normalise_doi(record["published_doi"])
                    return {"published_doi": published, "published_venue": record.get("published_journal", ""), "published_url": f"https://doi.org/{published}", "published_source": f"{record.get('preprint_platform', server)} API", "server": record.get("preprint_platform", server)}
        return None
