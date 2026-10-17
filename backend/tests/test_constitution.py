"""Constitution checks, on synthetic data only: every author, journal, DOI and finding below is fictional."""

import ast
import json
from pathlib import Path

from mwenza_engine.constitution import DRAFT_BANNER, LABELS, Evidence, correction_prompt, remediate, review_reply

SEARCH_RESULT = json.dumps({"results": [
    {"title": "[SYNTHETIC] Distance to clinic and facility delivery in rural districts", "authors": ["Achieng Otieno", "Baraka Mwangi"], "year": 2021, "doi": "10.5555/synthetic.0001", "url": "https://doi.org/10.5555/synthetic.0001", "retracted": False, "preprint": False},
    {"title": "[SYNTHETIC] Mobile money and smallholder savings", "authors": ["Kwame Asante"], "year": 2019, "doi": "10.5555/synthetic.0002", "url": "https://journal.example.org/articles/0002", "retracted": True, "preprint": False},
    {"title": "[SYNTHETIC] Teacher feedback in large classes", "authors": ["Zanele Dlamini"], "year": 2024, "doi": "10.5555/synthetic.0003", "url": "https://africarxiv.example.org/p/0003", "retracted": False, "preprint": True},
]})


def evidence(*provided):
    return Evidence.collect([SEARCH_RESULT], provided)


def kinds(review):
    return [finding.kind for finding in review.findings]


def test_grounded_reply_passes():
    reply = "Otieno and Mwangi (2021) found that distance mattered (doi:10.5555/synthetic.0001). Dlamini (2024) is a preprint, so it has not been peer reviewed: 10.5555/synthetic.0003."
    review = review_reply(reply, evidence())
    assert review.status == "pass", review.to_dict()


def test_invented_doi_and_citation_are_blocked():
    reply = "Several studies agree (Otieno, 2021; Kamau, 2018). See https://doi.org/10.5555/invented.9999 for the trial."
    review = review_reply(reply, evidence())
    assert kinds(review) == ["unverified-citation", "unverified-doi"]
    assert review.findings[0].excerpt.startswith("Kamau")
    assert review.blocking


def test_wrong_year_for_a_real_author_is_unverified():
    review = review_reply("As Otieno (2020) argued, distance matters.", evidence())
    assert kinds(review) == ["unverified-citation"]


def test_retracted_work_is_blocked_by_doi_and_by_author_year():
    by_doi = review_reply("Savings rose sharply (10.5555/synthetic.0002).", evidence())
    by_name = review_reply("Asante (2019) showed savings rose.", evidence())
    assert kinds(by_doi) == ["retracted"] and kinds(by_name) == ["retracted"]


def test_preprint_without_caveat_warns_but_does_not_block():
    review = review_reply("Feedback improved marks (10.5555/synthetic.0003).", evidence())
    assert kinds(review) == ["preprint-uncaveated"]
    assert not review.blocking and review.status == "warnings"


def test_links_must_come_from_evidence_or_the_student():
    assert kinds(review_reply("Read https://journal.example.org/articles/7777.", evidence())) == ["unverified-link"]
    assert review_reply("Your link https://uni.example.ac.ke/handbook/ethics.pdf covers this.", evidence("My handbook is https://uni.example.ac.ke/handbook/ethics.pdf")).status == "pass"
    assert review_reply("Start at https://openalex.org.", evidence()).status == "pass"


def test_student_supplied_references_ground_their_citations():
    pasted = "My draft cites Wanjiru (2017) and (Nkosi & Banda, 2015)."
    reply = "You cite Wanjiru (2017) for the prevalence figure; does (Nkosi & Banda, 2015) report the same population?"
    assert review_reply(reply, evidence(pasted)).status == "pass"
    assert kinds(review_reply(reply, evidence())) == ["unverified-citation", "unverified-citation"]


def test_month_and_preposition_before_a_year_are_not_citations():
    assert review_reply("Data were collected in (2022) and fieldwork ran from March (2023) onward.", evidence()).status == "pass"


THESIS_PARAGRAPH = (
    "Access to skilled birth attendance remains uneven across rural districts, and the distance a woman must travel to reach a facility is among the most persistent barriers. "
    "Households located more than ten kilometres from a health centre report lower rates of facility delivery, even after accounting for income and education. "
    "Transport costs, poor roads during the rainy season and the opportunity cost of time away from farming compound the effect of distance. "
    "These barriers interact with perceptions of quality of care, so that a closer facility with stock-outs may be bypassed in favour of a distant hospital. "
    "This study therefore examines how distance, transport and perceived quality jointly shape the place of delivery among women in three rural districts, "
    "using a household survey and facility audit to separate the influence of geography from that of service readiness and to inform where new maternity waiting homes should be located."
)


def test_finished_thesis_prose_is_flagged():
    review = review_reply("Here is your background section:\n\n" + THESIS_PARAGRAPH, evidence())
    assert kinds(review) == ["draftable-prose"] and review.blocking


def test_questions_lists_short_text_and_labelled_examples_are_not_flagged():
    as_questions = THESIS_PARAGRAPH.replace("This study therefore examines", "Could your study examine") + " What would that add?"
    as_list = "\n".join("- " + sentence for sentence in THESIS_PARAGRAPH.split(". "))
    labelled = "Annotated example (not your text):\n\n" + THESIS_PARAGRAPH
    addressed = THESIS_PARAGRAPH.replace("This study therefore examines", "Your study could examine")
    for reply in (as_questions, as_list, labelled, addressed, "Distance matters. Transport matters. Quality matters. So does cost."):
        assert review_reply(reply, evidence()).status == "pass", reply[:60]


def test_code_blocks_are_not_prose():
    reply = "Run this:\n\n```python\n" + THESIS_PARAGRAPH + "\n```\n"
    assert review_reply(reply, evidence()).status == "pass"


def test_remediation_labels_without_deleting():
    reply = "Kamau (2018) disagrees.\n\n" + THESIS_PARAGRAPH
    review = review_reply(reply, evidence())
    fixed = remediate(reply, review)
    assert "Kamau (2018) " + LABELS["unverified-citation"] in fixed
    assert DRAFT_BANNER in fixed and THESIS_PARAGRAPH in fixed
    assert fixed.index(DRAFT_BANNER) < fixed.index(THESIS_PARAGRAPH)
    assert "integrity check labelled" in fixed


def test_correction_prompt_names_each_issue_and_carries_the_draft():
    reply = "See 10.5555/invented.9999."
    prompt = correction_prompt(reply, review_reply(reply, evidence()))
    assert "unverified-doi" in prompt and "<draft>\nSee 10.5555/invented.9999.\n</draft>" in prompt


def test_module_is_standard_library_only_so_deerflow_can_vendor_it():
    source = Path(__file__).parents[1] / "src" / "mwenza_engine" / "constitution.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module}
    relative = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level > 0]
    assert not relative and imported <= {"__future__", "json", "re", "dataclasses", "typing"}
