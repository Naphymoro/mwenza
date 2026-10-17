import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from mwenza_engine.discovery import DiscoveryError
from mwenza_engine.open_discovery import OpenDiscovery, OpenDiscoveryConfig, clean_doaj_query, clean_query, find_doi, fulltext_reuse, normalise_doi

FIXTURES = Path(__file__).parent / "fixtures" / "open_discovery"
FIRST_DOI = "10.1155/2017/9740196"
SHARED_DOI = "10.1371/journal.pone.0162006"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeOpenApis:
    """Routes requests by host to responses recorded from the real APIs (trimmed)."""

    def __init__(self, failing=(), status=500):
        self.requests = []
        self.failing, self.status = set(failing), status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        name = {"api.openalex.org": "openalex", "api.crossref.org": "crossref", "doaj.org": "doaj", "api.opencitations.net": "opencitations"}[host]
        if name in self.failing:
            return httpx.Response(self.status, json={"error": "unavailable"})
        if name == "openalex" and "doi:" in request.url.params.get("filter", ""):
            return httpx.Response(200, json={"results": [dict(fixture("openalex_search.json")["results"][0], doi="https://doi.org/10.1186/s12884-025-07164-4", display_name="A citing paper about facility delivery")]})
        body = {"openalex": "openalex_search.json", "crossref": "crossref_search.json", "doaj": "doaj_search.json", "opencitations": "opencitations_citations.json"}[name]
        headers = {"x-ratelimit-remaining": "990"} if name == "openalex" else {}
        return httpx.Response(200, json=fixture(body), headers=headers)

    def sent(self, host):
        return [request for request in self.requests if request.url.host == host]


def discovery(fake, **config):
    engine = OpenDiscovery(OpenDiscoveryConfig(**config), transport=httpx.MockTransport(fake), pace=False)
    engine.sleep = lambda seconds: None
    return engine


def by_doi(works):
    return {work.doi: work for work in works}


def test_federated_search_merges_by_doi_and_records_sources():
    works, status = discovery(FakeOpenApis()).search("skilled birth attendance Kenya", limit=20)
    assert status == {"openalex": "ok", "crossref": "ok", "doaj": "ok"}
    found = by_doi(works)
    assert len(found) == len([work.doi for work in works if work.doi])
    assert found[FIRST_DOI].sources == ["crossref", "openalex"]
    assert found[SHARED_DOI].sources == ["doaj", "openalex"]
    assert works[0].doi in {FIRST_DOI, SHARED_DOI}


def test_each_field_carries_its_licence():
    found = by_doi(discovery(FakeOpenApis()).search("skilled birth attendance Kenya", limit=20)[0])
    first = found[FIRST_DOI]
    assert first.abstract_source == "openalex" and first.abstract_storable and "CC0" in first.abstract_licence
    assert first.oa_licence == "cc-by" and first.fulltext_reuse == "yes"
    shared = found[SHARED_DOI]
    assert shared.fulltext_reuse == "restricted" and any("CC-BY-NC" in note for note in shared.notes)
    crossref_only = [work for work in found.values() if work.sources == ["crossref"] and work.abstract]
    assert crossref_only and all(not work.abstract_storable and "publisher copyright" in work.notes[0] for work in crossref_only)
    ajol = found["10.4314/example.v1i1.1"]
    assert ajol.link_only and not ajol.abstract_storable and ajol.fulltext_reuse == "no" and "AJOL" in ajol.notes[0]


def test_year_filters_and_no_contact_details_unless_configured():
    fake = FakeOpenApis()
    discovery(fake).search("maternal care", limit=5, year_from=2015)
    openalex, crossref, doaj = fake.sent("api.openalex.org")[0], fake.sent("api.crossref.org")[0], fake.sent("doaj.org")[0]
    assert openalex.url.params["filter"] == "title_and_abstract.search:maternal care,is_paratext:false,from_publication_date:2015-01-01"
    assert "is_retracted" in openalex.url.params["select"]
    assert crossref.url.params["filter"].endswith(",from-pub-date:2015")
    assert "bibjson.year:[2015 TO 2100]" in unquote(doaj.url.path)
    assert "mailto" not in openalex.url.params and "api_key" not in openalex.url.params and "mailto" not in crossref.url.params
    assert "mailto" not in openalex.headers["user-agent"]
    keyed = FakeOpenApis()
    discovery(keyed, openalex_key="free-key", contact_email="library@example.org").search("maternal care", limit=5)
    request = keyed.sent("api.openalex.org")[0]
    assert request.url.params["api_key"] == "free-key" and request.url.params["mailto"] == "library@example.org"
    assert "mailto:library@example.org" in request.headers["user-agent"]


def test_same_title_under_two_dois_is_listed_once():
    engine = discovery(FakeOpenApis())
    original = engine._search_crossref

    def with_duplicate(*args):
        works = original(*args)
        twin = type(works[0])(**{**works[0].__dict__, "doi": "10.9999/duplicate", "paper_id": "10.9999/duplicate", "sources": ["crossref"], "notes": []})
        return works + [twin]

    engine._search_crossref = with_duplicate
    works, _ = engine.search("skilled birth attendance Kenya", limit=20)
    titles = [(work.title.lower(), work.year) for work in works]
    assert len(titles) == len(set(titles))
    assert any("Also registered under DOI 10.9999/duplicate." in work.notes for work in works)


def test_a_failing_source_is_reported_and_the_rest_still_answer():
    works, status = discovery(FakeOpenApis(failing={"doaj"})).search("skilled birth attendance Kenya")
    assert works and status["doaj"].startswith("error:") and status["openalex"] == "ok"
    with pytest.raises(DiscoveryError) as everything_down:
        discovery(FakeOpenApis(failing={"openalex", "crossref", "doaj"})).search("skilled birth attendance Kenya")
    assert everything_down.value.status == 502


def test_openalex_budget_exhaustion_suggests_a_key():
    fake = FakeOpenApis()
    original = fake.__call__

    def spent(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "26000"}, json={"error": "limit"})
        return original(request)

    works, status = discovery(spent).search("skilled birth attendance Kenya")
    assert "daily budget" in status["openalex"] and "7 hour" in status["openalex"] and "MWENZA_OPENALEX_KEY" in status["openalex"] and works


def test_cache_avoids_repeat_calls_and_is_not_mutated_by_merging():
    fake = FakeOpenApis()
    engine = discovery(fake)
    first = by_doi(engine.search("Skilled birth attendance Kenya", limit=20)[0])
    calls = len(fake.requests)
    second = by_doi(engine.search("skilled birth attendance kenya", limit=20)[0])
    assert len(fake.requests) == calls
    assert second[FIRST_DOI].sources == first[FIRST_DOI].sources == ["crossref", "openalex"]
    assert second[SHARED_DOI].notes == first[SHARED_DOI].notes and len(second[SHARED_DOI].notes) == 1
    assert engine.status()["openalex_credits_remaining"] == 990


def test_citations_come_from_opencitations_and_are_described_by_openalex():
    fake = FakeOpenApis()
    works = discovery(fake).citations(f"https://doi.org/{FIRST_DOI}")
    assert [work.doi for work in works] == ["10.3126/cdj.v32i46.77010", "10.1186/s12884-025-07164-4"]
    assert works[1].title == "A citing paper about facility delivery" and "opencitations" in works[1].sources
    assert works[0].title == "" and "Not described in OpenAlex" in works[0].notes[0]
    assert fake.sent("api.opencitations.net")[0].url.path.endswith(f"/citations/doi:{FIRST_DOI}")


def test_licence_and_doi_helpers():
    assert [fulltext_reuse(value) for value in ("cc-by", "cc-by-nc-sa", "publisher-specific-oa", None)] == ["yes", "restricted", "no", "unknown"]
    assert normalise_doi("https://doi.org/10.1155/2017/9740196") == normalise_doi("DOI:10.1155/2017/9740196".lower()) == FIRST_DOI


def test_api_defaults_to_open_sources_and_records_searches(monkeypatch):
    from mwenza_engine import api

    monkeypatch.setattr(api, "open_discovery", discovery(FakeOpenApis()))
    client = TestClient(api.app)
    body = client.post("/discovery/papers", json={"query": "skilled birth attendance Kenya", "document_id": "lit-review"}).json()
    assert body["provider"] == "open" and body["sources_status"]["openalex"] == "ok" and "CC0" in body["attribution"]
    assert {"fulltext_reuse", "abstract_storable", "sources", "link_only"} <= set(body["results"][0])
    record = client.get("/provenance/lit-review").json()
    assert "1 literature search through open scholarly metadata" in record["declaration"]
    assert record["events"][0]["kind"] == "discovery-search"
    assert client.post("/discovery/snippets", json={"query": "skilled birth attendance"}).status_code == 501
    cited = client.post("/discovery/citations", json={"doi": FIRST_DOI}).json()
    assert len(cited["results"]) == 2 and "OpenCitations" in cited["attribution"]
    sources = client.get("/capabilities").json()["data_sources"]
    assert set(sources) == {"openalex", "crossref", "doaj", "opencitations"} and all(item["commercial_use"] for item in sources.values())


class Scripted:
    """Answers each request from a queue per host; records every request."""

    def __init__(self, **queues):
        self.queues = {host: list(responses) for host, responses in queues.items()}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        answer = self.queues[request.url.host].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def openalex_result(**overrides):
    return dict(fixture("openalex_search.json")["results"][0], **overrides)


def test_queries_are_cleaned_the_way_the_live_apis_require():
    assert clean_query("smartphone* health Africa?") == "smartphone health Africa"
    assert clean_query("maternal health, Kenya, distance") == "maternal health Kenya distance"
    assert clean_query("maternal|child mortality") == "maternal child mortality"
    assert clean_query("#mHealth \U0001F4F1 Africa") == "mHealth Africa"
    assert clean_query('"skilled birth attendance" Kenya') == '"skilled birth attendance" Kenya'
    assert clean_query('"unbalanced quote Kenya') == "unbalanced quote Kenya"
    assert clean_query("(maternal OR child) health; women's") == "(maternal OR child) health women's"
    assert clean_query("sant\u00e9 maternelle S\u00e9n\u00e9gal") == "sant\u00e9 maternelle S\u00e9n\u00e9gal"
    assert clean_doaj_query("Ubuntu philosophy: research (ethics) & care") == "Ubuntu philosophy research ethics care"
    assert find_doi("see https://doi.org/10.1155/2017/9740196.") == FIRST_DOI and find_doi("no doi here") == ""


def test_symbol_only_query_is_refused_clearly():
    with pytest.raises(DiscoveryError) as refused:
        discovery(FakeOpenApis()).search("** \U0001F4F1 ##")
    assert refused.value.status == 422


def test_a_pasted_doi_is_looked_up_directly_and_falls_back_to_crossref():
    found = Scripted(**{"api.openalex.org": [httpx.Response(200, json=openalex_result())]})
    works, status = discovery(found).search(f"doi:{FIRST_DOI}")
    assert [work.doi for work in works] == [FIRST_DOI] and status == {"openalex": "ok (DOI lookup)"}
    assert found.requests[0].url.path == f"/works/doi:{FIRST_DOI}" and "search" not in found.requests[0].url.params
    crossref_item = fixture("crossref_search.json")["message"]["items"][-1]
    missing = Scripted(**{"api.openalex.org": [httpx.Response(404, json={})], "api.crossref.org": [httpx.Response(200, json={"message": crossref_item})]})
    works, _ = discovery(missing).search(f"https://doi.org/{FIRST_DOI.upper()}")
    assert works[0].sources == ["crossref"] and works[0].doi == FIRST_DOI
    nothing = Scripted(**{"api.openalex.org": [httpx.Response(404, json={})], "api.crossref.org": [httpx.Response(404, json={})]})
    with pytest.raises(DiscoveryError) as unknown:
        discovery(nothing).search("10.9999/does-not-exist")
    assert unknown.value.status == 404


def test_too_few_title_matches_widen_to_full_text_and_say_so():
    engine = discovery(Scripted(**{"api.openalex.org": [
        httpx.Response(200, json={"results": [openalex_result()]}),
        httpx.Response(200, json={"results": [openalex_result(), openalex_result(id="https://openalex.org/W9", doi="https://doi.org/10.1/broad", display_name="A broad match", authorships=[])]}),
    ]}))
    works = engine._search_openalex("ubuntu ethics", 10, None, None)
    assert [work.match for work in works] == ["title or abstract", "full text"]
    assert "Matched only in the full text" in engine._finish(works[1]).notes[-1]


def test_retracted_works_are_flagged_first_and_language_is_kept():
    engine = discovery(FakeOpenApis())
    work = engine._finish(engine._from_openalex(openalex_result(is_retracted=True, language="fr")))
    assert work.retracted and work.language == "fr" and work.notes[0].startswith("This work has been retracted")


def test_transient_failures_are_retried_and_auth_failures_explained():
    flaky = Scripted(**{"api.openalex.org": [httpx.Response(503), httpx.ReadTimeout("slow"), httpx.Response(200, json={"results": [openalex_result()] * 3})]})
    assert len(discovery(flaky)._search_openalex("malaria", 3, None, None)) == 3 and len(flaky.requests) == 3
    throttled = Scripted(**{"api.openalex.org": [httpx.Response(429, headers={"retry-after": "1", "x-ratelimit-remaining": "500"}), httpx.Response(200, json={"results": [openalex_result()] * 3})]})
    assert len(discovery(throttled)._search_openalex("malaria", 3, None, None)) == 3
    down = Scripted(**{"api.openalex.org": [httpx.Response(500)] * 3})
    with pytest.raises(DiscoveryError, match="HTTP 500"):
        discovery(down)._search_openalex("malaria", 3, None, None)
    rejected = Scripted(**{"api.openalex.org": [httpx.Response(401, json={"message": "bad key"})]})
    with pytest.raises(DiscoveryError, match="rejected the configured MWENZA_OPENALEX_KEY"):
        discovery(rejected, openalex_key="wrong")._search_openalex("malaria", 3, None, None)
    bad_request = Scripted(**{"api.openalex.org": [httpx.Response(400, json={"message": "Wildcards (* or ?) require exact search"})]})
    with pytest.raises(DiscoveryError, match="Wildcards"):
        discovery(bad_request)._search_openalex("malaria", 3, None, None)


def test_same_title_one_year_apart_by_the_same_author_is_one_work():
    engine = discovery(FakeOpenApis())
    original = engine._search_openalex

    def with_version(*args):
        works = original(*args)
        twin = type(works[0])(**{**works[0].__dict__, "doi": "10.9999/preprint", "paper_id": "10.9999/preprint", "year": works[0].year + 1, "notes": [], "sources": ["openalex"]})
        other = type(works[0])(**{**works[0].__dict__, "doi": "10.9999/other", "paper_id": "10.9999/other", "year": works[0].year + 5, "notes": [], "sources": ["openalex"]})
        return works + [twin, other]

    engine._search_openalex = with_version
    works, _ = engine.search("skilled birth attendance Kenya", limit=20)
    same = [work for work in works if work.title == works[0].title or work.doi in {"10.9999/preprint", "10.9999/other"}]
    titles = {work.doi: work for work in same}
    assert "10.9999/preprint" not in titles and "10.9999/other" in titles
    assert any("Also registered under DOI 10.9999/preprint" in note for work in works for note in work.notes)


def test_front_matter_is_dropped_and_crossref_limited_to_research_types():
    fake = FakeOpenApis()
    engine = discovery(fake)
    original = engine._search_crossref

    def with_news(*args):
        works = original(*args)
        news = type(works[0])(**{**works[0].__dict__, "doi": "10.9999/news", "paper_id": "10.9999/news", "title": "News in Brief", "notes": [], "sources": ["crossref"]})
        return [news] + works

    engine._search_crossref = with_news
    works, _ = engine.search("skilled birth attendance Kenya", limit=20)
    assert all(work.title != "News in Brief" for work in works)
    discovery(fake).search("maternal care")
    assert "type:journal-article" in fake.sent("api.crossref.org")[-1].url.params["filter"]


def test_openalex_outranks_crossref_at_equal_rank():
    works, _ = discovery(FakeOpenApis()).search("skilled birth attendance Kenya", limit=20)
    first_single = next(work for work in works if len(work.sources) == 1)
    assert first_single.sources == ["openalex"]
