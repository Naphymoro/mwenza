from __future__ import annotations

import re
from typing import Iterable

from .retrieval import tokenize

STOPWORDS = frozenset(
    "the and for with from that this these those into onto among between within about which what when where whose will would shall should "
    "could their there they them than then also such each other over under more most less least very can may might must been being have has "
    "had are was were not nor but its our your how why who does did doing done study research aim aims objective objectives question questions "
    "hypothesis hypotheses using use used based towards toward upon extent determine assess examine investigate explore establish evaluate".split()
)

ABBREVIATION = re.compile(r"\b(?:et al|e\.g|i\.e|vs|cf|dr|prof|fig|figs|no|nos|approx|ca|pp?|vol|eds?)\.", re.IGNORECASE)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[A-Z0-9\"'“‘(\[])|\n\s*\n")


def stem(token: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ness", "ment", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def content_terms(text: str, extra_stopwords: frozenset[str] = frozenset()) -> set[str]:
    return {stem(token) for token in tokenize(text) if token not in STOPWORDS and token not in extra_stopwords and not token.isdigit()}


def has_cue(text: str, cues: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"(?<![\w-]){re.escape(cue)}(?![\w-])", lowered) for cue in cues)


def sentence_bounds(text: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of sentences in ``text``.

    Abbreviations such as "et al." are masked with a same-length placeholder
    first, so offsets always index the original text.
    """
    masked = ABBREVIATION.sub(lambda match: match.group(0)[:-1] + "§", text)
    bounds: list[tuple[int, int]] = []
    start = 0
    for match in SENTENCE_BREAK.finditer(masked):
        _append_trimmed(text, start, match.start(), bounds)
        start = match.end()
    _append_trimmed(text, start, len(text), bounds)
    return bounds


def _append_trimmed(text: str, start: int, end: int, bounds: list[tuple[int, int]]) -> None:
    segment = text[start:end]
    stripped = segment.strip()
    if stripped:
        offset = start + segment.index(stripped)
        bounds.append((offset, offset + len(stripped)))
