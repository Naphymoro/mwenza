from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .methodology import (
    CHANGE_CUES, CONFIRMATORY_CUES, GENERALISATION_CLAIMS, MIXED, NON_PROBABILITY_SAMPLING, PARADIGMS, PROBABILITY_SAMPLING, QUAL, QUANT,
    SAMPLE_SIZE_QUAL, SAMPLE_SIZE_QUANT, STRATEGIES, TRUST_CRITERIA, TRUSTWORTHINESS, VALIDITY, VALIDITY_CRITERIA, Paradigm, Strategy,
    analysis_kind, collection_kind, find_logic, find_paradigm, find_strategy, normalise_approach, strategy_approach,
)
from .text import content_terms, has_cue

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
LAYERS = (
    ("paradigm", "Paradigm"), ("logic", "Approach to theory"), ("approach", "Methodological choice"), ("strategy", "Strategy"), ("time", "Time horizon"),
    ("sampling", "Sampling"), ("collection", "Data collection"), ("analysis", "Analysis"), ("quality", "Quality criteria"),
)
RELATION_WORDS = CONFIRMATORY_CUES + ("higher", "lower", "more", "less", "greater", "fewer", "increase", "increases", "decrease", "decreases", "reduce", "reduces", "improve", "improves", "than", "between")
QUALITY_LABELS = {VALIDITY: "validity and reliability", TRUSTWORTHINESS: "trustworthiness (credibility, transferability, dependability, confirmability)"}
REFERENCES = (
    "Saunders, M., Lewis, P. and Thornhill, A. Research Methods for Business Students (the \"research onion\").",
    "Creswell, J. W. and Creswell, J. D. (2018). Research Design: Qualitative, Quantitative, and Mixed Methods Approaches. 5th ed. SAGE.",
    "Lincoln, Y. S. and Guba, E. G. (1985). Naturalistic Inquiry. SAGE.",
    "Chilisa, B. Indigenous Research Methodologies. SAGE.",
)

GUIDANCE: dict[str, tuple[str, str]] = {
    "completeness": ("Examiners expect each layer of the design to be stated and justified, from paradigm to quality criteria, so the reasoning between layers can be followed.", "Which layer of your design would you find hardest to defend in a viva, and why?"),
    "paradigm-logic": ("A paradigm implies how theory relates to data: positivist work usually tests theory (deductive), interpretivist work usually builds it (inductive), and pragmatist or critical-realist work often moves between the two (abductive).", "Are you starting from a theory to test, or hoping to develop one from what you find?"),
    "paradigm-approach": ("The methodological choice should follow from what you believe reality is and how it can be known. Measuring a single objective reality calls for quantitative methods; understanding constructed meanings calls for qualitative ones.", "Do you believe the reality you study can be measured objectively, or is it constructed by the people experiencing it?"),
    "paradigm-strategy": ("Each strategy carries assumptions. A survey assumes the phenomenon can be measured consistently across people; phenomenology assumes it must be understood through lived experience.", "What does this strategy assume about knowledge, and do you share that assumption?"),
    "strategy-approach": ("The strategy is the practical form of the methodological choice and should not contradict it.", "Why is this strategy the best way to answer your questions under your stated approach?"),
    "logic-strategy": ("Some strategies have a built-in logic. Grounded theory builds theory from data, so it cannot start by testing a theory; experiments test predictions, so they are deductive.", "What role does existing theory play at the start of your study?"),
    "hypotheses-logic": ("Hypotheses are predictions derived from theory before data collection, which makes a design deductive.", "Are these hypotheses to test, or are they expectations you want to explore openly?"),
    "hypothesis-measurability": ("A testable hypothesis states a relationship or difference between named constructs, and each construct is measured by your instruments.", "How exactly will you measure each construct in this hypothesis, and what result would show it is false?"),
    "time-horizon": ("Questions about change, trends or effects over time need data from more than one point in time; a cross-sectional design shows a single snapshot.", "Does your question ask how things are, or how they change?"),
    "sampling": ("Probability sampling supports statistical generalisation to a population; purposive sampling selects information-rich cases for depth and supports transferability, not statistical generalisation.", "To whom do you want your findings to apply, and does your sampling allow that claim?"),
    "sample-size": ("Sample size must be justified: quantitative studies by a power analysis or a stated formula, qualitative studies by saturation or information power.", "Why this number, and what would change if you had half as many participants?"),
    "collection-approach": ("Data collection methods must produce the kind of data your approach and strategy need: measurements for quantitative work, rich accounts for qualitative work.", "What kind of data will this instrument produce, and how does it answer your question?"),
    "analysis-approach": ("Quantitative questions need statistical analysis; qualitative questions need interpretive analysis; mixed designs need both and a plan to integrate them.", "For each research question, which analysis produces the answer?"),
    "quality-criteria": ("Quality criteria come from the paradigm. Quantitative studies argue validity and reliability; qualitative studies argue trustworthiness (Lincoln and Guba's credibility, transferability, dependability, confirmability); Indigenous research adds relational accountability.", "Which criteria would a reader from your paradigm use to judge your study?"),
    "generalisation-claim": ("Qualitative and purposively sampled studies cannot generalise statistically; they argue transferability through thick description of context.", "What would a reader need to know about your setting to judge whether your findings apply to theirs?"),
}


@dataclass(frozen=True)
class MethodDesign:
    paradigm: str = ""
    approach: str = ""
    logic: str = ""
    strategy: str = ""
    time_horizon: str = ""
    sampling: str = ""
    sample_size: str = ""
    data_collection: tuple[str, ...] = ()
    analysis: tuple[str, ...] = ()
    quality: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    claims: str = ""
    title: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MethodDesign":
        values: dict[str, Any] = {}
        for item in fields(cls):
            value = data.get(item.name, "" if item.type == "str" else ())
            values[item.name] = tuple(text.strip() for text in value if text and text.strip()) if isinstance(value, (list, tuple)) else (value or "").strip()
        return cls(**values)


@dataclass(frozen=True)
class MethodIssue:
    check: str
    severity: str
    layers: tuple[str, ...]
    message: str
    teach: str
    ask: str
    alternatives: tuple[str, ...] = ()


@dataclass
class ParadigmReport:
    title: str
    layers: list[dict[str, Any]] = field(default_factory=list)
    issues: list[MethodIssue] = field(default_factory=list)
    profile: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        severities = {issue.severity for issue in self.issues}
        return "needs-revision" if "error" in severities else "review" if "warning" in severities else "coherent"

    def to_dict(self) -> dict[str, Any]:
        for layer in self.layers:
            levels = [issue.severity for issue in self.issues if layer["id"] in issue.layers]
            if layer["status"] not in {"missing", "unrecognised"}:
                layer["status"] = "conflict" if "error" in levels else "tension" if "warning" in levels else "coherent"
        return {
            "title": self.title,
            "status": self.status,
            "counts": {level: sum(1 for issue in self.issues if issue.severity == level) for level in SEVERITY_ORDER},
            "layers": self.layers,
            "issues": [asdict(issue) for issue in self.issues],
            "profile": self.profile,
            "references": list(REFERENCES),
            "method": "deterministic rules over a catalogue of widely taught paradigm and method positions; tensions are prompts for justification, not prohibitions",
        }


def _names(keys: frozenset[str] | set[str], catalogue: tuple[Any, ...]) -> str:
    return ", ".join(item.name for item in catalogue if item.key in keys)


def _profile(paradigm: Paradigm) -> dict[str, Any]:
    return {
        "name": paradigm.name, "ontology": paradigm.ontology, "epistemology": paradigm.epistemology, "axiology": paradigm.axiology,
        "logics": sorted(paradigm.logics), "approaches": sorted(paradigm.approaches), "strategies": [item.name for item in STRATEGIES if item.key in paradigm.strategies],
        "quality": [QUALITY_LABELS[item] for item in sorted(paradigm.quality)],
    }


class ParadigmMethodChecker:
    """Checks that each layer of a research design follows from the paradigm.

    Layers follow the widely taught "research onion": paradigm, approach to
    theory, methodological choice, strategy, time horizon, then techniques
    (sampling, data collection, analysis) and quality criteria. Each conflict
    lists coherent alternatives in both directions, so the student chooses
    what to change.
    """

    def check(self, design: MethodDesign) -> ParadigmReport:
        report = ParadigmReport(design.title)
        paradigm = find_paradigm(design.paradigm) if design.paradigm else None
        strategy = find_strategy(design.strategy) if design.strategy else None
        approach, approach_source = self._approach(design, strategy)
        logic, logic_source = self._logic(design, strategy)
        horizon, horizon_source = self._horizon(design, strategy)
        sampling = self._sampling(design.sampling)
        collection = {collection_kind(item) for item in design.data_collection} - {"unclear"}
        analysis = {analysis_kind(item) for item in design.analysis} - {"unclear"}
        quality = self._quality(design.quality)
        report.profile = _profile(paradigm) if paradigm else None
        report.layers = [
            self._layer("paradigm", design.paradigm, paradigm.name if paradigm else ""),
            self._layer("logic", design.logic, logic, logic_source),
            self._layer("approach", design.approach, approach, approach_source),
            self._layer("strategy", design.strategy, strategy.name if strategy else ""),
            self._layer("time", design.time_horizon, horizon, horizon_source),
            self._layer("sampling", design.sampling, sampling),
            self._layer("collection", "; ".join(design.data_collection), " + ".join(sorted(collection))),
            self._layer("analysis", "; ".join(design.analysis), " + ".join(sorted(analysis))),
            self._layer("quality", "; ".join(design.quality), " + ".join(QUALITY_LABELS[item].split(" (")[0] for item in sorted(quality))),
        ]
        self._completeness(report, design, paradigm, strategy, approach)
        if paradigm:
            self._paradigm_fit(report, paradigm, approach, logic, strategy, quality)
        if strategy:
            self._strategy_fit(report, strategy, approach, logic)
        self._hypotheses(report, design, approach, logic)
        self._time(report, design, horizon, strategy)
        self._sampling_checks(report, design, approach, sampling, strategy)
        self._techniques(report, approach, strategy, collection, analysis, quality, bool(design.data_collection), bool(design.analysis))
        self._claims(report, design, approach, sampling)
        report.issues.sort(key=lambda issue: SEVERITY_ORDER[issue.severity])
        return report

    @staticmethod
    def _layer(layer_id: str, value: str, recognised: str, source: str = "declared") -> dict[str, Any]:
        label = dict(LAYERS)[layer_id]
        status = "missing" if not value and not recognised else "unrecognised" if not recognised else "coherent"
        return {"id": layer_id, "label": label, "value": value, "recognised": recognised, "source": source if recognised else "", "status": status}

    def _issue(self, report: ParadigmReport, check: str, severity: str, layers: tuple[str, ...], message: str, alternatives: tuple[str, ...] = ()) -> None:
        teach, ask = GUIDANCE[check]
        report.issues.append(MethodIssue(check, severity, layers, message, teach, ask, alternatives))

    @staticmethod
    def _approach(design: MethodDesign, strategy: Strategy | None) -> tuple[str, str]:
        declared = normalise_approach(design.approach)
        if declared:
            return declared, "declared"
        implied = strategy_approach(design.strategy) if strategy else ""
        if implied:
            return implied, "inferred from strategy"
        kinds = {analysis_kind(item) for item in design.analysis} - {"unclear"}
        if kinds:
            return (MIXED if "both" in kinds or len(kinds) > 1 else kinds.pop()), "inferred from analysis"
        return "", ""

    @staticmethod
    def _logic(design: MethodDesign, strategy: Strategy | None) -> tuple[str, str]:
        declared = find_logic(design.logic)
        if declared:
            return declared, "declared"
        if design.hypotheses:
            return "deductive", "inferred from hypotheses"
        if strategy and strategy.logic:
            return strategy.logic, "inferred from strategy"
        return "", ""

    @staticmethod
    def _horizon(design: MethodDesign, strategy: Strategy | None) -> tuple[str, str]:
        text = design.time_horizon.lower()
        if "longitudinal" in text or "panel" in text or "repeated" in text:
            return "longitudinal", "declared"
        if "cross" in text or "single point" in text or "snapshot" in text:
            return "cross-sectional", "declared"
        if strategy and strategy.longitudinal:
            return "longitudinal", "inferred from strategy"
        if has_cue(design.strategy, ("cross-sectional",)):
            return "cross-sectional", "inferred from strategy"
        return "", ""

    @staticmethod
    def _sampling(text: str) -> str:
        probability, purposive = has_cue(text, PROBABILITY_SAMPLING), has_cue(text, NON_PROBABILITY_SAMPLING)
        return "probability and non-probability" if probability and purposive else "probability" if probability else "non-probability" if purposive else ""

    @staticmethod
    def _quality(items: tuple[str, ...]) -> set[str]:
        text = " ".join(items)
        return {kind for kind, cues in ((VALIDITY, VALIDITY_CRITERIA), (TRUSTWORTHINESS, TRUST_CRITERIA)) if has_cue(text, cues)}

    def _completeness(self, report: ParadigmReport, design: MethodDesign, paradigm: Paradigm | None, strategy: Strategy | None, approach: str) -> None:
        if not design.paradigm:
            self._issue(report, "completeness", "warning", ("paradigm",), "No research paradigm is stated, so the other layers cannot be traced to it.")
        elif paradigm is None:
            self._issue(report, "completeness", "info", ("paradigm",), f"'{design.paradigm}' is not in the paradigm catalogue, so its fit was not checked.", tuple(item.name for item in PARADIGMS))
        if not approach:
            self._issue(report, "completeness", "error", ("approach",), "No methodological choice is stated or implied by the strategy or analysis.")
        if not design.strategy:
            self._issue(report, "completeness", "warning", ("strategy",), "No research strategy is stated (for example survey, case study, phenomenology).")
        elif strategy is None:
            self._issue(report, "completeness", "info", ("strategy",), f"'{design.strategy}' is not in the strategy catalogue, so its fit was not checked.")
        for layer, value, message in (("sampling", design.sampling, "No sampling technique is stated."), ("collection", design.data_collection, "No data collection methods are stated."), ("analysis", design.analysis, "No analysis methods are stated."), ("quality", design.quality, "No quality criteria are stated (validity and reliability, or trustworthiness).")):
            if not value:
                self._issue(report, "completeness" if layer != "quality" else "quality-criteria", "warning", (layer,), message)

    def _paradigm_fit(self, report: ParadigmReport, paradigm: Paradigm, approach: str, logic: str, strategy: Strategy | None, quality: set[str]) -> None:
        if approach and approach not in paradigm.approaches:
            supporting = [item.name for item in PARADIGMS if approach in item.approaches]
            self._issue(report, "paradigm-approach", "error", ("paradigm", "approach"), f"A {approach} approach does not follow from {paradigm.name}.", (f"Keep {paradigm.name}: use a {' or '.join(sorted(paradigm.approaches))} approach.", f"Keep the {approach} approach: consider {', '.join(supporting)}."))
        if logic and logic not in paradigm.logics:
            self._issue(report, "paradigm-logic", "warning", ("paradigm", "logic"), f"{paradigm.name} usually uses {' or '.join(sorted(paradigm.logics))} reasoning, but the design is {logic}.", (f"Keep {paradigm.name}: argue a {' or '.join(sorted(paradigm.logics))} logic.", f"Keep {logic} reasoning: consider {', '.join(item.name for item in PARADIGMS if logic in item.logics)}."))
        if strategy and strategy.key not in paradigm.strategies:
            self._issue(report, "paradigm-strategy", "warning", ("paradigm", "strategy"), f"{strategy.name} is unusual under {paradigm.name}; justify it explicitly or reconsider.", (f"Strategies typical of {paradigm.name}: {_names(paradigm.strategies, STRATEGIES)}.", f"Paradigms that typically use {strategy.name}: {', '.join(item.name for item in PARADIGMS if strategy.key in item.strategies) or 'none in the catalogue'}."))
        if quality and not quality & paradigm.quality:
            self._issue(report, "quality-criteria", "warning", ("paradigm", "quality"), f"The quality criteria ({', '.join(QUALITY_LABELS[item].split(' (')[0] for item in sorted(quality))}) are not the ones {paradigm.name} usually uses.", (f"Under {paradigm.name}, argue {' and '.join(QUALITY_LABELS[item] for item in sorted(paradigm.quality))}.",))

    def _strategy_fit(self, report: ParadigmReport, strategy: Strategy, approach: str, logic: str) -> None:
        if approach and approach not in strategy.approaches:
            self._issue(report, "strategy-approach", "warning", ("strategy", "approach"), f"{strategy.name} is normally {' or '.join(sorted(strategy.approaches))}, but the design is {approach}.", (f"Strategies that suit a {approach} approach: {', '.join(item.name for item in STRATEGIES if approach in item.approaches)}.",))
        if strategy.logic and logic and logic != strategy.logic:
            severity = "error" if strategy.key == "grounded theory" else "warning"
            self._issue(report, "logic-strategy", severity, ("logic", "strategy"), f"{strategy.name} is {strategy.logic} by design, but the stated logic is {logic}.", (f"Keep {strategy.name}: adopt {strategy.logic} reasoning.", f"Keep {logic} reasoning: choose a strategy such as {', '.join([item.name for item in STRATEGIES if item.logic in {logic, ''} and item.key != strategy.key][:4])}."))

    def _hypotheses(self, report: ParadigmReport, design: MethodDesign, approach: str, logic: str) -> None:
        if design.hypotheses and find_logic(design.logic) == "inductive":
            self._issue(report, "hypotheses-logic", "warning", ("logic",), "Hypotheses are stated, but the declared logic is inductive.")
        measured = content_terms(" ".join(design.data_collection))
        for index, hypothesis in enumerate(design.hypotheses, 1):
            if not has_cue(hypothesis, RELATION_WORDS):
                self._issue(report, "hypothesis-measurability", "warning", ("logic",), f"Hypothesis {index} does not state a relationship or difference that could be tested.")
            terms = content_terms(hypothesis)
            if design.data_collection and terms and len(terms & measured) / len(terms) < 0.25:
                self._issue(report, "hypothesis-measurability", "warning", ("collection",), f"The constructs in hypothesis {index} are not visibly measured by the data collection methods.")

    def _time(self, report: ParadigmReport, design: MethodDesign, horizon: str, strategy: Strategy | None) -> None:
        asks_change = any(has_cue(text, CHANGE_CUES) for text in (*design.questions, *design.hypotheses, design.claims))
        if asks_change and horizon == "cross-sectional":
            self._issue(report, "time-horizon", "warning", ("time",), "The questions ask about change over time, but the design is cross-sectional.", ("Keep the question: collect data at two or more points (panel, cohort or repeated cross-sections).", "Keep the cross-sectional design: reframe the question as differences between groups at one point in time."))
        if horizon == "longitudinal" and has_cue(design.strategy, ("cross-sectional",)):
            self._issue(report, "time-horizon", "warning", ("time", "strategy"), "The time horizon is longitudinal, but the strategy is described as cross-sectional.")

    def _sampling_checks(self, report: ParadigmReport, design: MethodDesign, approach: str, sampling: str, strategy: Strategy | None) -> None:
        if design.sampling and not sampling:
            self._issue(report, "sampling", "info", ("sampling",), "The sampling technique is not named in a recognised way (for example stratified random, purposive, snowball).")
        if approach == QUANT and sampling == "non-probability":
            self._issue(report, "sampling", "info", ("sampling", "approach"), "Non-probability sampling in a quantitative design limits statistical generalisation; say so in the limitations.")
        if approach == QUAL and sampling == "probability":
            self._issue(report, "sampling", "info", ("sampling", "approach"), "Probability sampling is unusual in qualitative work; purposeful selection of information-rich cases is the norm.")
        if strategy and strategy.key == "grounded theory" and not has_cue(design.sampling, ("theoretical sampling", "theoretical")):
            self._issue(report, "sampling", "info", ("sampling", "strategy"), "Grounded theory normally uses theoretical sampling, guided by the emerging analysis.")
        size = design.sample_size
        if approach in {QUANT, MIXED} and not has_cue(size, SAMPLE_SIZE_QUANT):
            self._issue(report, "sample-size", "warning", ("sampling",), "The quantitative sample size is not justified by a power analysis or a stated formula.")
        if approach in {QUAL, MIXED} and not has_cue(size, SAMPLE_SIZE_QUAL):
            self._issue(report, "sample-size", "info" if approach == MIXED else "warning", ("sampling",), "The qualitative sample size is not justified by saturation or information power.")

    def _techniques(self, report: ParadigmReport, approach: str, strategy: Strategy | None, collection: set[str], analysis: set[str], quality: set[str], has_collection: bool, has_analysis: bool) -> None:
        if approach in {QUANT, QUAL} and collection and approach not in collection and "both" not in collection:
            self._issue(report, "collection-approach", "warning", ("collection", "approach"), f"The data collection methods produce {next(iter(collection))} data, but the design is {approach}." + (f" {strategy.name} usually uses {', '.join(strategy.collection)}." if strategy else ""))
        if approach and has_analysis:
            has_quant, has_qual = bool(analysis & {QUANT, "both"}), bool(analysis & {QUAL, "both"})
            if approach == QUANT and not has_quant:
                self._issue(report, "analysis-approach", "error", ("analysis", "approach"), "The design is quantitative but no statistical analysis is planned.")
            elif approach == QUAL and not has_qual:
                self._issue(report, "analysis-approach", "error", ("analysis", "approach"), "The design is qualitative but no interpretive analysis is planned.")
            elif approach == MIXED and not (has_quant and has_qual):
                self._issue(report, "analysis-approach", "warning", ("analysis", "approach"), "A mixed-methods design needs a statistical strand, an interpretive strand and an integration step.")
        if any(issue.check == "quality-criteria" for issue in report.issues):
            return
        if quality and approach == QUAL and quality == {VALIDITY}:
            self._issue(report, "quality-criteria", "warning", ("quality", "approach"), "A qualitative design argues trustworthiness rather than reliability and statistical validity.", ("Argue credibility, transferability, dependability and confirmability, with reflexivity.",))
        if quality and approach == QUANT and quality == {TRUSTWORTHINESS}:
            self._issue(report, "quality-criteria", "warning", ("quality", "approach"), "A quantitative design argues validity and reliability of its measures.", ("Report instrument validity and reliability, for example Cronbach's alpha and content validity.",))
        if quality and approach == MIXED and quality != {VALIDITY, TRUSTWORTHINESS}:
            self._issue(report, "quality-criteria", "info", ("quality", "approach"), "A mixed-methods design argues quality for each strand and for their integration.")

    def _claims(self, report: ParadigmReport, design: MethodDesign, approach: str, sampling: str) -> None:
        claims = " ".join((design.claims, *design.quality))
        if not has_cue(claims, GENERALISATION_CLAIMS):
            return
        if approach == QUAL:
            self._issue(report, "generalisation-claim", "warning", ("quality", "approach"), "The design claims generalisation, which qualitative research does not support statistically.", ("Argue transferability and give thick description of the setting.",))
        elif sampling == "non-probability":
            self._issue(report, "generalisation-claim", "warning", ("sampling",), "The design claims generalisation from a non-probability sample.", ("Use probability sampling, or limit the claim to the sample and argue transferability.",))


LAYER_LABELS = dict(LAYERS)


def method_text(design: MethodDesign) -> str:
    """Serialise a method design as one labelled paragraph per field for the provenance ledger."""
    rows = (("Paradigm", design.paradigm), ("Approach to theory", design.logic), ("Methodological choice", design.approach), ("Strategy", design.strategy), ("Time horizon", design.time_horizon), ("Sampling", design.sampling), ("Sample size", design.sample_size), ("Data collection", design.data_collection), ("Analysis", design.analysis), ("Quality criteria", design.quality), ("Hypotheses", design.hypotheses), ("Research questions", design.questions), ("Claims", design.claims))
    parts = []
    for label, value in rows:
        if isinstance(value, tuple):
            value = "\n".join(f"{index}. {item}" for index, item in enumerate(value, 1))
        if value:
            parts.append(f"{label}: {value}")
    return "\n\n".join(parts)


def method_flags(report: ParadigmReport) -> list[dict[str, str]]:
    return [{"anchor": LAYER_LABELS[layer], "severity": issue.severity, "verdict": issue.check, "message": issue.message} for issue in report.issues if issue.severity != "info" for layer in issue.layers]
