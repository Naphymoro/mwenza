from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Iterable

from .models import Answer, Citation
from .retrieval import tokenize

ALIGNED = 0.25
WEAK = 0.10
MIN_TERMS = 3
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

STOPWORDS = frozenset(
    "the and for with from that this these those into onto among between within about which what when where whose will would shall should "
    "could their there they them than then also such each other over under more most less least very can may might must been being have has "
    "had are was were not nor but its our your how why who does did doing done study research aim aims objective objectives question questions "
    "hypothesis hypotheses using use used based towards toward upon extent determine assess examine investigate explore establish evaluate".split()
)

EXPLORATORY_CUES = ("how do", "how does", "how did", "why", "experience", "experiences", "lived", "perception", "perceptions", "perceive", "meaning", "meanings", "understand", "understanding", "views", "describe", "explore")
CONFIRMATORY_CUES = ("effect", "effects", "impact", "influence", "influences", "relationship", "association", "associated", "predict", "predicts", "predictor", "predictors", "correlation", "correlated", "difference", "differences", "compare", "to what extent", "affect", "affects", "determinants")

QUANT_ANALYSIS = ("regression", "t-test", "anova", "ancova", "manova", "chi-square", "correlation", "structural equation", "sem", "descriptive statistics", "logistic", "factor analysis", "multilevel", "mann-whitney", "kruskal-wallis", "survival analysis", "difference-in-differences", "meta-analysis")
QUAL_ANALYSIS = ("thematic", "content analysis", "ipa", "interpretative phenomenological", "grounded theory", "narrative analysis", "discourse analysis", "framework analysis", "constant comparison", "qualitative coding")

STRATEGY_APPROACH = (
    (("explanatory sequential", "exploratory sequential", "convergent", "mixed methods", "mixed-methods"), "mixed"),
    (("survey", "experiment", "experimental", "quasi-experimental", "randomised", "randomized", "cross-sectional", "cohort", "correlational", "longitudinal panel"), "quantitative"),
    (("ethnography", "ethnographic", "phenomenology", "phenomenological", "grounded theory", "narrative inquiry", "focus group", "in-depth interview"), "qualitative"),
)

PARADIGM_APPROACHES = (
    (("post-positivism", "postpositivism", "post-positivist", "postpositivist"), {"quantitative", "mixed"}),
    (("positivism", "positivist"), {"quantitative"}),
    (("interpretivism", "interpretivist", "constructivism", "constructivist", "social constructionism", "constructionist"), {"qualitative"}),
    (("pragmatism", "pragmatist"), {"quantitative", "qualitative", "mixed"}),
    (("critical theory", "critical realism", "critical", "transformative"), {"qualitative", "mixed"}),
    (("afrocentric", "afrocentricity", "ubuntu", "indigenous"), {"qualitative", "mixed"}),
)

GUIDANCE: dict[str, tuple[str, str]] = {
    "completeness": ("A postgraduate design states its problem, gap, aim, objectives, questions, paradigm, approach and analysis explicitly so an examiner can trace the argument.", "Which part of your design would an examiner look for first, and where is it written down?"),
    "chain": ("Each link in the golden thread should carry key terms forward: the gap narrows the problem, the aim answers the gap, and each objective operationalises the aim.", "If someone read only your aim, could they reconstruct the gap it responds to?"),
    "objective-question": ("Every research question should answer exactly one objective, and every objective needs at least one question that operationalises it.", "Which objective does this question serve, and what would be lost if you deleted it?"),
    "hypotheses": ("A hypothesis is a testable prediction derived from a research question and the theory; it should name the same constructs as its question.", "Which question does this hypothesis test, and which theoretical proposition does it come from?"),
    "hypotheses-approach": ("Hypotheses belong to confirmatory, usually quantitative, designs. Qualitative designs generate understanding rather than test predictions.", "Are you trying to test a prediction or to understand a phenomenon from participants' perspectives?"),
    "question-approach": ("Question wording signals design: 'how' and 'why' questions about experiences call for qualitative inquiry; questions about effects, relationships or differences call for quantitative testing.", "What kind of evidence would convince you that this question has been answered?"),
    "paradigm-approach": ("Your paradigm sets what counts as knowledge (epistemology) and what exists (ontology); the approach must follow from it.", "Do you believe the reality you study can be measured objectively, or is it constructed by the people experiencing it?"),
    "strategy-approach": ("The research strategy (survey, case study, ethnography, experiment) is an expression of the approach and must not contradict it.", "Why is this strategy the best way to answer your questions under your stated approach?"),
    "approach-analysis": ("The analysis plan is where the golden thread most often snaps: quantitative questions need statistical tests, qualitative questions need interpretive analysis, and mixed designs need both plus an integration step.", "For each question, which analysis will produce the answer, and what will that answer look like?"),
    "theory": ("A theoretical underpinning explains why the variables or themes should relate. Grounded theory designs are the main exception, because they build theory from data.", "Which theory predicts or explains the relationships you are studying, and why that one over its rivals?"),
    "theory-constructs": ("Theory is used, not decorative, when each construct appears in your questions or hypotheses and is measured or explored in data collection.", "Where in your instruments will this construct be measured or explored?"),
    "findings-questions": ("Findings should answer the research questions in order; findings that answer no question suggest scope drift.", "Which research question does this finding answer?"),
    "gap-evidence": ("A gap must be shown, not claimed: cite literature demonstrating the absence, conflict or limitation you describe.", "Which three sources best demonstrate that this gap exists?"),
}


@dataclass(frozen=True)
class ResearchDesign:
    problem: str
    gap: str
    aim: str
    objectives: tuple[str, ...]
    questions: tuple[str, ...]
    hypotheses: tuple[str, ...] = ()
    paradigm: str = ""
    approach: str = ""
    strategy: str = ""
    theory: str = ""
    constructs: tuple[str, ...] = ()
    data_collection: tuple[str, ...] = ()
    analysis: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    title: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchDesign":
        values: dict[str, Any] = {}
        for item in fields(cls):
            value = data.get(item.name, "" if item.type == "str" else ())
            values[item.name] = tuple(text.strip() for text in value if text and text.strip()) if isinstance(value, (list, tuple)) else (value or "").strip()
        return cls(**values)


@dataclass(frozen=True)
class ThreadNode:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class ThreadEdge:
    source: str
    target: str
    relation: str
    status: str
    score: float | None
    reason: str


@dataclass(frozen=True)
class ThreadIssue:
    check: str
    severity: str
    node_ids: tuple[str, ...]
    message: str
    teach: str
    ask: str


@dataclass
class GoldenThreadReport:
    title: str
    approach: str
    approach_source: str
    nodes: list[ThreadNode] = field(default_factory=list)
    edges: list[ThreadEdge] = field(default_factory=list)
    issues: list[ThreadIssue] = field(default_factory=list)
    gap_citations: tuple[Citation, ...] = ()

    @property
    def alignment_score(self) -> float | None:
        judged = [edge for edge in self.edges if edge.status not in {"unknown", "declared"}]
        if not judged:
            return None
        return round(sum(1.0 if edge.status == "aligned" else 0.5 if edge.status == "weak" else 0.0 for edge in judged) / len(judged), 3)

    @property
    def status(self) -> str:
        severities = {issue.severity for issue in self.issues}
        return "needs-revision" if "error" in severities else "review" if "warning" in severities else "aligned"

    def to_dict(self) -> dict[str, Any]:
        counts = {level: sum(1 for issue in self.issues if issue.severity == level) for level in SEVERITY_ORDER}
        return {
            "title": self.title,
            "status": self.status,
            "alignment_score": self.alignment_score,
            "approach": {"value": self.approach, "source": self.approach_source},
            "counts": counts,
            "nodes": [asdict(item) for item in self.nodes],
            "edges": [asdict(item) for item in self.edges],
            "issues": [asdict(item) for item in self.issues],
            "gap_citations": [asdict(item) for item in self.gap_citations],
            "method": "deterministic lexical and rule-based checks; status is the verdict, alignment_score is the share of judged links that are aligned, and neither replaces supervisor judgement",
        }


def _stem(token: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ness", "ment", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _terms(text: str) -> set[str]:
    return {_stem(token) for token in tokenize(text) if token not in STOPWORDS and not token.isdigit()}


def _overlap(left: str, right: str) -> tuple[float | None, list[str]]:
    a, b = _terms(left), _terms(right)
    if min(len(a), len(b)) < MIN_TERMS:
        return None, []
    shared = sorted(a & b)
    return len(shared) / min(len(a), len(b)), shared


def _status(score: float | None) -> str:
    if score is None:
        return "unknown"
    return "aligned" if score >= ALIGNED else "weak" if score >= WEAK else "broken"


def _has_cue(text: str, cues: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"(?<![\w-]){re.escape(cue)}(?![\w-])", lowered) for cue in cues)


def classify_question(text: str) -> str:
    exploratory, confirmatory = _has_cue(text, EXPLORATORY_CUES), _has_cue(text, CONFIRMATORY_CUES)
    return "mixed" if exploratory and confirmatory else "exploratory" if exploratory else "confirmatory" if confirmatory else "unclear"


def _analysis_kind(text: str) -> str:
    quant, qual = _has_cue(text, QUANT_ANALYSIS), _has_cue(text, QUAL_ANALYSIS)
    return "both" if quant and qual else "quantitative" if quant else "qualitative" if qual else "unclear"


def _strategy_approach(text: str) -> str:
    for cues, approach in STRATEGY_APPROACH:
        if _has_cue(text, cues):
            return approach
    return ""


def _normalise_approach(text: str) -> str:
    lowered = text.lower()
    if "mixed" in lowered:
        return "mixed"
    if "quantitative" in lowered:
        return "quantitative"
    if "qualitative" in lowered:
        return "qualitative"
    return ""


def _paradigm_approaches(text: str) -> set[str] | None:
    for cues, approaches in PARADIGM_APPROACHES:
        if _has_cue(text, cues):
            return approaches
    return None


class GoldenThreadChecker:
    """Checks that a research design forms one coherent argument.

    The checks are deliberately deterministic: lexical carry-over between
    linked elements plus methodology rules. Links with too little text to
    judge are reported as ``unknown`` instead of being guessed, mirroring the
    engine's abstention contract.
    """

    def check(self, design: ResearchDesign, evidence: Callable[[str], Answer] | None = None) -> GoldenThreadReport:
        approach, approach_source = self._approach(design)
        report = GoldenThreadReport(design.title, approach, approach_source)
        self._add_nodes(report, design)
        self._check_completeness(report, design)
        self._check_chain(report, design)
        self._check_objectives_questions(report, design)
        self._check_hypotheses(report, design, approach)
        self._check_question_approach(report, design, approach)
        self._check_paradigm(report, design, approach)
        self._check_analysis(report, design, approach)
        self._check_theory(report, design)
        self._check_findings(report, design)
        self._check_gap_evidence(report, design, evidence)
        report.issues.sort(key=lambda issue: SEVERITY_ORDER[issue.severity])
        return report

    def _approach(self, design: ResearchDesign) -> tuple[str, str]:
        declared = _normalise_approach(design.approach)
        if declared:
            return declared, "declared"
        inferred = _strategy_approach(design.strategy)
        if inferred:
            return inferred, "inferred-from-strategy"
        kinds = {_analysis_kind(item) for item in design.analysis} - {"unclear"}
        if kinds:
            return ("mixed" if "both" in kinds or len(kinds) > 1 else kinds.pop()), "inferred-from-analysis"
        return "unknown", "missing"

    def _add_nodes(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        for node_id, kind, text in (("problem", "problem", design.problem), ("gap", "gap", design.gap), ("aim", "aim", design.aim), ("paradigm", "paradigm", design.paradigm), ("design", "design", " · ".join(item for item in (design.approach, design.strategy) if item)), ("theory", "theory", design.theory)):
            if text:
                report.nodes.append(ThreadNode(node_id, kind, text))
        for prefix, kind, items in (("obj", "objective", design.objectives), ("rq", "question", design.questions), ("h", "hypothesis", design.hypotheses), ("construct", "construct", design.constructs), ("collection", "data-collection", design.data_collection), ("analysis", "analysis", design.analysis), ("finding", "finding", design.findings)):
            report.nodes.extend(ThreadNode(f"{prefix}-{index}", kind, text) for index, text in enumerate(items, 1))

    def _issue(self, report: GoldenThreadReport, check: str, severity: str, node_ids: Iterable[str], message: str) -> None:
        teach, ask = GUIDANCE[check]
        report.issues.append(ThreadIssue(check, severity, tuple(node_ids), message, teach, ask))

    def _link(self, report: GoldenThreadReport, source: str, target: str, relation: str, left: str, right: str) -> ThreadEdge:
        score, shared = _overlap(left, right)
        status = _status(score)
        reason = "too little text to judge" if score is None else f"shared terms: {', '.join(shared[:8])}" if shared else "no shared key terms"
        edge = ThreadEdge(source, target, relation, status, None if score is None else round(score, 3), reason)
        report.edges.append(edge)
        return edge

    def _rule_edge(self, report: GoldenThreadReport, source: str, target: str, relation: str, fits: bool, reason: str) -> None:
        report.edges.append(ThreadEdge(source, target, relation, "aligned" if fits else "broken", 1.0 if fits else 0.0, reason))

    def _check_completeness(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        required = {"problem statement": design.problem, "research gap": design.gap, "aim": design.aim, "objectives": design.objectives, "research questions": design.questions, "analysis plan": design.analysis}
        missing = [name for name, value in required.items() if not value]
        if missing:
            self._issue(report, "completeness", "error", (), f"Missing: {', '.join(missing)}.")
        if report.approach == "unknown":
            self._issue(report, "completeness", "error", ("design",), "No research approach is declared and none can be inferred from the strategy or analysis.")
        if not design.paradigm:
            self._issue(report, "completeness", "warning", (), "No research paradigm is stated, so paradigm–method coherence cannot be checked.")
        if not design.data_collection:
            self._issue(report, "completeness", "warning", (), "No data collection methods are listed, so constructs cannot be traced to instruments.")

    def _flag_edge(self, report: GoldenThreadReport, edge: ThreadEdge, check: str, broken_message: str, weak_message: str, broken_severity: str = "error") -> None:
        if edge.status == "broken":
            self._issue(report, check, broken_severity, (edge.source, edge.target), broken_message)
        elif edge.status == "weak":
            self._issue(report, check, "warning", (edge.source, edge.target), weak_message)

    def _check_chain(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        if design.problem and design.gap:
            edge = self._link(report, "problem", "gap", "narrowed-to", design.problem, design.gap)
            self._flag_edge(report, edge, "chain", "The gap does not appear to come from the stated problem.", "The gap only loosely follows from the problem.")
        if design.gap and design.aim:
            edge = self._link(report, "gap", "aim", "addressed-by", design.gap, design.aim)
            self._flag_edge(report, edge, "chain", "The aim does not address the stated gap.", "The aim only partly addresses the gap.")
        if design.aim:
            for index, objective in enumerate(design.objectives, 1):
                edge = self._link(report, "aim", f"obj-{index}", "operationalised-by", design.aim, objective)
                self._flag_edge(report, edge, "chain", f"Objective {index} does not operationalise the aim.", f"Objective {index} is only loosely tied to the aim.")

    def _best_match(self, text: str, candidates: tuple[str, ...]) -> tuple[int, float | None, list[str]]:
        best = (0, None, [])
        for index, candidate in enumerate(candidates, 1):
            score, shared = _overlap(candidate, text)
            if score is not None and (best[1] is None or score > best[1]):
                best = (index, score, shared)
        return best

    def _check_objectives_questions(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        if not design.objectives or not design.questions:
            return
        covered: set[int] = set()
        for index, question in enumerate(design.questions, 1):
            match, _, _ = self._best_match(question, design.objectives)
            if not match:
                report.edges.append(ThreadEdge("obj-?", f"rq-{index}", "answered-by", "unknown", None, "too little text to judge"))
                continue
            edge = self._link(report, f"obj-{match}", f"rq-{index}", "answered-by", design.objectives[match - 1], question)
            if edge.status in {"aligned", "weak"}:
                covered.add(match)
            self._flag_edge(report, edge, "objective-question", f"Research question {index} does not answer any objective.", f"Research question {index} is only loosely tied to objective {match}.")
        for index in range(1, len(design.objectives) + 1):
            if index not in covered:
                self._issue(report, "objective-question", "warning", (f"obj-{index}",), f"Objective {index} has no research question that clearly operationalises it.")

    def _check_hypotheses(self, report: GoldenThreadReport, design: ResearchDesign, approach: str) -> None:
        if design.hypotheses and approach == "qualitative":
            self._issue(report, "hypotheses-approach", "warning", tuple(f"h-{index}" for index in range(1, len(design.hypotheses) + 1)), "Hypotheses are stated in a qualitative design.")
        if not design.hypotheses and approach == "quantitative" and any(classify_question(question) == "confirmatory" for question in design.questions):
            self._issue(report, "hypotheses", "info", (), "Confirmatory questions in a quantitative design usually have matching hypotheses.")
        for index, hypothesis in enumerate(design.hypotheses, 1):
            match, _, _ = self._best_match(hypothesis, design.questions)
            if match:
                edge = self._link(report, f"rq-{match}", f"h-{index}", "tested-by", design.questions[match - 1], hypothesis)
                self._flag_edge(report, edge, "hypotheses", f"Hypothesis {index} does not test any research question.", f"Hypothesis {index} is only loosely tied to question {match}.", "warning")

    def _check_question_approach(self, report: GoldenThreadReport, design: ResearchDesign, approach: str) -> None:
        if approach not in {"quantitative", "qualitative", "mixed"}:
            return
        kinds = []
        for index, question in enumerate(design.questions, 1):
            kind = classify_question(question)
            kinds.append(kind)
            clash = (approach == "quantitative" and kind == "exploratory") or (approach == "qualitative" and kind == "confirmatory")
            if kind != "unclear":
                self._rule_edge(report, "design", f"rq-{index}", "fits-approach", not clash, f"{kind} question in a {approach} design")
            if clash:
                self._issue(report, "question-approach", "warning", (f"rq-{index}", "design"), f"Research question {index} is worded as {kind} but the design is {approach}.")
        if approach == "mixed" and not ({"exploratory", "mixed"} & set(kinds) and {"confirmatory", "mixed"} & set(kinds)):
            self._issue(report, "question-approach", "info", ("design",), "A mixed-methods design usually has both exploratory and confirmatory questions, linked by an integration question.")

    def _check_paradigm(self, report: GoldenThreadReport, design: ResearchDesign, approach: str) -> None:
        if not design.paradigm:
            return
        allowed = _paradigm_approaches(design.paradigm)
        if allowed is None:
            self._issue(report, "paradigm-approach", "info", ("paradigm",), f"'{design.paradigm}' is not in the paradigm catalogue, so its fit with the approach was not checked.")
        elif approach in {"quantitative", "qualitative", "mixed"}:
            fits = approach in allowed
            self._rule_edge(report, "paradigm", "design", "justifies", fits, f"{design.paradigm} typically supports: {', '.join(sorted(allowed))}")
            if not fits:
                self._issue(report, "paradigm-approach", "error", ("paradigm", "design"), f"A {approach} approach does not follow from {design.paradigm}.")
        strategy = _strategy_approach(design.strategy)
        if strategy and approach in {"quantitative", "qualitative"} and strategy not in {approach, "mixed"}:
            self._issue(report, "strategy-approach", "warning", ("design",), f"The strategy '{design.strategy}' suggests a {strategy} approach, but the design is {approach}.")

    def _check_analysis(self, report: GoldenThreadReport, design: ResearchDesign, approach: str) -> None:
        if not design.analysis or approach not in {"quantitative", "qualitative", "mixed"}:
            return
        kinds = set()
        for index, item in enumerate(design.analysis, 1):
            kind = _analysis_kind(item)
            kinds.add(kind)
            if kind != "unclear":
                fits = approach == "mixed" or kind in {approach, "both"}
                self._rule_edge(report, "design", f"analysis-{index}", "analysed-by", fits, f"{kind} analysis in a {approach} design")
        has_quant, has_qual = bool(kinds & {"quantitative", "both"}), bool(kinds & {"qualitative", "both"})
        if approach == "quantitative" and not has_quant:
            self._issue(report, "approach-analysis", "error", ("design",), "The design is quantitative but no statistical analysis is planned.")
        elif approach == "qualitative" and not has_qual:
            self._issue(report, "approach-analysis", "error", ("design",), "The design is qualitative but no interpretive analysis is planned.")
        elif approach == "mixed" and not (has_quant and has_qual):
            self._issue(report, "approach-analysis", "warning", ("design",), "A mixed-methods design needs both a statistical and an interpretive analysis strand.")
        if kinds == {"unclear"}:
            self._issue(report, "approach-analysis", "info", ("design",), "The analysis methods are not in the catalogue, so their fit was not checked.")

    def _check_theory(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        grounded = _has_cue(design.strategy, ("grounded theory",)) or any(_has_cue(item, ("grounded theory",)) for item in design.analysis)
        if not design.theory:
            self._issue(report, "theory", "info" if grounded else "warning", (), "No theoretical underpinning is named." + (" This can be acceptable in grounded theory, which builds theory from data." if grounded else ""))
            return
        if not design.constructs:
            self._issue(report, "theory-constructs", "warning", ("theory",), "The theory names no constructs, so its use in the design cannot be traced.")
            return
        usage = [(f"{prefix}-{position}", _terms(text)) for prefix, items in (("rq", design.questions), ("h", design.hypotheses), ("obj", design.objectives), ("collection", design.data_collection)) for position, text in enumerate(items, 1)]
        for index, construct in enumerate(design.constructs, 1):
            terms = _terms(construct)
            users = [node_id for node_id, node_terms in usage if terms and terms <= node_terms]
            used = bool(users)
            report.edges.append(ThreadEdge("theory", f"construct-{index}", "defines", "declared", None, "construct named by the student for this theory"))
            self._rule_edge(report, f"construct-{index}", users[0] if used else "design", "operationalised-in", used, f"appears in {', '.join(users)}" if used else "not found in questions, hypotheses or instruments")
            if not used:
                self._issue(report, "theory-constructs", "warning", ("theory", f"construct-{index}"), f"The construct '{construct}' is not used in any question, hypothesis or instrument.")

    def _check_findings(self, report: GoldenThreadReport, design: ResearchDesign) -> None:
        if not design.findings:
            return
        matched: set[int] = set()
        for index, question in enumerate(design.questions, 1):
            match, score, _ = self._best_match(question, design.findings)
            if not match:
                continue
            edge = self._link(report, f"rq-{index}", f"finding-{match}", "answered-in", question, design.findings[match - 1])
            if edge.status in {"aligned", "weak"}:
                matched.add(match)
            self._flag_edge(report, edge, "findings-questions", f"No finding answers research question {index}.", f"Research question {index} is only loosely answered by finding {match}.", "warning")
        for index in range(1, len(design.findings) + 1):
            if index not in matched:
                self._issue(report, "findings-questions", "info", (f"finding-{index}",), f"Finding {index} does not clearly answer a research question.")

    def _check_gap_evidence(self, report: GoldenThreadReport, design: ResearchDesign, evidence: Callable[[str], Answer] | None) -> None:
        if not design.gap:
            return
        if evidence is None:
            self._issue(report, "gap-evidence", "info", ("gap",), "No sources ingested by the engine were selected, so the gap was not checked against literature.")
            return
        answer = evidence(design.gap)
        if answer.abstained:
            self._issue(report, "gap-evidence", "warning", ("gap",), "No passage in the selected sources relates to the stated gap.")
            return
        report.gap_citations = answer.citations
        self._issue(report, "gap-evidence", "info", ("gap",), f"Found {len(answer.citations)} candidate passage(s) related to the gap. Confirm they show an absence, conflict or limitation rather than just the topic.")
