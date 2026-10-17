from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import SourceRecord
from .text import content_terms

GENESIS = "0" * 64
SHINGLE = 6
VERBATIM_MIN_WORDS = 10
LINEAGE_SIMILARITY = 0.5
PASTED, MIXED = 0.6, 0.2
WORD = re.compile(r"[\w'’-]+")

ORIGIN_LABELS = {
    "typed": "Typed or edited in Mwenza",
    "pasted": "Pasted from outside Mwenza (origin not recorded)",
    "mixed": "Partly pasted from outside Mwenza",
    "present-at-start": "Already present when tracking began (origin not recorded)",
}


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    timestamp: str
    document_id: str
    kind: str
    actor: str
    summary: str
    details: dict[str, Any]
    content_hash: str | None
    prev_hash: str
    hash: str
    text: str | None = None

    def hashed_fields(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key not in {"hash", "text"}}


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _words(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0).lower(), match.start(), match.end()) for match in WORD.finditer(text)]


def _shingles(words: list[str], size: int = SHINGLE) -> set[tuple[str, ...]]:
    return {tuple(words[index:index + size]) for index in range(len(words) - size + 1)}


def _covered(words: list[str], shingles: set[tuple[str, ...]], size: int = SHINGLE) -> list[bool]:
    covered = [False] * len(words)
    for index in range(len(words) - size + 1):
        if tuple(words[index:index + size]) in shingles:
            for position in range(index, index + size):
                covered[position] = True
    return covered


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    a, b = content_terms(left), content_terms(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _inside_quotes(text: str, start: int) -> bool:
    before = text[:start]
    return before.count('"') % 2 == 1 or before.count("“") > before.count("”")


class ProvenanceLedger:
    """Append-only, hash-chained record of how a document was written.

    Each event's hash covers its fields and the previous event's hash, and
    snapshot text is bound by ``content_hash``, so edits to the stored log are
    detectable by ``verify``. The ledger is tamper-evident, not tamper-proof:
    whoever controls the store can rewrite the whole chain.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[LedgerEvent] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.events.append(LedgerEvent(**json.loads(line)))

    def append(self, document_id: str, kind: str, actor: str, summary: str, details: dict[str, Any] | None = None, text: str | None = None) -> LedgerEvent:
        fields_ = {"seq": len(self.events) + 1, "timestamp": datetime.now(timezone.utc).isoformat(), "document_id": document_id, "kind": kind, "actor": actor, "summary": summary, "details": details or {}, "content_hash": _sha(text) if text is not None else None, "prev_hash": self.events[-1].hash if self.events else GENESIS}
        event = LedgerEvent(**fields_, hash=_digest(fields_), text=text)
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return event

    def verify(self) -> dict[str, Any]:
        previous = GENESIS
        for event in self.events:
            if event.prev_hash != previous or event.hash != _digest(event.hashed_fields()):
                return {"valid": False, "broken_at": event.seq, "reason": "event fields or chain link do not match their hash"}
            if event.text is not None and _sha(event.text) != event.content_hash:
                return {"valid": False, "broken_at": event.seq, "reason": "stored text does not match its recorded hash"}
            previous = event.hash
        return {"valid": True, "broken_at": None, "reason": "", "head": previous}

    def for_document(self, document_id: str) -> list[LedgerEvent]:
        return [event for event in self.events if event.document_id == document_id]

    def record_check(self, document_id: str, tool: str, text: str, pasted_segments: Iterable[str], flags: list[dict[str, str]], summary: str) -> tuple[LedgerEvent, LedgerEvent]:
        pasted = [segment for segment in pasted_segments if segment.strip()]
        snapshot = self.append(document_id, "text-snapshot", "student", f"Submitted {len(paragraphs(text))} paragraph(s) to {tool}", {"tool": tool, "pasted_segments": pasted, "paste_source": "reported by the browser"}, text)
        check = self.append(document_id, "ai-check", "mwenza", summary, {"tool": tool, "snapshot_seq": snapshot.seq, "flags": flags})
        return snapshot, check

    def report(self, document_id: str, sources: Mapping[str, SourceRecord]) -> dict[str, Any]:
        events = self.for_document(document_id)
        snapshots = [event for event in events if event.kind == "text-snapshot"]
        checks = [event for event in events if event.kind == "ai-check"]
        attribution = self._attribute(snapshots, checks, sources) if snapshots else []
        integrity = self.verify()
        return {
            "document_id": document_id,
            "integrity": integrity,
            "events": [{key: value for key, value in asdict(event).items() if key != "text"} for event in reversed(events)],
            "paragraphs": attribution,
            "declaration": self._declaration(document_id, snapshots, checks, attribution, integrity),
            "origin_labels": ORIGIN_LABELS,
            "method": "paragraph lineage by text similarity across recorded snapshots; paste reports come from the browser; verbatim matches use runs of 10 or more identical words against sources in scope",
        }

    def _attribute(self, snapshots: list[LedgerEvent], checks: list[LedgerEvent], sources: Mapping[str, SourceRecord]) -> list[dict[str, Any]]:
        checks_by_snapshot: dict[int, list[LedgerEvent]] = {}
        for check in checks:
            checks_by_snapshot.setdefault(check.details["snapshot_seq"], []).append(check)
        source_shingles = {source_id: _shingles([word for word, _, _ in _words(" ".join(span.text for span in record.pages))]) for source_id, record in sources.items()}
        latest = paragraphs(snapshots[-1].text or "")
        results = []
        for position, paragraph in enumerate(latest, 1):
            lineage = self._lineage(paragraph, snapshots)
            first_index = lineage[0][0]
            words = [word for word, _, _ in _words(paragraph)]
            paste_shingles = set().union(*(_shingles([word for word, _, _ in _words(segment)]) for index, _ in lineage for segment in snapshots[index].details.get("pasted_segments", [])))
            pasted_share = (sum(_covered(words, paste_shingles)) / len(words)) if words and paste_shingles else 0.0
            origin = "pasted" if pasted_share >= PASTED else "mixed" if pasted_share >= MIXED else "present-at-start" if first_index == 0 else "typed"
            feedback, revised = [], False
            for index, version in lineage:
                for check in checks_by_snapshot.get(snapshots[index].seq, []):
                    hits = [flag for flag in check.details["flags"] if self._flag_in(flag, version)]
                    if hits:
                        later = [text for later_index, text in lineage if later_index > index]
                        changed = any(text != version for text in later)
                        revised = revised or changed
                        feedback.append({"seq": check.seq, "timestamp": check.timestamp, "tool": check.details["tool"], "flags": hits, "revised_after": changed})
            results.append({
                "index": position,
                "text": paragraph,
                "origin": origin,
                "origin_label": ORIGIN_LABELS[origin],
                "pasted_share": round(pasted_share, 3),
                "first_seen": snapshots[first_index].timestamp,
                "versions": len({text for _, text in lineage}),
                "feedback": feedback,
                "revised_after_feedback": revised,
                "open_feedback": next((len(entry["flags"]) for entry in feedback if entry["seq"] in {check.seq for check in checks_by_snapshot.get(snapshots[-1].seq, [])}), 0),
                "verbatim": self._verbatim(paragraph, sources, source_shingles),
            })
        return results

    def _lineage(self, paragraph: str, snapshots: list[LedgerEvent]) -> list[tuple[int, str]]:
        """Follow a paragraph backwards through snapshots while it stays recognisable."""
        lineage = [(len(snapshots) - 1, paragraph)]
        current = paragraph
        for index in range(len(snapshots) - 2, -1, -1):
            candidates = paragraphs(snapshots[index].text or "")
            best = max(candidates, key=lambda candidate: _similarity(current, candidate), default=None)
            if best is None or _similarity(current, best) < LINEAGE_SIMILARITY:
                break
            lineage.insert(0, (index, best))
            current = best
        return lineage

    @staticmethod
    def _flag_in(flag: Mapping[str, str], paragraph: str) -> bool:
        anchor = flag.get("anchor", "")
        return bool(anchor) and (anchor in paragraph or paragraph.startswith(f"{anchor}:"))

    @staticmethod
    def _verbatim(paragraph: str, sources: Mapping[str, SourceRecord], source_shingles: Mapping[str, set[tuple[str, ...]]]) -> list[dict[str, Any]]:
        tokens = _words(paragraph)
        words = [word for word, _, _ in tokens]
        matches = []
        for source_id, shingles in source_shingles.items():
            covered = _covered(words, shingles)
            index = 0
            while index < len(covered):
                if not covered[index]:
                    index += 1
                    continue
                end = index
                while end + 1 < len(covered) and covered[end + 1]:
                    end += 1
                if end - index + 1 >= VERBATIM_MIN_WORDS:
                    start_char, end_char = tokens[index][1], tokens[end][2]
                    matches.append({"source_id": source_id, "source_name": sources[source_id].name, "words": end - index + 1, "text": paragraph[start_char:end_char], "quoted": _inside_quotes(paragraph, start_char)})
                index = end + 1
        return matches

    @staticmethod
    def _declaration(document_id: str, snapshots: list[LedgerEvent], checks: list[LedgerEvent], attribution: list[dict[str, Any]], integrity: Mapping[str, Any]) -> str:
        if not snapshots:
            return f"No activity has been recorded for '{document_id}'."
        tools: dict[str, int] = {}
        for check in checks:
            tools[check.details["tool"]] = tools.get(check.details["tool"], 0) + 1
        flagged = [item for item in attribution if item["feedback"]]
        revised = [item for item in flagged if item["revised_after_feedback"]]
        origins = {origin: sum(1 for item in attribution if item["origin"] == origin) for origin in ORIGIN_LABELS}
        still_open = [item for item in attribution if item["open_feedback"]]
        unquoted = [item for item in attribution if any(not match["quoted"] for match in item["verbatim"])]
        tool_names = {"golden-thread": "research-design alignment checks (golden thread)", "citation-audit": "citation checks", "paradigm-method": "paradigm-method fit checks"}
        lines = [
            f"# AI-use declaration: {document_id}",
            "",
            f"Recorded from {snapshots[0].timestamp[:16].replace('T', ' ')} UTC to {snapshots[-1].timestamp[:16].replace('T', ' ')} UTC in the Mwenza provenance ledger.",
            "",
            "## How Mwenza was used",
            "",
            *[f"- {count} {tool_names.get(tool, tool)}" if count != 1 else f"- 1 {tool_names.get(tool, tool).replace('checks', 'check')}" for tool, count in sorted(tools.items())],
            "- Mwenza gives feedback and questions. It does not generate or rewrite the student's text.",
            "",
            "## The current text",
            "",
            f"- {_count(len(attribution), 'paragraph')} in the latest recorded version.",
            *[f"- {count} {ORIGIN_LABELS[origin][0].lower()}{ORIGIN_LABELS[origin][1:]}." for origin, count in origins.items() if count],
            ("- Mwenza raised feedback on 1 paragraph, which was " + ("revised" if revised else "not revised") + " afterwards." if len(flagged) == 1 else f"- Mwenza raised feedback on {len(flagged)} paragraphs; {len(revised)} of them were revised afterwards.") if flagged else "- Mwenza raised no feedback on the current paragraphs.",
            *([f"- {_count(len(still_open), 'paragraph')} still {'has' if len(still_open) == 1 else 'have'} open feedback from the latest check."] if still_open else []),
        ]
        if unquoted:
            lines.append(f"- {_count(len(unquoted), 'paragraph')} {'contains' if len(unquoted) == 1 else 'contain'} 10 or more consecutive words identical to a source in scope without quotation marks. These should be quoted and cited, or paraphrased.")
        lines += [
            "",
            "## Limits of this record",
            "",
            "- Paste events are reported by the student's browser. Text written in other tools before tracking began has no recorded origin.",
            "- The ledger is tamper-evident, not tamper-proof: " + ("its hash chain verified intact" if integrity["valid"] else f"its hash chain FAILED verification at event {integrity['broken_at']}") + (f" (head {integrity['head'][:16]})." if integrity.get("head") else "."),
        ]
        return "\n".join(lines) + "\n"
