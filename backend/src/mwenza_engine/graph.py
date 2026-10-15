from __future__ import annotations

import hashlib
import re

from .models import Entity, EvidenceSpan, Relation

ENTITY_PATTERN = re.compile(r"\b(?:[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,4}|[A-Z]{2,}(?:\d+)?)\b")
DATE_PATTERN = re.compile(r"\b(?:\d{1,2}[/-]){2}\d{2,4}\b|\b(?:19|20)\d{2}\b")


def _entity_id(label: str, kind: str) -> str:
    return "ent-" + hashlib.sha1(f"{kind}:{label.casefold()}".encode()).hexdigest()[:16]


def extract_graph(spans: list[EvidenceSpan]) -> tuple[list[Entity], list[Relation]]:
    """Create conservative candidate entities and co-occurrence edges.

    Edges are explicitly marked as candidates. This baseline never promotes
    co-occurrence into a verified causal or semantic relationship.
    """
    entities: dict[str, Entity] = {}
    relations: list[Relation] = []
    for span in spans:
        candidates: list[Entity] = []
        for match in list(ENTITY_PATTERN.finditer(span.text)) + list(DATE_PATTERN.finditer(span.text)):
            label = match.group(0).strip()
            if len(label) < 3:
                continue
            kind = "date" if DATE_PATTERN.fullmatch(label) else "named-phrase"
            entity = Entity(_entity_id(label, kind), label, kind, span.source_id, span.page, span.start + match.start(), span.start + match.end(), 0.62)
            entities.setdefault(entity.id, entity)
            candidates.append(entity)
        for subject, object_ in zip(candidates, candidates[1:]):
            if subject.id == object_.id:
                continue
            relations.append(Relation(subject.id, "co-occurs-with", object_.id, span.source_id, span.page, span.text[:500], 0.35))
    return list(entities.values()), relations
