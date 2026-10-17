import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mwenza_engine.navigator import DESIGNS, STEPS, NavigatorError, catalogue, recommend
from mwenza_engine.paradigm import MethodDesign, ParadigmMethodChecker

SCENARIOS = json.loads((Path(__file__).parent / "synthetic" / "navigator_scenarios.json").read_text(encoding="utf-8"))


def test_scenario_file_is_marked_synthetic():
    assert SCENARIOS["synthetic"] is True and "invented" in SCENARIOS["note"]


def test_tree_is_well_formed_and_every_design_is_reachable():
    reached = set()
    for step in STEPS.values():
        for option in step.options:
            assert bool(option.next) != bool(option.design), (step.id, option.id)
            assert not option.next or option.next in STEPS
            if option.design:
                assert option.design in DESIGNS
                reached.add(option.design)
    assert reached == set(DESIGNS)


@pytest.mark.parametrize("scenario", SCENARIOS["scenarios"], ids=lambda item: item["design"])
def test_synthetic_research_questions_reach_the_expected_design(scenario):
    result = recommend(scenario["answers"])
    assert result["complete"] and result["design"]["key"] == scenario["design"]
    assert len(result["path"]) == len(scenario["answers"]) and all(step["why"] for step in result["path"])


@pytest.mark.parametrize("key", sorted(DESIGNS))
def test_every_design_passes_the_paradigm_checker_under_each_suggested_paradigm(key):
    design = DESIGNS[key]
    assert design.paradigms, key
    checker = ParadigmMethodChecker()
    for paradigm in design.paradigms:
        report = checker.check(MethodDesign.from_dict({**design.method_fields(), "paradigm": paradigm.split(" /")[0]}))
        blocking = [(issue.check, issue.message) for issue in report.issues if issue.severity != "info"]
        assert blocking == [], (key, paradigm, blocking)


def test_designs_carry_reasons_cautions_and_paradigm_specific_quality():
    par = DESIGNS["par"].to_dict()
    assert any(name.startswith("Afrocentric") for name in par["paradigms"]) and "Relational accountability through community validation" in par["quality"]
    assert DESIGNS["survey"].to_dict()["paradigms"][:2] == ["Post-positivism", "Positivism"]
    assert all(design.reasons and design.cautions for design in DESIGNS.values())


def test_partial_and_invalid_paths():
    partial = recommend(["test", "observe"])
    assert not partial["complete"] and partial["next"]["id"] == "q-time"
    with pytest.raises(NavigatorError, match="not an option"):
        recommend(["test", "maybe"])
    with pytest.raises(NavigatorError, match="continue past"):
        recommend(["test", "random", "extra"])
    assert recommend([])["next"]["id"] == "start"
    assert set(catalogue()["designs"]) == set(DESIGNS)


def test_navigator_api():
    from mwenza_engine.api import app

    client = TestClient(app)
    tree = client.get("/navigator").json()
    assert tree["start"] == "start" and len(tree["designs"]) == len(DESIGNS)
    body = client.post("/navigator/recommend", json={"answers": ["explore", "community"]}).json()
    assert body["design"]["key"] == "par" and body["method_fields"]["approach"] == "Qualitative"
    assert client.post("/navigator/recommend", json={"answers": ["nonsense"]}).status_code == 422
