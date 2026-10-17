import json
from pathlib import Path

from fastapi.testclient import TestClient

from mwenza_engine.golden_thread import ResearchDesign
from mwenza_engine.pipeline import NotebookEngine
from mwenza_engine.provenance import ProvenanceLedger
from test_citations import ACHIENG, WANJIRU

OPENING = "In Kitui, 64% of births were attended by skilled personnel (Wanjiru & Otieno, 2019)."
FIXED = "In Kitui, 46% of births were attended by skilled personnel (Wanjiru & Otieno, 2019)."
PASTED = "Rural maternal health programmes across East Africa have expanded quickly since 2013, but their reach into remote households remains uneven and poorly measured."
COPIED = "Women living more than 5 kilometres from a health facility were less likely to deliver with a skilled birth attendant (Wanjiru & Otieno, 2019)."
QUOTED = "Achieng reports that “women with greater household decision-making autonomy had higher odds of skilled birth attendance” (Achieng, 2021)."
TYPED = "This study will survey 400 women across four wards of Kitui County to test both explanations."


def _session(engine: NotebookEngine, source_ids: set[str]) -> None:
    """Three recorded versions: start, additions (one pasted), then a revision after feedback."""
    versions = [
        ([OPENING], []),
        ([OPENING, PASTED, COPIED, QUOTED], [PASTED]),
        ([FIXED, PASTED, COPIED, QUOTED, TYPED], []),
    ]
    for paragraphs, pasted in versions:
        text = "\n\n".join(paragraphs)
        engine.record_citation_audit("chapter-2", text, engine.audit_citations(text, source_ids), pasted)


def _engine(ledger_path=None):
    engine = NotebookEngine(ledger_path)
    ids = {engine.ingest_text("Wanjiru & Otieno 2019", WANJIRU, "wanjiru").id, engine.ingest_text("Achieng 2021", ACHIENG, "achieng").id}
    return engine, ids


def test_paragraph_origins_feedback_and_verbatim_text():
    engine, ids = _engine()
    _session(engine, ids)
    report = engine.provenance_report("chapter-2")
    by_text = {item["text"]: item for item in report["paragraphs"]}
    opening = by_text[FIXED]
    assert opening["origin"] == "present-at-start" and opening["versions"] == 2
    assert opening["revised_after_feedback"] is True and opening["open_feedback"] == 0
    assert opening["feedback"][0]["tool"] == "citation-audit" and opening["feedback"][0]["revised_after"] is True
    assert by_text[PASTED]["origin"] == "pasted"
    assert by_text[COPIED]["origin"] == "typed"
    assert by_text[COPIED]["verbatim"] and by_text[COPIED]["verbatim"][0]["quoted"] is False
    assert by_text[QUOTED]["verbatim"][0]["quoted"] is True
    assert by_text[TYPED]["origin"] == "typed" and not by_text[TYPED]["verbatim"]
    declaration = report["declaration"]
    assert "3 citation checks" in declaration
    assert "1 pasted from outside Mwenza" in declaration
    assert "without quotation marks" in declaration
    assert "verified intact" in declaration and "open feedback" not in declaration


def test_hash_chain_detects_tampering_in_saved_ledger(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    engine, ids = _engine(path)
    _session(engine, ids)
    reloaded = ProvenanceLedger(path)
    assert reloaded.verify()["valid"] is True and len(reloaded.events) == 6
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[2])
    record["text"] = record["text"].replace("Rural", "Urban")
    lines[2] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered = ProvenanceLedger(path).verify()
    assert tampered == {"valid": False, "broken_at": 3, "reason": "stored text does not match its recorded hash"}
    record["summary"] = "edited"
    lines[2] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ProvenanceLedger(path).verify()["reason"] == "event fields or chain link do not match their hash"


def test_golden_thread_flags_attach_to_design_fields():
    engine = NotebookEngine()
    design = ResearchDesign(problem="Rural women in Kitui deliver at home without skilled birth attendance despite free maternity care.", gap="Few studies examine distance and household decision-making as drivers of skilled birth attendance in Kitui.", aim="To examine how distance and household decision-making shape skilled birth attendance in Kitui.", objectives=("To determine the relationship between distance and skilled birth attendance in Kitui.",), questions=("What is the relationship between distance and skilled birth attendance in Kitui?",), paradigm="Interpretivism", approach="Quantitative", analysis=("Logistic regression",))
    engine.record_golden_thread("proposal", design, engine.check_golden_thread(design), [])
    report = engine.provenance_report("proposal")
    paradigm = next(item for item in report["paragraphs"] if item["text"].startswith("Paradigm:"))
    assert paradigm["feedback"][0]["flags"][0]["verdict"] == "paradigm-approach"
    assert report["events"][0]["kind"] == "ai-check" and report["events"][1]["kind"] == "text-snapshot"


def test_documents_are_kept_apart_and_empty_documents_say_so():
    engine, ids = _engine()
    _session(engine, ids)
    assert engine.provenance_report("another-draft")["declaration"] == "No activity has been recorded for 'another-draft'."
    assert engine.provenance_report("another-draft")["paragraphs"] == []


def test_api_records_checks_and_serves_the_ledger():
    from mwenza_engine.api import app

    client = TestClient(app)
    client.post("/sources/text", json={"name": "Wanjiru & Otieno 2019", "text": WANJIRU, "source_id": "api-wanjiru"})
    response = client.post("/citations/audit", json={"text": OPENING, "source_ids": ["api-wanjiru"], "document_id": "api-draft", "pasted_segments": [OPENING]})
    assert response.status_code == 200
    ledger = client.get("/provenance/api-draft", params={"source_ids": ["api-wanjiru"]}).json()
    assert [event["kind"] for event in ledger["events"]] == ["ai-check", "text-snapshot"]
    assert ledger["paragraphs"][0]["origin"] == "pasted" and ledger["paragraphs"][0]["open_feedback"] == 1
    assert "1 paragraph still has open feedback from the latest check." in ledger["declaration"]
    assert ledger["integrity"]["valid"] is True
    assert client.post("/citations/audit", json={"text": OPENING, "document_id": "../x"}).status_code == 422
    assert client.get("/provenance/bad id").status_code == 422
