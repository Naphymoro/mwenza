"""Shared research-methodology catalogue used by the methodology engines.

The entries summarise widely taught positions (for example the layers of
Saunders, Lewis and Thornhill's "research onion", Lincoln and Guba's
trustworthiness criteria, and Chilisa's Indigenous research paradigm). They
are teaching defaults, not laws: a well-argued design can depart from them,
which is why the engines flag tensions for discussion rather than forbid them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .text import has_cue

QUANT, QUAL, MIXED = "quantitative", "qualitative", "mixed"
VALIDITY, TRUSTWORTHINESS = "validity-reliability", "trustworthiness"


@dataclass(frozen=True)
class Paradigm:
    key: str
    name: str
    cues: tuple[str, ...]
    ontology: str
    epistemology: str
    axiology: str
    logics: frozenset[str]
    approaches: frozenset[str]
    strategies: frozenset[str]
    quality: frozenset[str]


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    cues: tuple[str, ...]
    approaches: frozenset[str]
    collection: tuple[str, ...]
    logic: str = ""
    longitudinal: bool = False


def _set(*items: str) -> frozenset[str]:
    return frozenset(items)


# Order matters: more specific names are matched before the names they contain.
PARADIGMS: tuple[Paradigm, ...] = (
    Paradigm("post-positivism", "Post-positivism", ("post-positivism", "postpositivism", "post-positivist", "postpositivist"),
             "A reality exists, but it can only be known imperfectly and probabilistically.", "Knowledge is conjectural: claims are tested and may be falsified; objectivity is an aim, with bias acknowledged.", "The researcher strives for objectivity while recognising that values influence what is studied.",
             _set("deductive"), _set(QUANT, MIXED), _set("experiment", "quasi-experiment", "survey", "correlational", "cohort", "case-control", "secondary", "case study", "mixed methods"), _set(VALIDITY)),
    Paradigm("positivism", "Positivism", ("positivism", "positivist"),
             "A single, objective reality exists independently of the researcher.", "Valid knowledge comes from observable, measurable facts; the researcher stays detached from what is studied.", "Research aims to be value-free; the researcher's values are kept out of the findings.",
             _set("deductive"), _set(QUANT), _set("experiment", "quasi-experiment", "survey", "correlational", "cohort", "case-control", "secondary"), _set(VALIDITY)),
    Paradigm("critical-realism", "Critical realism", ("critical realism", "critical realist"),
             "Reality is layered: real mechanisms produce events, only some of which we observe.", "Knowledge is fallible and historically situated; research explains the mechanisms behind observed patterns.", "Values shape inquiry; the researcher acknowledges their position while seeking explanation.",
             _set("abductive", "deductive", "inductive"), _set(QUANT, QUAL, MIXED), _set("case study", "mixed methods", "survey", "ethnography", "secondary", "action research"), _set(VALIDITY, TRUSTWORTHINESS)),
    Paradigm("interpretivism", "Interpretivism / constructivism", ("interpretivism", "interpretivist", "constructivism", "constructivist", "social constructionism", "constructionist"),
             "Multiple realities are socially constructed through human experience and language.", "Knowledge is co-created by interpreting the meanings people give to their experiences.", "Research is value-bound; the researcher is part of what is studied and practises reflexivity.",
             _set("inductive", "abductive"), _set(QUAL), _set("phenomenology", "ethnography", "case study", "grounded theory", "narrative inquiry", "action research"), _set(TRUSTWORTHINESS)),
    Paradigm("pragmatism", "Pragmatism", ("pragmatism", "pragmatist"),
             "Reality is what is encountered in practice; it can be viewed from several perspectives.", "Knowledge is judged by its practical consequences; the research question decides the methods.", "Values drive the choice of problem and methods; research aims to be useful.",
             _set("abductive", "deductive", "inductive"), _set(QUANT, QUAL, MIXED), _set("mixed methods", "action research", "design science", "case study", "survey", "experiment", "quasi-experiment", "secondary"), _set(VALIDITY, TRUSTWORTHINESS)),
    Paradigm("critical", "Critical theory / transformative", ("critical theory", "transformative", "emancipatory", "feminist", "critical"),
             "Reality is shaped by power, history and social structures.", "Knowledge is political; research exposes and challenges inequality alongside participants.", "Research is explicitly value-laden and aims at emancipation or social change.",
             _set("abductive", "inductive"), _set(QUAL, MIXED), _set("action research", "ethnography", "case study", "narrative inquiry", "mixed methods"), _set(TRUSTWORTHINESS)),
    Paradigm("indigenous", "Afrocentric / Indigenous (including Ubuntu)", ("afrocentric", "afrocentricity", "ubuntu", "indigenous", "postcolonial", "decolonial"),
             "Reality is relational: people, communities, land and ancestors exist through their relationships (\"a person is a person through other persons\").", "Knowledge is communal and held in relationships and Indigenous knowledge systems, not only in individuals.", "Relational accountability: respect, reciprocity and benefit to the community guide every research choice.",
             _set("inductive", "abductive"), _set(QUAL, MIXED), _set("action research", "narrative inquiry", "case study", "ethnography", "mixed methods"), _set(TRUSTWORTHINESS)),
)

STRATEGIES: tuple[Strategy, ...] = (
    Strategy("mixed methods", "Mixed-methods design", ("explanatory sequential", "exploratory sequential", "convergent", "embedded design", "mixed methods", "mixed-methods"), _set(MIXED), ("questionnaire", "interview", "focus group")),
    Strategy("quasi-experiment", "Quasi-experiment", ("quasi-experiment", "quasi-experimental", "difference-in-differences", "non-equivalent control"), _set(QUANT), ("questionnaire", "test", "measurement", "records"), "deductive"),
    Strategy("experiment", "Experiment / trial", ("experiment", "experimental", "randomised controlled trial", "randomized controlled trial", "randomised", "randomized", "rct", "trial"), _set(QUANT), ("questionnaire", "test", "measurement", "biomarker", "observation checklist"), "deductive"),
    Strategy("cohort", "Cohort / panel study", ("cohort", "panel study", "longitudinal panel", "prospective"), _set(QUANT), ("questionnaire", "records", "measurement"), "deductive", True),
    Strategy("case-control", "Case-control study", ("case-control", "case control"), _set(QUANT), ("records", "questionnaire")),
    Strategy("survey", "Survey", ("survey", "cross-sectional"), _set(QUANT, MIXED), ("questionnaire", "structured interview")),
    Strategy("correlational", "Correlational design", ("correlational",), _set(QUANT), ("questionnaire", "records", "measurement"), "deductive"),
    Strategy("secondary", "Secondary / archival analysis", ("secondary data", "secondary analysis", "archival", "dhs", "demographic and health survey", "document analysis"), _set(QUANT, QUAL, MIXED), ("records", "documents", "dataset")),
    Strategy("grounded theory", "Grounded theory", ("grounded theory",), _set(QUAL), ("interview", "focus group", "observation"), "inductive"),
    Strategy("phenomenology", "Phenomenology", ("phenomenology", "phenomenological", "interpretative phenomenological"), _set(QUAL), ("interview", "in-depth interview")),
    Strategy("ethnography", "Ethnography", ("ethnography", "ethnographic"), _set(QUAL), ("participant observation", "observation", "field notes", "interview")),
    Strategy("narrative inquiry", "Narrative inquiry", ("narrative inquiry", "life history", "life histories", "storytelling", "oral history"), _set(QUAL), ("interview", "life history", "story", "storytelling", "oral history")),
    Strategy("action research", "Action research", ("participatory action research", "community-based participatory research", "action research", "cbpr", "par"), _set(QUAL, MIXED), ("workshop", "focus group", "interview", "observation", "questionnaire")),
    Strategy("design science", "Design science research", ("design science", "design-based research"), _set(QUANT, QUAL, MIXED), ("prototype", "evaluation", "interview", "questionnaire")),
    Strategy("case study", "Case study", ("case study", "case studies", "multiple-case", "multiple case"), _set(QUANT, QUAL, MIXED), ("interview", "documents", "observation", "questionnaire")),
)

QUANT_ANALYSIS = ("regression", "t-test", "anova", "ancova", "manova", "chi-square", "correlation", "structural equation", "sem", "descriptive statistics", "logistic", "factor analysis", "multilevel", "mann-whitney", "kruskal-wallis", "survival analysis", "difference-in-differences", "meta-analysis")
QUAL_ANALYSIS = ("thematic", "content analysis", "ipa", "interpretative phenomenological", "grounded theory", "narrative analysis", "discourse analysis", "framework analysis", "constant comparison", "qualitative coding")

QUANT_COLLECTION = ("questionnaire", "structured interview", "survey instrument", "scale", "test", "measurement", "biomarker", "records", "dataset", "observation checklist")
QUAL_COLLECTION = ("in-depth interview", "semi-structured interview", "unstructured interview", "interview", "focus group", "participant observation", "field notes", "life history", "storytelling", "oral history", "talking circle", "photovoice", "diary", "workshop")

PROBABILITY_SAMPLING = ("simple random", "random sampling", "randomly", "stratified", "cluster", "systematic sampling", "multistage", "multi-stage", "probability")
NON_PROBABILITY_SAMPLING = ("purposive", "purposeful", "snowball", "theoretical sampling", "convenience", "quota", "maximum variation", "criterion sampling", "non-probability")
SAMPLE_SIZE_QUANT = ("power", "g*power", "gpower", "cochran", "yamane", "formula", "calculated", "calculation", "effect size", "margin of error", "confidence level", "census")
SAMPLE_SIZE_QUAL = ("saturation", "information power", "data adequacy", "until no new")

VALIDITY_CRITERIA = ("validity", "reliability", "generalisability", "generalizability", "generalise", "generalize", "objectivity", "cronbach", "test-retest", "inter-rater")
TRUST_CRITERIA = ("credibility", "transferability", "dependability", "confirmability", "trustworthiness", "reflexivity", "member checking", "member check", "thick description", "audit trail", "authenticity", "relational accountability", "community validation")
GENERALISATION_CLAIMS = ("generalise", "generalize", "generalisable", "generalizable", "representative of", "all women", "the whole population", "nationally representative")
CHANGE_CUES = ("over time", "trend", "trends", "change in", "changes in", "changed", "trajectory", "trajectories", "before and after", "follow-up", "follow up", "long-term", "longitudinal")

LOGIC_CUES = (("abductive", ("abductive", "abduction", "retroductive", "retroduction")), ("deductive", ("deductive", "deduction", "hypothetico-deductive", "theory testing", "theory-testing")), ("inductive", ("inductive", "induction", "theory building", "theory-building")))

EXPLORATORY_CUES = ("how do", "how does", "how did", "why", "experience", "experiences", "lived", "perception", "perceptions", "perceive", "meaning", "meanings", "understand", "understanding", "views", "describe", "explore")
CONFIRMATORY_CUES = ("effect", "effects", "impact", "influence", "influences", "relationship", "association", "associated", "predict", "predicts", "predictor", "predictors", "correlation", "correlated", "difference", "differences", "compare", "to what extent", "affect", "affects", "determinants")


def find_paradigm(text: str) -> Paradigm | None:
    return next((paradigm for paradigm in PARADIGMS if has_cue(text, paradigm.cues)), None)


def find_strategy(text: str) -> Strategy | None:
    return next((strategy for strategy in STRATEGIES if has_cue(text, strategy.cues)), None)


def strategy_by_key(key: str) -> Strategy:
    return next(strategy for strategy in STRATEGIES if strategy.key == key)


def normalise_approach(text: str) -> str:
    lowered = text.lower()
    for approach in (MIXED, QUANT, QUAL):
        if approach[:5] in lowered:
            return approach
    return ""


def strategy_approach(text: str) -> str:
    """The approach a strategy implies, or "" when it fits any approach or is unknown."""
    strategy = find_strategy(text)
    if strategy:
        single = strategy.approaches - {MIXED}
        return next(iter(single)) if len(single) == 1 else MIXED if strategy.approaches == {MIXED} else ""
    if strategy is None and has_cue(text, ("focus group", "in-depth interview")):
        return QUAL
    return ""


def find_logic(text: str) -> str:
    return next((logic for logic, cues in LOGIC_CUES if has_cue(text, cues)), "")


def analysis_kind(text: str) -> str:
    quant, qual = has_cue(text, QUANT_ANALYSIS), has_cue(text, QUAL_ANALYSIS)
    return "both" if quant and qual else QUANT if quant else QUAL if qual else "unclear"


def collection_kind(text: str) -> str:
    quant, qual = has_cue(text, QUANT_COLLECTION), has_cue(text, QUAL_COLLECTION)
    return "both" if quant and qual else QUANT if quant else QUAL if qual else "unclear"


def classify_question(text: str) -> str:
    exploratory, confirmatory = has_cue(text, EXPLORATORY_CUES), has_cue(text, CONFIRMATORY_CUES)
    return "mixed" if exploratory and confirmatory else "exploratory" if exploratory else "confirmatory" if confirmatory else "unclear"
