from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .models import SourceRecord
from .text import content_terms, has_cue, sentence_bounds

SUPPORTED = 0.5
PARTIAL = 0.25
MIN_CLAIM_TERMS = 3
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
JUDGED = ("supported", "partial", "contrasting", "misquoted-number", "unrelated")

REPORTING_WORDS = frozenset(
    "found find finds reported report reports showed show shows shown argued argue argues noted note notes observed observe observes suggested "
    "suggest suggests demonstrated demonstrate demonstrates indicated indicate indicates according concluded conclude concludes revealed reveal "
    "reveals stated state states confirmed confirm confirms al".split()
)

YEAR = r"(?:1[89]|20)\d{2}[a-z]?"
PARENTHETICAL = re.compile(rf"\(([^()]*?\b{YEAR}\b[^()]*)\)")
NARRATIVE = re.compile(rf"\b(?P<authors>[A-Z][\w'’-]+(?:\s+(?:et\s+al\.?|and|&)(?:\s+[A-Z][\w'’-]+)?)?)\s+\((?P<years>{YEAR}(?:\s*[,;]\s*{YEAR})*)\)")
NUMERIC = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
YEAR_TOKEN = re.compile(rf"\b{YEAR}\b")
PERCENTAGE = re.compile(r"\d\s*(?:%|per\s?cent|percent)", re.IGNORECASE)
LEAD_IN = re.compile(r"^(?:see also|see|e\.g\.,?|cf\.|for example,?|for a review,? see)\s+", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.,])\d+(?:\.\d+)?(?:\s*(?:%|per\s?cent|percent))?")

NEGATION_CUES = ("not", "no", "never", "neither", "nor", "without", "failed to", "non-significant", "nonsignificant", "insignificant", "lack of", "unrelated", "cannot")
INCREASE_CUES = ("more", "increase", "increased", "increases", "increasing", "higher", "greater", "improve", "improved", "improves", "rise", "rose", "positive", "positively", "raised", "gain", "gains")
DECREASE_CUES = ("less", "decrease", "decreased", "decreases", "decreasing", "lower", "fewer", "reduce", "reduced", "reduces", "reduction", "decline", "declined", "fell", "negative", "negatively", "drop", "dropped", "worse")
CLAIM_CUES = ("studies", "research shows", "research has shown", "evidence suggests", "evidence shows", "has been shown", "have shown", "it is well known", "it is widely", "literature", "previous research", "prior research", "scholars", "according to", "prevalence", "significantly", "is associated with", "are associated with", "was associated with", "were associated with")
OWN_WORK_CUES = ("this study", "the present study", "this thesis", "this paper", "we will", "i will", "will be", "we propose", "i propose")

GUIDANCE: dict[str, tuple[str, str]] = {
    "supported": ("The cited passage contains the substance of this claim.", "Have you represented the source's conditions and caveats as well as its main point?"),
    "partial": ("Only part of this claim appears in the cited passage. Examiners expect every element of a cited sentence to be in the cited work.", "Which part of this sentence does the source actually say, and where does the rest come from?"),
    "contrasting": ("The cited passage may say the opposite, for example 'no significant association' cited as evidence of an effect. Misrepresenting a source is an academic-integrity problem.", "Read the passage again: does it support your sentence, or qualify or contradict it?"),
    "misquoted-number": ("A number in the claim does not appear in the passage that best matches it. Statistics must match the source exactly, including units and denominators.", "Where in the source does this number appear, and does it describe the same population and measure?"),
    "unrelated": ("The cited source does not appear to discuss this claim. It may be the wrong reference, or the claim may need a different source.", "Which page of this source makes the point you are citing it for?"),
    "unresolved": ("Mwenza could not match this citation to a source in scope, so it cannot be checked.", "Is this reference in your notebook? If so, link the citation to it."),
    "unknown": ("The claim has too little content to compare reliably against the source.", "Can you make the claim more specific?"),
    "needs-citation": ("Statistics, statements about prior research and other factual claims need a citation; otherwise they read as your own unsupported assertion.", "Who established this, and where can a reader check it?"),
}
SEVERITY = {"supported": "", "partial": "warning", "contrasting": "error", "misquoted-number": "error", "unrelated": "error", "unresolved": "warning", "unknown": "info", "needs-citation": "warning"}


@dataclass(frozen=True)
class CitationMarker:
    label: str
    key: str
    start: int
    end: int


@dataclass(frozen=True)
class Passage:
    source_id: str
    source_name: str
    page: int | None
    start: int
    end: int
    quote: str


@dataclass
class CitationCheck:
    label: str
    key: str
    source_id: str | None
    source_name: str | None
    resolution: str
    verdict: str
    coverage: float | None = None
    passage: Passage | None = None
    candidates: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        return SEVERITY[self.verdict]


@dataclass
class SentenceAudit:
    index: int
    start: int
    end: int
    text: str
    claim: str
    citations: list[CitationCheck] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        levels = [check.severity for check in self.citations] + [SEVERITY[flag] for flag in self.flags]
        return next((level for level in SEVERITY_ORDER if level in levels), "")


@dataclass
class AuditReport:
    sentences: list[SentenceAudit] = field(default_factory=list)

    @property
    def checks(self) -> list[CitationCheck]:
        return [check for sentence in self.sentences for check in sentence.citations]

    @property
    def status(self) -> str:
        levels = {sentence.severity for sentence in self.sentences}
        return "needs-revision" if "error" in levels else "review" if "warning" in levels else "supported"

    def to_dict(self) -> dict[str, Any]:
        counts = {verdict: sum(1 for check in self.checks if check.verdict == verdict) for verdict in GUIDANCE if verdict != "needs-citation"}
        counts["needs-citation"] = sum(1 for sentence in self.sentences if "needs-citation" in sentence.flags)
        judged = sum(counts[verdict] for verdict in JUDGED)
        unresolved: dict[str, dict[str, Any]] = {}
        for check in self.checks:
            if check.verdict == "unresolved":
                unresolved.setdefault(check.key, {"key": check.key, "label": check.label, "candidates": list(check.candidates)})
        return {
            "status": self.status,
            "counts": counts,
            "citations_checked": len(self.checks),
            "supported_share": round(counts["supported"] / judged, 3) if judged else None,
            "sentences": [self._sentence_dict(sentence) for sentence in self.sentences],
            "unresolved": list(unresolved.values()),
            "guidance": {verdict: {"severity": SEVERITY[verdict], "teach": teach, "ask": ask} for verdict, (teach, ask) in GUIDANCE.items()},
            "method": "deterministic sentence matching of each cited claim against the cited source; verdicts flag what to reread, they do not replace reading the source",
        }

    @staticmethod
    def _sentence_dict(sentence: SentenceAudit) -> dict[str, Any]:
        result = {key: value for key, value in asdict(sentence).items() if key != "citations"}
        result["severity"] = sentence.severity
        result["citations"] = [{**asdict(check), "severity": check.severity} for check in sentence.citations]
        return result


def _numbers(text: str) -> set[float]:
    values: set[float] = set()
    for match in NUMBER.finditer(text):
        raw = re.sub(r"\s*(?:%|per\s?cent|percent)$", "", match.group(0))
        is_percent = raw != match.group(0)
        value = float(raw.replace(",", ""))
        if not is_percent and "." not in raw and (value < 10 or (raw.isdigit() and 1800 <= value <= 2099)):
            continue
        values.add(value)
    return values


def _polarity(text: str) -> tuple[int, bool, bool]:
    """Multiply the signs of negation and direction words in order.

    Returns (sign, has_cues, has_negation). "Without autonomy ... less likely"
    multiplies to +1, the same as "greater autonomy ... higher odds".
    """
    text = re.sub(r"\b(?:more|less|fewer|greater|lower|higher) than\b", " ", text.lower())
    sign, cues, negated = 1, False, False
    for cue_set, cue_sign in ((NEGATION_CUES, -1), (INCREASE_CUES, 1), (DECREASE_CUES, -1)):
        for cue in cue_set:
            hits = len(re.findall(rf"(?<![\w-]){re.escape(cue)}(?![\w-])", text))
            if hits:
                cues = True
                negated = negated or cue_set is NEGATION_CUES
                sign *= cue_sign ** hits
    return sign, cues, negated


def _conflicts(claim: str, passage: str) -> str | None:
    claim_sign, claim_cues, _ = _polarity(claim)
    passage_sign, passage_cues, passage_negated = _polarity(passage)
    if not claim_cues:
        return "the passage negates what the claim asserts" if passage_negated and passage_sign < 0 else None
    if passage_cues and claim_sign != passage_sign:
        return "the claim and the passage point in opposite directions; check negations and words such as higher or lower"
    return None


def _first_surname(authors: str) -> str:
    for token in re.findall(r"[A-Z][\w'’-]+", authors):
        if token.lower() not in {"et", "and"}:
            return re.sub(r"['’]s$", "", token).lower()
    return ""


def find_citations(sentence: str) -> list[CitationMarker]:
    markers: list[CitationMarker] = []
    for match in NARRATIVE.finditer(sentence):
        surname = _first_surname(match.group("authors"))
        for year in YEAR_TOKEN.findall(match.group("years")):
            markers.append(CitationMarker(f"{match.group('authors')} ({year})", f"{surname}-{year}", match.start(), match.end()))
    for match in PARENTHETICAL.finditer(sentence):
        for part in match.group(1).split(";"):
            part = LEAD_IN.sub("", part.strip())
            years = YEAR_TOKEN.findall(part)
            first = YEAR_TOKEN.search(part)
            authors = part[: first.start()].strip(" ,") if first else ""
            if not years or not re.match(r"[A-Z]", authors):
                continue
            surname = _first_surname(authors)
            markers.extend(CitationMarker(f"{authors}, {year}", f"{surname}-{year}", match.start(), match.end()) for year in years)
    for match in NUMERIC.finditer(sentence):
        numbers: list[int] = []
        for part in re.split(r"\s*,\s*", match.group(1)):
            bounds = [int(value) for value in re.split(r"\s*[-–]\s*", part)]
            numbers.extend(range(bounds[0], bounds[-1] + 1) if len(bounds) == 2 and bounds[1] - bounds[0] < 50 else bounds)
        markers.extend(CitationMarker(f"[{number}]", f"ref-{number}", match.start(), match.end()) for number in numbers)
    unique: dict[str, CitationMarker] = {}
    for marker in markers:
        unique.setdefault(marker.key, marker)
    return list(unique.values())


def _strip_markers(sentence: str, markers: Iterable[CitationMarker]) -> str:
    claim = sentence
    for start, end in sorted({(marker.start, marker.end) for marker in markers}, reverse=True):
        claim = claim[:start] + claim[end:]
    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", claim)).strip()


class CitationAuditor:
    """Checks each cited claim in a draft against the passage it cites.

    Matching is deterministic: claim terms are compared with single sentences
    and adjacent sentence pairs from the cited source, then checked for
    negation or direction conflicts and for numbers missing from the passage.
    Citations that cannot be matched to a source are reported as unresolved
    rather than guessed.
    """

    def audit(self, text: str, sources: Mapping[str, SourceRecord], references: Mapping[str, str] | None = None) -> AuditReport:
        references = references or {}
        report = AuditReport()
        windows: dict[str, list[tuple[Passage, set[str], set[float]]]] = {}
        for index, (start, end) in enumerate(sentence_bounds(text), 1):
            sentence = text[start:end]
            markers = find_citations(sentence)
            audit = SentenceAudit(index, start, end, sentence, _strip_markers(sentence, markers))
            for marker in markers:
                audit.citations.append(self._check(marker, audit.claim, sources, references, windows))
            if not markers and self._needs_citation(audit.claim):
                audit.flags.append("needs-citation")
            report.sentences.append(audit)
        return report

    def _needs_citation(self, claim: str) -> bool:
        if has_cue(claim, OWN_WORK_CUES):
            return False
        return has_cue(claim, CLAIM_CUES) or bool(PERCENTAGE.search(claim))

    def _resolve(self, marker: CitationMarker, sources: Mapping[str, SourceRecord], references: Mapping[str, str]) -> tuple[str | None, str, tuple[str, ...]]:
        mapped = references.get(marker.key)
        if mapped:
            return (mapped, "mapped", ()) if mapped in sources else (None, "unresolved", ())
        if marker.key.startswith("ref-"):
            return None, "unresolved", ()
        surname, _, year = marker.key.rpartition("-")
        year_digits = year[:4]
        candidates = tuple(
            source_id for source_id, record in sources.items()
            if re.search(rf"(?<![a-z]){re.escape(surname)}(?![a-z])", self._haystack(record)) and re.search(rf"(?<!\d){year_digits}(?!\d)", self._haystack(record))
        )
        if len(candidates) == 1:
            return candidates[0], "auto-matched", ()
        return None, "unresolved", candidates

    @staticmethod
    def _haystack(record: SourceRecord) -> str:
        opening = " ".join(span.text for span in record.pages[:2])[:4000]
        return f"{record.name} {record.metadata.get('title', '')} {record.metadata.get('authors', '')} {opening}".lower()

    def _windows(self, record: SourceRecord, cache: dict[str, list[tuple[Passage, set[str], set[float]]]]) -> list[tuple[Passage, set[str], set[float]]]:
        if record.id not in cache:
            items = []
            for span in record.pages:
                bounds = sentence_bounds(span.text)
                for size in (1, 2):
                    for position in range(len(bounds) - size + 1):
                        start, end = bounds[position][0], bounds[position + size - 1][1]
                        quote = span.text[start:end]
                        items.append((Passage(record.id, record.name, span.page, span.start + start, span.start + end, quote), content_terms(quote, REPORTING_WORDS), _numbers(quote)))
            cache[record.id] = items
        return cache[record.id]

    def _check(self, marker: CitationMarker, claim: str, sources: Mapping[str, SourceRecord], references: Mapping[str, str], cache: dict[str, list[tuple[Passage, set[str], set[float]]]]) -> CitationCheck:
        source_id, resolution, candidates = self._resolve(marker, sources, references)
        if source_id is None:
            check = CitationCheck(marker.label, marker.key, None, None, resolution, "unresolved", candidates=candidates)
            check.notes.append(f"{len(candidates)} sources match this author and year; link the right one." if candidates else "No source in scope matches this citation.")
            return check
        record = sources[source_id]
        check = CitationCheck(marker.label, marker.key, source_id, record.name, resolution, "unknown")
        claim_terms, claim_numbers = content_terms(claim, REPORTING_WORDS), _numbers(claim)
        if len(claim_terms) < MIN_CLAIM_TERMS:
            check.notes.append("Too few content words in the claim to compare.")
            return check
        best: tuple[float, float, Passage, set[str], set[float]] | None = None
        for passage, terms, numbers in self._windows(record, cache):
            coverage = len(claim_terms & terms) / len(claim_terms)
            score = coverage + 0.1 * len(claim_numbers & numbers) - 0.001 * len(passage.quote) / 100
            if best is None or score > best[0]:
                best = (score, coverage, passage, terms, numbers)
        if best is None:
            check.verdict = "unrelated"
            check.notes.append("The cited source has no extractable text.")
            return check
        _, coverage, passage, terms, numbers = best
        check.coverage, check.passage = round(coverage, 3), passage
        missing_terms = sorted(claim_terms - terms)
        if coverage < PARTIAL:
            check.verdict = "unrelated"
            return check
        conflict = _conflicts(claim, passage.quote)
        missing_numbers = sorted(claim_numbers - numbers)
        if conflict:
            check.verdict = "contrasting"
            check.notes.append(f"Possible contrast: {conflict}.")
        elif missing_numbers:
            check.verdict = "misquoted-number"
            check.notes.append(f"Not found in the passage: {', '.join(f'{value:g}' for value in missing_numbers)}.")
        else:
            check.verdict = "supported" if coverage >= SUPPORTED else "partial"
        if check.verdict == "partial" and missing_terms:
            check.notes.append(f"Claim terms not in the passage: {', '.join(missing_terms[:8])}.")
        return check


def audit_flags(report: AuditReport) -> list[dict[str, str]]:
    flags = []
    for sentence in report.sentences:
        if sentence.severity in {"error", "warning"}:
            verdicts = [check.verdict for check in sentence.citations if check.severity in {"error", "warning"}] + sentence.flags
            flags.append({"anchor": sentence.text, "severity": sentence.severity, "verdict": ", ".join(verdicts), "message": "; ".join(dict.fromkeys(verdicts))})
    return flags
