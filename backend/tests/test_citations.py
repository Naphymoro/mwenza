from fastapi.testclient import TestClient

from mwenza_engine.citations import find_citations
from mwenza_engine.pipeline import NotebookEngine
from mwenza_engine.text import sentence_bounds

WANJIRU = (
    "Wanjiru, M. and Otieno, J. (2019). Distance and facility delivery in Kitui County, Kenya.\n\n"
    "We surveyed 812 women who had given birth in the previous two years. "
    "Women living more than 5 kilometres from a health facility were less likely to deliver with a skilled birth attendant. "
    "Overall, 46% of births in the sample were attended by skilled personnel. "
    "Household wealth was not significantly associated with skilled birth attendance after adjusting for distance."
)
ACHIENG = (
    "Achieng, R. (2021). Decision-making autonomy and maternal care in western Kenya.\n\n"
    "Women with greater household decision-making autonomy had higher odds of skilled birth attendance. "
    "Partner approval remained a strong influence on where women chose to deliver. "
    "Community health volunteers improved antenatal care attendance in the study villages."
)

# One sentence per expected verdict; the order matches EXPECTED below.
DRAFT = (
    "Women who live more than 5 kilometres from a health facility are less likely to deliver with a skilled birth attendant (Wanjiru & Otieno, 2019). "
    "In Kitui, 64% of births were attended by skilled personnel (Wanjiru & Otieno, 2019). "
    "Household wealth is significantly associated with skilled birth attendance (Wanjiru & Otieno, 2019). "
    "Achieng (2021) found that greater household decision-making autonomy raised the odds of skilled birth attendance. "
    "Mobile phone ownership improves childhood vaccination coverage (Achieng, 2021). "
    "Similar barriers to facility delivery exist in rural Uganda (Mukasa, 2018). "
    "Community health volunteers improved antenatal care attendance [1]. "
    "Previous research shows that 30% of rural women deliver at home. "
    "This study will survey 400 women in Kitui."
)
EXPECTED = ["supported", "misquoted-number", "contrasting", "supported", "unrelated", "unresolved", "supported", "needs-citation", None]


def _engine():
    engine = NotebookEngine()
    wanjiru = engine.ingest_text("Wanjiru & Otieno 2019 - Distance and facility delivery", WANJIRU, "wanjiru")
    achieng = engine.ingest_text("Achieng 2021 - Decision-making autonomy", ACHIENG, "achieng")
    return engine, wanjiru, achieng


def _verdicts(report):
    return [sentence.citations[0].verdict if sentence.citations else (sentence.flags[0] if sentence.flags else None) for sentence in report.sentences]


def test_seeded_citation_faults_are_detected():
    engine, wanjiru, achieng = _engine()
    report = engine.audit_citations(DRAFT, {wanjiru.id, achieng.id}, {"ref-1": achieng.id})
    assert _verdicts(report) == EXPECTED
    assert report.status == "needs-revision"
    supported = report.sentences[0].citations[0]
    assert supported.resolution == "auto-matched" and supported.source_id == "wanjiru"
    assert supported.passage.page == 1 and "5 kilometres" in supported.passage.quote
    assert WANJIRU[supported.passage.start:supported.passage.end] == supported.passage.quote
    assert "64" in report.sentences[1].citations[0].notes[0]
    assert report.sentences[2].citations[0].notes[0].startswith("Possible contrast")
    assert report.sentences[6].citations[0].resolution == "mapped"


def test_report_summary_lists_unresolved_keys_and_guidance():
    engine, wanjiru, achieng = _engine()
    body = engine.audit_citations(DRAFT, {wanjiru.id, achieng.id}).to_dict()
    assert {item["key"] for item in body["unresolved"]} == {"mukasa-2018", "ref-1"}
    assert body["counts"]["needs-citation"] == 1
    assert body["guidance"]["contrasting"]["ask"].endswith("?")
    assert 0 < body["supported_share"] < 1


def test_ambiguous_author_year_is_not_guessed():
    engine, wanjiru, _ = _engine()
    duplicate = engine.ingest_text("Wanjiru 2019 - Second paper", "Wanjiru (2019). Rainfall and maize yields.", "wanjiru-b")
    report = engine.audit_citations("Rainfall shapes maize yields (Wanjiru, 2019).", {wanjiru.id, duplicate.id})
    check = report.sentences[0].citations[0]
    assert check.verdict == "unresolved" and set(check.candidates) == {"wanjiru", "wanjiru-b"}


def test_sources_out_of_scope_are_not_used():
    engine, _, achieng = _engine()
    report = engine.audit_citations(DRAFT.split(". ")[0] + ".", {achieng.id})
    assert report.sentences[0].citations[0].verdict == "unresolved"


def test_citation_parsing_and_sentence_splitting():
    keys = [marker.key for marker in find_citations("As Ouma et al. (2021) showed, distance matters (see Wanjiru & Otieno, 2019, p. 4; Smith 2020a) [2-4].")]
    assert keys == ["ouma-2021", "wanjiru-2019", "smith-2020a", "ref-2", "ref-3", "ref-4"]
    assert find_citations("A sample (n = 230, 2019 data) was drawn.") == []
    text = "Ouma et al. (2021) studied Kitui, e.g. two wards. Results were mixed."
    assert [text[start:end] for start, end in sentence_bounds(text)] == ["Ouma et al. (2021) studied Kitui, e.g. two wards.", "Results were mixed."]


def test_text_source_and_audit_endpoints():
    from mwenza_engine.api import app

    client = TestClient(app)
    added = client.post("/sources/text", json={"name": "Achieng 2021", "text": ACHIENG, "source_id": "browser-achieng"})
    assert added.status_code == 200 and added.json()["id"] == "browser-achieng"
    assert client.post("/sources/text", json={"name": "x", "text": "y", "source_id": "../etc"}).status_code == 422
    response = client.post("/citations/audit", json={"text": "Community health volunteers improved antenatal care attendance [1].", "source_ids": ["browser-achieng"], "references": {"ref-1": "browser-achieng"}})
    assert response.status_code == 200
    check = response.json()["sentences"][0]["citations"][0]
    assert check["verdict"] == "supported" and check["passage"]["source_id"] == "browser-achieng"
    sceptic = next(agent for agent in client.get("/agents").json()["agents"] if agent["id"] == "skeptic")
    assert "audit_citations" in sceptic["tools"]


def test_negation_and_direction_flip_cancel_out():
    engine, _, achieng = _engine()
    agree = engine.audit_citations("Women without decision-making autonomy were less likely to use skilled birth attendance (Achieng, 2021).", {achieng.id})
    assert agree.sentences[0].citations[0].verdict != "contrasting"
    reversed_claim = engine.audit_citations("Women with greater household decision-making autonomy had lower odds of skilled birth attendance (Achieng, 2021).", {achieng.id})
    assert reversed_claim.sentences[0].citations[0].verdict == "contrasting"
