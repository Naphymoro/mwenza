from __future__ import annotations

from pathlib import Path

from .graph import extract_graph
from .ingest import ingest_path
from .models import Answer, Citation, Entity, EvidenceSpan, Relation, SourceRecord
from .retrieval import HybridRetriever
from .agents import AgentOrchestrator


class NotebookEngine:
    def __init__(self):
        self.sources: dict[str, SourceRecord] = {}
        self.entities: list[Entity] = []
        self.relations: list[Relation] = []
        self.retriever = HybridRetriever()
        self.agents = AgentOrchestrator(self.query, lambda: len(self.sources), lambda: len(self.evidence))

    @property
    def evidence(self) -> list[EvidenceSpan]:
        return [span for source in self.sources.values() for span in source.pages]

    def ingest(self, path: str | Path, source_id: str | None = None) -> SourceRecord:
        record = ingest_path(path, source_id)
        self.sources[record.id] = record
        self.entities, self.relations = extract_graph(self.evidence)
        return record

    def query(self, question: str, selected_source_ids: set[str] | None = None, limit: int = 5) -> Answer:
        spans = self.evidence
        if selected_source_ids is not None:
            spans = [span for span in spans if span.source_id in selected_source_ids]
        results = self.retriever.search(question, spans, limit=limit)
        if not results:
            return Answer(question, "I do not have enough evidence in the selected sources to answer that reliably.", (), False, True, (), "no-retrieved-evidence")
        citations = tuple(
            Citation(result.span.source_id, self.sources[result.span.source_id].name, result.span.page, result.span.text[:280], min(1.0, result.score))
            for result in results
        )
        text = " ".join(result.span.text[:420].strip() for result in results[:3])
        return Answer(question, text, citations, True, False, tuple(result.score for result in results), "extractive-evidence-summary")
