from dataclasses import replace

from fastapi.testclient import TestClient

from mwenza_engine.paradigm import MethodDesign, ParadigmMethodChecker

POSITIVIST_SURVEY = MethodDesign(
    paradigm="Positivism", approach="Quantitative", logic="Deductive", strategy="Cross-sectional household survey", time_horizon="Cross-sectional",
    sampling="Multistage stratified random sampling of households", sample_size="Cochran's formula at a 95% confidence level and 5% margin of error gives 384 women",
    data_collection=("Structured questionnaire measuring travel distance, decision-making autonomy and skilled birth attendance",),
    analysis=("Descriptive statistics", "Multivariable logistic regression"), quality=("Content validity through expert review", "Reliability using Cronbach's alpha"),
    hypotheses=("Longer travel distance is associated with lower skilled birth attendance.",), questions=("What is the relationship between travel distance and skilled birth attendance?",),
)
INTERPRETIVIST_PHENOMENOLOGY = MethodDesign(
    paradigm="Interpretivism", approach="Qualitative", logic="Inductive", strategy="Phenomenology", time_horizon="Cross-sectional",
    sampling="Purposive sampling of mothers who delivered at home", sample_size="Interviews continue until saturation, expected at 15 to 20 participants",
    data_collection=("In-depth interviews",), analysis=("Interpretative phenomenological analysis",),
    quality=("Credibility through member checking", "Transferability through thick description", "Reflexivity journal"),
    questions=("How do rural mothers experience the decision to deliver at home?",),
)
UBUNTU_PAR = MethodDesign(
    paradigm="Ubuntu", approach="Qualitative", strategy="Participatory action research with community elders", time_horizon="Cross-sectional",
    sampling="Purposive selection with the community advisory board", sample_size="Information power guides the number of talking circles",
    data_collection=("Talking circles", "Storytelling sessions"), analysis=("Thematic analysis",),
    quality=("Relational accountability through community validation", "Credibility through member checking"),
)

# One planted conflict per design, each something an examiner would query.
SEEDED = {
    "interpretivism with a quantitative survey": (replace(POSITIVIST_SURVEY, paradigm="Interpretivism"), "paradigm-approach", "error"),
    "deductive grounded theory": (replace(INTERPRETIVIST_PHENOMENOLOGY, strategy="Grounded theory", logic="Deductive", sampling="Theoretical sampling"), "logic-strategy", "error"),
    "statistics planned for a qualitative design": (replace(INTERPRETIVIST_PHENOMENOLOGY, analysis=("Logistic regression",)), "analysis-approach", "error"),
    "thematic analysis in a survey": (replace(POSITIVIST_SURVEY, analysis=("Thematic analysis",)), "analysis-approach", "error"),
    "ethnography under positivism": (replace(POSITIVIST_SURVEY, strategy="Ethnography"), "paradigm-strategy", "warning"),
    "change over time in a cross-sectional design": (replace(POSITIVIST_SURVEY, questions=("How has skilled birth attendance changed over time since free maternity care began?",)), "time-horizon", "warning"),
    "unjustified quantitative sample size": (replace(POSITIVIST_SURVEY, sample_size="About 300 women"), "sample-size", "warning"),
    "qualitative study claiming generalisation": (replace(INTERPRETIVIST_PHENOMENOLOGY, claims="Findings will be generalised to all women in Kenya."), "generalisation-claim", "warning"),
    "reliability in a qualitative study": (replace(INTERPRETIVIST_PHENOMENOLOGY, quality=("Reliability using Cronbach's alpha",)), "quality-criteria", "warning"),
    "questionnaire in phenomenology": (replace(INTERPRETIVIST_PHENOMENOLOGY, data_collection=("Structured questionnaire",)), "collection-approach", "warning"),
    "hypothesis with unmeasured constructs": (replace(POSITIVIST_SURVEY, hypotheses=("Health literacy predicts facility delivery.",)), "hypothesis-measurability", "warning"),
    "hypothesis without a relationship": (replace(POSITIVIST_SURVEY, hypotheses=("Travel distance and skilled birth attendance in Kitui.",)), "hypothesis-measurability", "warning"),
}


def _blocking(report):
    return [issue for issue in report.issues if issue.severity != "info"]


def test_coherent_designs_across_paradigms_raise_no_errors_or_warnings():
    checker = ParadigmMethodChecker()
    for design in (POSITIVIST_SURVEY, INTERPRETIVIST_PHENOMENOLOGY, UBUNTU_PAR):
        report = checker.check(design)
        assert _blocking(report) == [], (design.paradigm, _blocking(report))
        assert report.status == "coherent"


def test_seeded_conflicts_are_detected_at_the_right_severity():
    checker = ParadigmMethodChecker()
    missed = []
    for name, (design, check, severity) in SEEDED.items():
        found = {(issue.check, issue.severity) for issue in checker.check(design).issues}
        if (check, severity) not in found:
            missed.append((name, sorted(found)))
    assert not missed, missed


def test_conflicts_offer_alternatives_both_ways_and_a_paradigm_profile():
    report = ParadigmMethodChecker().check(SEEDED["interpretivism with a quantitative survey"][0]).to_dict()
    conflict = next(issue for issue in report["issues"] if issue["check"] == "paradigm-approach")
    assert conflict["alternatives"][0].startswith("Keep Interpretivism")
    assert "Positivism" in conflict["alternatives"][1] and "Pragmatism" in conflict["alternatives"][1]
    assert conflict["ask"].endswith("?")
    assert report["profile"]["name"] == "Interpretivism / constructivism" and "constructed" in report["profile"]["ontology"]
    layers = {layer["id"]: layer for layer in report["layers"]}
    assert layers["paradigm"]["status"] == "conflict" and layers["approach"]["status"] == "conflict"
    assert layers["time"]["status"] == "coherent"


def test_inferred_layers_and_missing_layers_are_labelled():
    sparse = MethodDesign(strategy="Grounded theory", data_collection=("Semi-structured interviews",), analysis=("Constant comparison",))
    report = ParadigmMethodChecker().check(sparse).to_dict()
    layers = {layer["id"]: layer for layer in report["layers"]}
    assert layers["approach"]["recognised"] == "qualitative" and layers["approach"]["source"] == "inferred from strategy"
    assert layers["logic"]["recognised"] == "inductive" and layers["logic"]["source"] == "inferred from strategy"
    assert layers["paradigm"]["status"] == "missing" and layers["quality"]["status"] == "missing"
    assert any(issue["check"] == "sampling" and "theoretical sampling" in issue["message"] for issue in report["issues"])


def test_indigenous_profile_carries_relational_axiology():
    report = ParadigmMethodChecker().check(UBUNTU_PAR).to_dict()
    assert report["profile"]["name"].startswith("Afrocentric") and "Relational accountability" in report["profile"]["axiology"]


def test_api_checks_records_provenance_and_wires_the_methodologist():
    from mwenza_engine.api import app

    client = TestClient(app)
    payload = {key: list(value) if isinstance(value, tuple) else value for key, value in SEEDED["interpretivism with a quantitative survey"][0].__dict__.items()}
    body = client.post("/paradigm/check", json={**payload, "document_id": "methods-chapter"}).json()
    assert body["status"] == "needs-revision" and body["references"]
    ledger = client.get("/provenance/methods-chapter").json()
    paradigm = next(item for item in ledger["paragraphs"] if item["text"].startswith("Paradigm:"))
    assert paradigm["feedback"][0]["tool"] == "paradigm-method"
    assert "1 paradigm-method fit check" in ledger["declaration"]
    methodologist = next(agent for agent in client.get("/agents").json()["agents"] if agent["id"] == "methodologist")
    assert "check_paradigm_fit" in methodologist["tools"]
