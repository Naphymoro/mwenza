from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from mwenza_engine.golden_thread import GoldenThreadChecker, ResearchDesign, classify_question
from mwenza_engine.pipeline import NotebookEngine

COHERENT = ResearchDesign(
    title="Skilled birth attendance in rural Kenya",
    problem="Maternal mortality remains high in rural Kenyan counties despite free maternity services, because many rural women still deliver at home without skilled birth attendance.",
    gap="Studies of free maternity services in Kenya measure facility delivery rates, but few examine how household decision-making and travel distance shape skilled birth attendance among rural women.",
    aim="To examine how household decision-making autonomy and travel distance influence skilled birth attendance among rural women in Kenya.",
    objectives=(
        "To determine the relationship between travel distance and skilled birth attendance among rural women.",
        "To assess the influence of household decision-making autonomy on skilled birth attendance among rural women.",
    ),
    questions=(
        "What is the relationship between travel distance and skilled birth attendance among rural women?",
        "To what extent does household decision-making autonomy influence skilled birth attendance among rural women?",
    ),
    hypotheses=(
        "Longer travel distance is associated with lower skilled birth attendance among rural women.",
        "Greater household decision-making autonomy is associated with higher skilled birth attendance among rural women.",
    ),
    paradigm="Positivism",
    approach="Quantitative",
    strategy="Cross-sectional household survey",
    theory="Andersen's Behavioral Model of Health Services Use",
    constructs=("travel distance", "decision-making autonomy", "skilled birth attendance"),
    data_collection=("Structured questionnaire measuring travel distance, household decision-making autonomy and skilled birth attendance",),
    analysis=("Descriptive statistics", "Multivariable logistic regression"),
)

# Each seeded break is a single, known flaw an examiner would raise.
SEEDED_BREAKS = {
    "aim drifts from the gap": (replace(COHERENT, aim="To evaluate teacher retention policies in urban secondary schools across Nairobi."), "chain"),
    "orphan research question": (replace(COHERENT, questions=COHERENT.questions + ("How do nurses perceive workload pressures in referral hospitals?",)), "objective-question"),
    "paradigm contradicts approach": (replace(COHERENT, paradigm="Interpretivism"), "paradigm-approach"),
    "analysis contradicts approach": (replace(COHERENT, analysis=("Reflexive thematic analysis",)), "approach-analysis"),
    "exploratory question in quantitative design": (replace(COHERENT, questions=COHERENT.questions + ("How do rural women experience household decision-making about skilled birth attendance?",)), "question-approach"),
    "decorative theory construct": (replace(COHERENT, constructs=COHERENT.constructs + ("health literacy",)), "theory-constructs"),
    "hypotheses in qualitative design": (replace(COHERENT, paradigm="Interpretivism", approach="Qualitative", strategy="Phenomenology", analysis=("Interpretative phenomenological analysis",)), "hypotheses-approach"),
    "strategy contradicts approach": (replace(COHERENT, strategy="Ethnography"), "strategy-approach"),
}


def test_coherent_design_has_no_errors_or_warnings():
    report = GoldenThreadChecker().check(COHERENT)
    blocking = [issue for issue in report.issues if issue.severity != "info"]
    assert blocking == [], blocking
    assert report.status == "aligned"
    assert report.alignment_score is not None and report.alignment_score >= 0.9
    assert {"problem", "gap", "aim", "obj-1", "rq-2", "h-2", "construct-3", "analysis-2"} <= {node.id for node in report.nodes}


def test_seeded_break_detection_recall():
    checker = GoldenThreadChecker()
    missed = [name for name, (design, check) in SEEDED_BREAKS.items() if check not in {issue.check for issue in checker.check(design).issues if issue.severity != "info"}]
    recall = 1 - len(missed) / len(SEEDED_BREAKS)
    assert recall == 1.0, f"alignment-detection recall {recall:.2f}; missed: {missed}"


def test_issues_teach_and_ask_rather_than_rewrite():
    report = GoldenThreadChecker().check(SEEDED_BREAKS["paradigm contradicts approach"][0])
    issue = next(item for item in report.issues if item.check == "paradigm-approach")
    assert issue.severity == "error"
    assert issue.teach and issue.ask.endswith("?")
    assert report.status == "needs-revision"


def test_too_little_text_is_unknown_not_broken():
    sparse = ResearchDesign(problem="Low uptake.", gap="Few studies.", aim="Explore uptake.", objectives=("Explore uptake.",), questions=("Why?",), approach="qualitative", analysis=("Thematic analysis",))
    report = GoldenThreadChecker().check(sparse)
    assert {edge.status for edge in report.edges if edge.relation in {"narrowed-to", "addressed-by"}} == {"unknown"}
    assert not any(issue.check == "chain" for issue in report.issues)


def test_missing_sections_and_inferred_approach():
    design = ResearchDesign(problem=COHERENT.problem, gap="", aim=COHERENT.aim, objectives=(), questions=COHERENT.questions, strategy="Cross-sectional survey", analysis=COHERENT.analysis)
    report = GoldenThreadChecker().check(design)
    assert report.approach == "quantitative" and report.approach_source == "inferred-from-strategy"
    completeness = next(issue for issue in report.issues if issue.check == "completeness" and issue.severity == "error")
    assert "research gap" in completeness.message and "objectives" in completeness.message


def test_question_classification():
    assert classify_question("How do teachers experience curriculum reform?") == "exploratory"
    assert classify_question("What is the effect of tutoring on exam scores?") == "confirmatory"
    assert classify_question("Which policies exist?") == "unclear"


def test_gap_evidence_uses_selected_sources(tmp_path: Path):
    path = tmp_path / "review.txt"
    path.write_text("Few studies examine household decision-making and travel distance as drivers of skilled birth attendance among rural women in Kenya.", encoding="utf-8")
    engine = NotebookEngine()
    source = engine.ingest(path)
    report = engine.check_golden_thread(COHERENT, {source.id})
    assert report.gap_citations and report.gap_citations[0].source_id == source.id
    unscoped = NotebookEngine().check_golden_thread(COHERENT)
    assert any(issue.check == "gap-evidence" and "No sources" in issue.message for issue in unscoped.issues)


def test_api_endpoint_and_agent_wiring():
    from mwenza_engine.api import app

    client = TestClient(app)
    payload = {key: list(value) if isinstance(value, tuple) else value for key, value in COHERENT.__dict__.items()}
    response = client.post("/golden-thread/check", json={**payload, "paradigm": "Interpretivism"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs-revision"
    assert any(issue["check"] == "paradigm-approach" for issue in body["issues"])
    preflight = client.options("/golden-thread/check", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5173"
    foreign = client.options("/golden-thread/check", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in foreign.headers
    methodologist = next(agent for agent in client.get("/agents").json()["agents"] if agent["id"] == "methodologist")
    assert "check_alignment" in methodologist["tools"]
