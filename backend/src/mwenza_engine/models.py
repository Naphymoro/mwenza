from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvidenceSpan:
    source_id: str
    page: int | None
    start: int
    end: int
    text: str
    extraction_method: Literal["text", "ocr", "manual"]
    confidence: float
    bbox: tuple[float, float, float, float] | None = None
    parser_version: str = "mwenza-extractor-0.1"


@dataclass
class SourceRecord:
    id: str
    name: str
    media_type: str
    checksum: str
    status: Literal["ready", "ocr_required", "failed"]
    created_at: str = field(default_factory=utc_now)
    version: int = 1
    pages: list[EvidenceSpan] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Citation:
    source_id: str
    source_name: str
    page: int | None
    quote: str
    confidence: float


@dataclass(frozen=True)
class Entity:
    id: str
    label: str
    kind: str
    source_id: str
    page: int | None
    span_start: int
    span_end: int
    confidence: float


@dataclass(frozen=True)
class Relation:
    subject_id: str
    predicate: str
    object_id: str
    source_id: str
    page: int | None
    evidence: str
    confidence: float
    extraction_method: str = "co-occurrence-candidate"


@dataclass(frozen=True)
class RetrievedEvidence:
    span: EvidenceSpan
    score: float
    lexical_score: float
    semantic_score: float = 0.0


@dataclass(frozen=True)
class Answer:
    question: str
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    abstained: bool
    retrieval_scores: tuple[float, ...] = ()
    reason: str = ""
