"""Mwenza's constitution: deterministic checks on what an agent is about to tell a student.

Two rules that no prompt, skill or Forge generation may relax:

* Grounding. Every DOI, link and author-year citation in a reply must come from evidence the
  agent actually holds in this conversation: a Mwenza tool result, or text the student supplied.
  Retracted works are never presented as evidence; preprints are named as preprints.
* Integrity. Mwenza teaches; it does not ghost-write. Long, finished prose that a student could
  paste into a thesis is flagged so it becomes questions, an outline or a labelled example.

The module is standard-library only and imports nothing else from ``mwenza_engine``, so the
DeerFlow middleware can vendor it unchanged (see ``integrations/deerflow``). Its citation
patterns follow ``citations.py``; keep the two in step. The prose check is word-count based and
advisory in spirit (long, declarative, not addressed to the student): the middleware asks the agent to rework once, then labels rather than deletes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

YEAR = r"(?:1[89]|20)\d{2}[a-z]?"
DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>()\[\]{}]+", re.IGNORECASE)
URL = re.compile(r"https?://[^\s\"'<>()\[\]{}]+", re.IGNORECASE)
SURNAME = r"[A-Z][\w'’-]+"
NARRATIVE = re.compile(rf"\b(?P<author>{SURNAME})(?:\s+(?:et\s+al\.?|(?:and|&)\s+{SURNAME}))?\s+\((?P<years>{YEAR}(?:\s*[,;]\s*{YEAR})*)\)")
PARENTHETICAL = re.compile(rf"\(([^()]*?\b{YEAR}\b[^()]*)\)")
CITE_IN_PARENS = re.compile(rf"(?P<author>{SURNAME})(?:\s+(?:et\s+al\.?|(?:and|&)\s+{SURNAME}))?,?\s+(?P<years>{YEAR}(?:\s*,\s*{YEAR})*)")
YEAR_TOKEN = re.compile(rf"\b{YEAR}\b")
SENTENCE_END = re.compile(r"[.!?](?:[\"'”’)\]]*)(?:\s|$)")
SECOND_PERSON = re.compile(r"\b(?:you|your|yours|yourself)\b", re.IGNORECASE)
LIST_LINE = re.compile(r"^\s*(?:[-*+•]|\d+[.)]|#{1,6}\s|>|\|)")
TRAILING_PUNCTUATION = ".,;:!?"

# Words that look like a surname before a year but are not one ("In (2019)", "Since 2020").
NOT_AUTHORS = frozenset(
    (
        "In On At By For From Since Until Before After During Between And Or The A An This That These Those See Also "
        "Table Figure Fig Page Chapter Section Version Phase Wave Round Year Spring Summer Autumn Fall Winter "
        "January February March April May June July August September October November December"
    ).split()
)

DRAFT_WORDS = 120
DRAFT_SENTENCES = 4
EXAMPLE_LABEL = "Annotated example"
LABELS = {
    "unverified-doi": "[unverified: this DOI did not come from Mwenza's search or from you]",
    "unverified-link": "[unverified: this link did not come from Mwenza's search or from you]",
    "unverified-citation": "[unverified: no matching work in this conversation]",
    "retracted": "[retracted: do not use as evidence]",
}
DRAFT_BANNER = f"**{EXAMPLE_LABEL}, not your text.** Use it to see the moves the writing makes; do not paste it into your thesis."
GUIDANCE = {
    "unverified-doi": "Cite only DOIs returned by a Mwenza tool in this conversation or supplied by the student. Search for the work, or remove the reference and say you could not find a source.",
    "unverified-link": "Link only to URLs returned by a Mwenza tool or supplied by the student.",
    "unverified-citation": "Every author-year citation must match a work (surname and year) returned by a Mwenza tool or supplied by the student. Search for it, or say plainly that you have no source.",
    "retracted": "This work is retracted. Do not present it as evidence; you may mention the retraction itself.",
    "preprint-uncaveated": "This work is a preprint. Say that it has not been peer reviewed, in the same sentence or the next.",
    "draftable-prose": "This paragraph reads as finished thesis text. Turn it into questions for the student, an outline of the moves to make, or a short example clearly labelled 'Annotated example'.",
}
BLOCKING = frozenset({"unverified-doi", "unverified-link", "unverified-citation", "retracted", "draftable-prose"})


def normalise_doi(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(TRAILING_PUNCTUATION)


def normalise_url(value: str) -> str:
    value = value.strip().rstrip(TRAILING_PUNCTUATION).lower()
    value = re.sub(r"^https?://(?:www\.)?", "", value)
    return value.rstrip("/")


def surname_key(name: str) -> str:
    """The family name of 'Achieng Otieno', 'Otieno, A.' or 'A. Otieno', lower-cased."""
    name = name.strip()
    if not name:
        return ""
    if "," in name:
        return name.split(",", 1)[0].strip().split()[-1].lower()
    return name.split()[-1].strip(".").lower()


@dataclass
class Work:
    doi: str = ""
    url: str = ""
    title: str = ""
    surnames: tuple[str, ...] = ()
    year: int | None = None
    retracted: bool = False
    preprint: bool = False
    origin: str = "tool"


@dataclass
class Evidence:
    """What the agent may cite: works from tool results plus DOIs and links the student supplied."""

    works: list[Work] = field(default_factory=list)
    dois: dict[str, Work] = field(default_factory=dict)
    urls: set[str] = field(default_factory=set)
    author_years: set[tuple[str, int]] = field(default_factory=set)

    @classmethod
    def collect(cls, tool_outputs: Iterable[str] = (), provided: Iterable[str] = ()) -> Evidence:
        evidence = cls()
        for text in tool_outputs:
            evidence.add_text(text, "tool")
        for text in provided:
            evidence.add_text(text, "student")
        return evidence

    def add_text(self, text: str, origin: str) -> None:
        if not text:
            return
        try:
            self._walk(json.loads(text), origin)
        except (TypeError, ValueError):
            pass
        for match in DOI.finditer(text):
            self.dois.setdefault(normalise_doi(match.group(0)), Work(doi=normalise_doi(match.group(0)), origin=origin))
        for match in URL.finditer(text):
            self.urls.add(normalise_url(match.group(0)))
        if origin == "student":
            # A reference list or draft the student pasted grounds the citations it contains.
            for author, year in cited_author_years(text):
                self.author_years.add((author.lower(), year))

    def _walk(self, node: Any, origin: str) -> None:
        if isinstance(node, list):
            for item in node:
                self._walk(item, origin)
        elif isinstance(node, dict):
            if any(key in node for key in ("doi", "title")) and ("authors" in node or "year" in node or "doi" in node):
                self._add_record(node, origin)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    self._walk(value, origin)

    def _add_record(self, record: dict[str, Any], origin: str) -> None:
        authors = record.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        year = record.get("year")
        work = Work(
            doi=normalise_doi(str(record.get("doi") or "")),
            url=str(record.get("url") or ""),
            title=str(record.get("title") or ""),
            surnames=tuple(key for key in (surname_key(str(author)) for author in authors if str(author) != "et al.") if key),
            year=year if isinstance(year, int) else None,
            retracted=bool(record.get("retracted")),
            preprint=bool(record.get("preprint")),
            origin=origin,
        )
        self.works.append(work)
        if work.doi:
            self.dois[work.doi] = work
        for link in (work.url, record.get("oa_url"), (record.get("published") or {}).get("url") if isinstance(record.get("published"), dict) else None):
            if link:
                self.urls.add(normalise_url(str(link)))
        if work.year:
            for surname in work.surnames:
                self.author_years.add((surname, work.year))

    def knows_author_year(self, author: str, year: int) -> bool:
        return (author.lower(), year) in self.author_years


def cited_author_years(text: str) -> list[tuple[str, int]]:
    return [(author, year) for author, year, _start, _end in _author_year_spans(text)]


def _author_year_spans(text: str) -> list[tuple[str, int, int, int]]:
    spans: list[tuple[str, int, int, int]] = []
    for match in NARRATIVE.finditer(text):
        if match.group("author") in NOT_AUTHORS:
            continue
        for year in YEAR_TOKEN.findall(match.group("years")):
            spans.append((match.group("author"), int(year[:4]), match.start(), match.end()))
    for match in PARENTHETICAL.finditer(text):
        inner_start = match.start(1)
        for part in re.finditer(r"[^;]+", match.group(1)):
            cite = CITE_IN_PARENS.search(part.group(0))
            if not cite or cite.group("author") in NOT_AUTHORS:
                continue
            for year in YEAR_TOKEN.findall(cite.group("years")):
                start = inner_start + part.start() + cite.start()
                spans.append((cite.group("author"), int(year[:4]), start, inner_start + part.start() + cite.end()))
    return spans


@dataclass
class Finding:
    kind: str
    excerpt: str
    start: int
    end: int
    blocking: bool
    guidance: str


@dataclass
class Review:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(finding.blocking for finding in self.findings)

    @property
    def status(self) -> str:
        return "blocked" if self.blocking else ("warnings" if self.findings else "pass")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [asdict(finding) for finding in self.findings]}


def _paragraphs(text: str) -> list[tuple[int, int]]:
    """(start, end) of prose paragraphs, skipping fenced code."""
    spans, start, fenced = [], None, False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            if start is not None:
                spans.append((start, offset))
                start = None
        elif not fenced:
            if stripped and start is None:
                start = offset
            elif not stripped and start is not None:
                spans.append((start, offset))
                start = None
        offset += len(line)
    if start is not None and not fenced:
        spans.append((start, offset))
    return spans


def _is_draftable(paragraph: str, previous: str, draft_words: int) -> bool:
    lines = [line for line in paragraph.splitlines() if line.strip()]
    if not lines or any(LIST_LINE.match(line) for line in lines):
        return False
    if EXAMPLE_LABEL.lower() in paragraph.lower()[:200] or EXAMPLE_LABEL.lower() in previous.lower()[-300:]:
        return False
    if "?" in paragraph or SECOND_PERSON.search(paragraph):
        return False  # questions, or talk addressed to the student, are teaching rather than thesis text
    return len(paragraph.split()) >= draft_words and len(SENTENCE_END.findall(paragraph)) >= DRAFT_SENTENCES


def review_reply(reply: str, evidence: Evidence, draft_words: int = DRAFT_WORDS) -> Review:
    review = Review()
    seen: set[tuple[str, str]] = set()

    def add(kind: str, excerpt: str, start: int, end: int) -> None:
        if (kind, excerpt.lower()) in seen:
            return
        seen.add((kind, excerpt.lower()))
        review.findings.append(Finding(kind, excerpt, start, end, kind in BLOCKING, GUIDANCE[kind]))

    doi_spans = []
    for match in DOI.finditer(reply):
        doi = normalise_doi(match.group(0))
        end = match.start() + len(match.group(0).rstrip(TRAILING_PUNCTUATION))
        doi_spans.append((match.start(), end))
        work = evidence.dois.get(doi)
        if work is None:
            add("unverified-doi", reply[match.start() : end], match.start(), end)
        elif work.retracted:
            add("retracted", reply[match.start() : end], match.start(), end)
        elif work.preprint and "preprint" not in _sentence_window(reply, match.start()).lower():
            add("preprint-uncaveated", reply[match.start() : end], match.start(), end)
    for match in URL.finditer(reply):
        end = match.start() + len(match.group(0).rstrip(TRAILING_PUNCTUATION))
        if any(start <= match.start() < stop or match.start() <= start < end for start, stop in doi_spans):
            continue  # a doi.org link: judged as a DOI above
        link = normalise_url(match.group(0))
        if link not in evidence.urls and "/" in link:
            add("unverified-link", reply[match.start() : end], match.start(), end)
    for author, year, start, end in _author_year_spans(reply):
        if not evidence.knows_author_year(author, year):
            add("unverified-citation", reply[start:end], start, end)
        else:
            for work in evidence.works:
                if work.year == year and author.lower() in work.surnames and work.retracted:
                    add("retracted", reply[start:end], start, end)
    previous = ""
    for start, end in _paragraphs(reply):
        paragraph = reply[start:end]
        if _is_draftable(paragraph, previous, draft_words):
            add("draftable-prose", paragraph.strip()[:160] + ("…" if len(paragraph.strip()) > 160 else ""), start, end)
        previous = paragraph
    review.findings.sort(key=lambda finding: finding.start)
    return review


def _sentence_window(text: str, position: int, reach: int = 300) -> str:
    """The sentence holding ``position`` and the one after it."""
    before = text[max(0, position - reach) : position]
    start = max(before.rfind(". "), before.rfind("\n")) + 1
    after = text[position : position + reach * 2]
    ends = [match.end() for match in SENTENCE_END.finditer(after)]
    stop = ends[1] if len(ends) > 1 else len(after)
    return before[start:] + after[:stop]


def remediate(reply: str, review: Review) -> str:
    """Label what the agent could not fix: unverified and retracted references, and draftable prose.

    Nothing the agent wrote is deleted; the student sees the label and the reason.
    """
    edits: list[tuple[int, str]] = []
    for finding in review.findings:
        if finding.kind == "draftable-prose":
            edits.append((finding.start, DRAFT_BANNER + "\n\n"))
        elif finding.kind in LABELS:
            edits.append((finding.end, " " + LABELS[finding.kind]))
    text = reply
    for position, insertion in sorted(edits, key=lambda edit: edit[0], reverse=True):
        text = text[:position] + insertion + text[position:]
    if review.blocking:
        text += "\n\n---\n*Mwenza's integrity check labelled parts of this reply. Labels show what could not be verified or what is an example rather than your own text.*"
    return text


def correction_prompt(reply: str, review: Review) -> str:
    """The hidden instruction that asks the agent to revise its draft reply once."""
    issues = "\n".join(f"- {finding.kind}: {finding.excerpt!r}. {finding.guidance}" for finding in review.findings)
    return (
        "<mwenza_constitution>\n"
        "Your draft reply to the student broke Mwenza's grounding or integrity rules, so it was not sent. Revise it and reply again.\n\n"
        f"Issues:\n{issues}\n\n"
        "You may call Mwenza's tools to find a source. If you cannot find one, say so plainly instead of citing.\n\n"
        f"Your draft:\n<draft>\n{reply}\n</draft>\n"
        "</mwenza_constitution>"
    )
