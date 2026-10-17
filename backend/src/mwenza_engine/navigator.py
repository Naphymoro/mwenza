"""Methodology Decision Navigator: a decision tree from the research question
to a coherent design (approach, strategy, sampling, data collection,
analysis and quality criteria), with the reasoning behind each step.

Designs are built from the shared catalogue in ``methodology.py``, and the
tests run every design through the paradigm-method checker, so the navigator
cannot recommend a design the checker would flag.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .methodology import MIXED, PARADIGMS, QUAL, QUANT, strategy_by_key

QUALITY = {
    QUANT: ("Content and construct validity of the instruments", "Reliability, for example Cronbach's alpha or test-retest"),
    QUAL: ("Credibility through member checking and triangulation", "Transferability through thick description", "Dependability and confirmability through an audit trail and reflexivity"),
}


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    hint: str = ""
    next: str = ""
    design: str = ""


@dataclass(frozen=True)
class Step:
    id: str
    question: str
    why: str
    options: tuple[Option, ...]


@dataclass(frozen=True)
class Design:
    key: str
    name: str
    strategy: str
    strategy_key: str
    approach: str
    logic: str
    time_horizon: str
    sampling: str
    sample_size: str
    data_collection: tuple[str, ...]
    analysis: tuple[str, ...]
    reasons: tuple[str, ...]
    cautions: tuple[str, ...] = ()
    extra_quality: tuple[str, ...] = ()

    @property
    def quality(self) -> tuple[str, ...]:
        base = QUALITY[QUANT] + QUALITY[QUAL] + ("Legitimation of how the two strands are integrated",) if self.approach == MIXED else QUALITY[self.approach]
        return base + self.extra_quality

    @property
    def paradigms(self) -> list[str]:
        return [paradigm.name for paradigm in PARADIGMS if self.strategy_key in paradigm.strategies and self.approach in paradigm.approaches and (not self.logic or self.logic in paradigm.logics)]

    def to_dict(self) -> dict[str, Any]:
        strategy = strategy_by_key(self.strategy_key)
        result = asdict(self)
        result.update({"quality": list(self.quality), "paradigms": self.paradigms, "strategy_family": strategy.name})
        return result

    def method_fields(self) -> dict[str, Any]:
        """The design as fields for the paradigm-method checker (the paradigm is the student's choice)."""
        return {"approach": {QUANT: "Quantitative", QUAL: "Qualitative", MIXED: "Mixed methods"}[self.approach], "logic": self.logic.capitalize(), "strategy": self.strategy, "time_horizon": self.time_horizon,
                "sampling": self.sampling, "sample_size": self.sample_size, "data_collection": list(self.data_collection), "analysis": list(self.analysis), "quality": list(self.quality)}


DESIGNS: dict[str, Design] = {design.key: design for design in (
    Design("rct", "Randomised controlled trial", "Randomised controlled trial", "experiment", QUANT, "deductive", "Longitudinal (baseline and follow-up)",
           "Random sampling of eligible participants, then random assignment to study arms", "Power analysis (for example with G*Power) for the smallest effect worth detecting",
           ("Structured questionnaire or validated scales", "Clinical or field measurements"), ("Intention-to-treat comparison with t-tests or ANOVA", "Regression adjusting for baseline values"),
           ("You can assign the intervention, so random assignment rules out most alternative explanations.", "Randomisation makes the groups comparable, which supports causal claims."),
           ("Register the trial and its outcomes before recruitment.", "Ethics review must cover what the control group receives.")),
    Design("quasi", "Quasi-experiment", "Quasi-experimental design with a comparison group", "quasi-experiment", QUANT, "deductive", "Longitudinal (before and after the intervention)",
           "Comparison groups chosen to resemble the intervention group, with random sampling within each group", "Power analysis that allows for clustering of participants within sites",
           ("Structured questionnaire", "Routine records before and after the intervention"), ("Difference-in-differences regression", "Propensity score matching with logistic regression"),
           ("The intervention is assigned without randomisation, so a comparison group and before-and-after data are the next best way to estimate its effect.",),
           ("Argue why the comparison group would have followed the same trend without the intervention.",)),
    Design("cohort", "Cohort study", "Prospective cohort study", "cohort", QUANT, "deductive", "Longitudinal (repeated measurement of the same people)",
           "Random sampling of a defined population at baseline", "Power analysis that allows for expected loss to follow-up",
           ("Structured questionnaire at each wave", "Routine or clinical records"), ("Survival analysis", "Multilevel regression for repeated measures"),
           ("You observe rather than assign the exposure, and the question is about change over time, so the same people are followed.",),
           ("Plan how to limit and report loss to follow-up.",)),
    Design("case-control", "Case-control study", "Case-control study", "case-control", QUANT, "deductive", "Cross-sectional (looking back from the outcome)",
           "Cases with the outcome and controls without it, matched on key characteristics", "Power calculation for the smallest odds ratio worth detecting",
           ("Structured questionnaire about past exposures", "Clinical or routine records"), ("Conditional logistic regression reporting odds ratios",),
           ("The outcome is rare, so starting from people who have it is far more efficient than following a whole population.",),
           ("Recall bias: people with the outcome may remember exposures differently.",)),
    Design("survey", "Cross-sectional survey", "Cross-sectional household survey", "survey", QUANT, "deductive", "Cross-sectional",
           "Stratified random sampling", "Cochran's formula or a power calculation for the main comparison",
           ("Structured questionnaire",), ("Descriptive statistics", "Chi-square tests", "Multivariable regression"),
           ("You observe relationships at one point in time and the outcome is common, so a probability sample of the population fits.",),
           ("Associations from one point in time do not show cause and effect; say so in the limitations.",)),
    Design("secondary", "Secondary data analysis", "Secondary data analysis of an existing national dataset", "secondary", QUANT, "deductive", "Cross-sectional",
           "Probability sampling as designed by the original study; describe it", "Fixed by the dataset; report a power or precision calculation for your analysis",
           ("Existing dataset with documented questionnaire",), ("Descriptive statistics", "Survey-weighted logistic regression"),
           ("The variables you need are already measured, so reanalysing existing data saves time and covers large populations.",),
           ("Check the data-use licence and that the original measures fit your constructs.",)),
    Design("phenomenology", "Phenomenology", "Phenomenology", "phenomenology", QUAL, "inductive", "Cross-sectional",
           "Purposive sampling of people who have lived the experience", "Until saturation; typically a small, information-rich sample",
           ("In-depth interviews",), ("Interpretative phenomenological analysis",),
           ("The question is about what an experience means to the people living it, which phenomenology is built to study.",),
           ("Bracket or reflexively record your own assumptions about the experience.",)),
    Design("ethnography", "Ethnography", "Ethnography", "ethnography", QUAL, "inductive", "Longitudinal (prolonged fieldwork)",
           "Purposive selection of a setting and key informants", "Prolonged engagement until saturation",
           ("Participant observation", "Field notes", "In-depth interviews"), ("Thematic analysis of field notes and interviews",),
           ("The question is about shared practices and culture, which are best understood by spending time with the group.",),
           ("Negotiate access and your role in the setting before fieldwork.",)),
    Design("grounded-theory", "Grounded theory", "Grounded theory", "grounded theory", QUAL, "inductive", "Cross-sectional",
           "Theoretical sampling guided by the emerging analysis", "Until theoretical saturation",
           ("Semi-structured interviews",), ("Constant comparison through open, axial and selective coding",),
           ("You want to build a theory of how a process works, so the theory must come from the data rather than be tested on it.",),
           ("Collect and analyse data in alternating rounds; the sample cannot be fixed in advance.",)),
    Design("narrative", "Narrative inquiry", "Narrative inquiry", "narrative inquiry", QUAL, "inductive", "Cross-sectional",
           "Purposive sampling of storytellers", "A small number of participants, justified by information power",
           ("Life history interviews",), ("Narrative analysis",),
           ("The question is about how people tell and make sense of their lives, which narrative inquiry keeps whole rather than breaking into codes.",),
           ("Agree with participants how their stories will be represented.",)),
    Design("case-study", "Qualitative case study", "Qualitative case study", "case study", QUAL, "inductive", "Cross-sectional",
           "Purposive selection of information-rich cases", "Cases chosen and justified by information power",
           ("Semi-structured interviews", "Documents", "Participant observation"), ("Thematic analysis within each case", "Cross-case synthesis"),
           ("The question needs an in-depth understanding of one or a few bounded cases in their real context.",),
           ("Define the boundaries of each case clearly.",)),
    Design("par", "Participatory action research", "Participatory action research with community partners", "action research", QUAL, "abductive", "Longitudinal (cycles of action and reflection)",
           "Purposive selection with community partners", "Information power, agreed with the community",
           ("Community workshops", "Focus groups", "Talking circles"), ("Thematic analysis in cycles of action and reflection",),
           ("The problem is defined with the community and the aim is change, so participants act as co-researchers.",),
           ("Agree ownership of data and findings with the community before starting.",),
           ("Relational accountability through community validation",)),
    Design("explanatory", "Explanatory sequential mixed methods", "Explanatory sequential mixed methods", "mixed methods", MIXED, "abductive", "Cross-sectional",
           "Stratified random sampling for the survey, then purposive sampling of survey respondents for interviews", "Power calculation for the survey; saturation for the interviews",
           ("Structured questionnaire", "In-depth interviews"), ("Multivariable regression", "Thematic analysis", "Joint display to integrate the two strands"),
           ("You need to measure first and then explain the results, so a quantitative phase is followed by a qualitative one.",),
           ("Decide in advance which survey results will guide the choice of interviewees.",)),
    Design("exploratory", "Exploratory sequential mixed methods", "Exploratory sequential mixed methods", "mixed methods", MIXED, "abductive", "Cross-sectional",
           "Purposive sampling for interviews, then stratified random sampling for the survey", "Saturation for the interviews; power calculation for the survey",
           ("In-depth interviews", "Structured questionnaire built from the interview findings"), ("Thematic analysis", "Factor analysis of the new instrument", "Joint display to integrate the two strands"),
           ("You need to explore first because the concepts are not yet well defined, then build and test a measure.",),
           ("Allow time to develop and pilot the instrument between the phases.",)),
    Design("convergent", "Convergent mixed methods", "Convergent parallel mixed methods", "mixed methods", MIXED, "abductive", "Cross-sectional",
           "Stratified random sampling for the survey and purposive sampling for interviews, at the same time", "Power calculation for the survey; saturation for the interviews",
           ("Structured questionnaire", "In-depth interviews"), ("Descriptive statistics and regression", "Thematic analysis", "Joint display comparing the two strands"),
           ("You want both kinds of evidence on the same question at once, to compare and corroborate them.",),
           ("Plan what you will do if the two strands disagree.",)),
    Design("design-science", "Design science research", "Design science research", "design science", MIXED, "abductive", "Longitudinal (build and evaluation cycles)",
           "Purposive selection of intended users for each evaluation cycle, and random sampling for comparative tests", "Power calculation for comparative evaluation; information power for user interviews",
           ("Prototype evaluation sessions", "Usability questionnaire", "User interviews"), ("Descriptive statistics of usability scores", "Thematic analysis of user feedback"),
           ("The aim is to build and evaluate an artefact (a tool, intervention or system), which design science structures into build-and-evaluate cycles.",),
           ("State the design principles your artefact contributes, not just the artefact.",)),
)}

STEPS: dict[str, Step] = {step.id: step for step in (
    Step("start", "What does your main research question ask you to do?", "The purpose of the question decides the approach: testing needs measurement, understanding needs depth, and both need a mixed design.", (
        Option("test", "Explain or test relationships, effects or differences", "For example: does distance affect skilled birth attendance?", next="q-test"),
        Option("explore", "Understand experiences, meanings, cultures or processes", "For example: how do mothers decide where to give birth?", next="q-explore"),
        Option("both", "Measure something and understand why or how", "For example: how common is home birth, and why do women choose it?", next="q-mixed"),
        Option("change", "Solve a practical problem by changing practice or building something", "For example: co-design a referral system with health volunteers.", next="q-change"),
    )),
    Step("q-test", "Can you control who receives the intervention or exposure?", "Control over assignment decides how strongly you can claim cause and effect.", (
        Option("random", "Yes, I can assign it at random", design="rct"),
        Option("nonrandom", "It is assigned, but not at random", "For example a policy rolled out in some districts first.", design="quasi"),
        Option("observe", "No, I observe it as it happens", next="q-time"),
        Option("existing", "No, and existing data already measure it", "For example a Demographic and Health Survey.", design="secondary"),
    )),
    Step("q-time", "Does your question ask how things change over time?", "Change can only be measured by observing the same people more than once.", (
        Option("yes", "Yes, I need to follow the same people", design="cohort"),
        Option("no", "No, a single point in time is enough", next="q-rare"),
    )),
    Step("q-rare", "Is the outcome rare in the population?", "A rare outcome needs a design that starts from the people who have it.", (
        Option("rare", "Yes, it is rare", "For example maternal death or a rare disease.", design="case-control"),
        Option("common", "No, it is common", design="survey"),
    )),
    Step("q-explore", "What is the focus of your question?", "Each qualitative tradition is built for a different kind of understanding.", (
        Option("lived", "The lived experience of a phenomenon", design="phenomenology"),
        Option("culture", "The shared practices and culture of a group", design="ethnography"),
        Option("process", "How a process works, to build a theory of it", design="grounded-theory"),
        Option("stories", "People's life stories or narratives", design="narrative"),
        Option("case", "One or a few bounded cases in depth", design="case-study"),
        Option("community", "A community-defined issue, studied with the community", "Fits Afrocentric, Ubuntu and Indigenous research.", design="par"),
    )),
    Step("q-mixed", "Which part comes first?", "The order of the strands decides which one shapes the other.", (
        Option("measure-first", "Measure first, then explain the results in depth", design="explanatory"),
        Option("explore-first", "Explore first, then build and test a measure", design="exploratory"),
        Option("together", "Collect both at the same time and compare them", design="convergent"),
    )),
    Step("q-change", "Who drives the change?", "Change led by participants and change led by a designed artefact need different structures.", (
        Option("community", "Practitioners or community members, in cycles of action and reflection", design="par"),
        Option("artefact", "You build an intervention, tool or system and evaluate it", design="design-science"),
    )),
)}


class NavigatorError(ValueError):
    pass


def catalogue() -> dict[str, Any]:
    return {"start": "start", "steps": {key: asdict(step) for key, step in STEPS.items()}, "designs": {key: design.to_dict() for key, design in DESIGNS.items()}}


def recommend(answers: list[str]) -> dict[str, Any]:
    """Follow the chosen option ids from the start step; return the path taken and, at a leaf, the design."""
    step, path = STEPS["start"], []
    for index, answer in enumerate(answers):
        option = next((item for item in step.options if item.id == answer), None)
        if option is None:
            raise NavigatorError(f"'{answer}' is not an option at step {index + 1} ({step.question}).")
        path.append({"step": step.id, "question": step.question, "why": step.why, "answer": option.label})
        if option.design:
            if index != len(answers) - 1:
                raise NavigatorError("The answers continue past a finished design.")
            design = DESIGNS[option.design]
            return {"complete": True, "path": path, "design": design.to_dict(), "method_fields": design.method_fields()}
        step = STEPS[option.next]
    return {"complete": False, "path": path, "next": asdict(step)}
