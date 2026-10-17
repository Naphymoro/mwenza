from __future__ import annotations

from pathlib import Path

from .graph import extract_graph
from .ingest import checksum_bytes, extract_text_file, ingest_path
from .provenance import ProvenanceLedger
from .models import Answer, Citation, Entity, EvidenceSpan, Relation, SourceRecord
from .retrieval import HybridRetriever
from .agents import AgentOrchestrator
from .citations import AuditReport, CitationAuditor, audit_flags
from .golden_thread import GoldenThreadChecker, GoldenThreadReport, ResearchDesign, design_flags, design_text


class NotebookEngine:
    def __init__(self, ledger_path: str | Path | None = None):
        self.sources: dict[str, SourceRecord] = {}
        self.entities: list[Entity] = []
        self.relations: list[Relation] = []
        self.retriever = HybridRetriever()
        self.golden_thread = GoldenThreadChecker()
        self.citation_auditor = CitationAuditor()
        self.ledger = ProvenanceLedger(ledger_path)
        self.agents = AgentOrchestrator(self.query, lambda: len(self.sources), lambda: len(self.evidence))

    @property
    def evidence(self) -> list[EvidenceSpan]:
        return [span for source in self.sources.values() for span in source.pages]

    def ingest(self, path: str | Path, source_id: str | None = None) -> SourceRecord:
        return self._store(ingest_path(path, source_id))

    def ingest_text(self, name: str, text: str, source_id: str | None = None) -> SourceRecord:
        data = text.encode("utf-8")
        record = extract_text_file(Path("source.txt"), source_id or f"src-{checksum_bytes(data)[:16]}", data)
        record.name = name
        return self._store(record)

    def _store(self, record: SourceRecord) -> SourceRecord:
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

    def check_golden_thread(self, design: ResearchDesign, selected_source_ids: set[str] | None = None) -> GoldenThreadReport:
        in_scope = [span for span in self.evidence if selected_source_ids is None or span.source_id in selected_source_ids]
        evidence = (lambda text: self.query(text, selected_source_ids)) if in_scope else None
        return self.golden_thread.check(design, evidence)

    def audit_citations(self, text: str, selected_source_ids: set[str] | None = None, references: dict[str, str] | None = None) -> AuditReport:
        in_scope = {source_id: record for source_id, record in self.sources.items() if selected_source_ids is None or source_id in selected_source_ids}
        return self.citation_auditor.audit(text, in_scope, references)

    def record_golden_thread(self, document_id: str, design: ResearchDesign, report: GoldenThreadReport, pasted_segments: list[str]) -> None:
        counts = report.to_dict()["counts"]
        summary = f"Golden thread check: {report.status}, {counts['error']} error(s), {counts['warning']} warning(s)"
        self.ledger.record_check(document_id, "golden-thread", design_text(design), pasted_segments, design_flags(report), summary)

    def record_citation_audit(self, document_id: str, text: str, report: AuditReport, pasted_segments: list[str]) -> None:
        flags = audit_flags(report)
        summary = f"Citation audit: {report.status}, {len(report.checks)} citation(s) checked, {len(flags)} sentence(s) flagged"
        self.ledger.record_check(document_id, "citation-audit", text, pasted_segments, flags, summary)

    def provenance_report(self, document_id: str, selected_source_ids: set[str] | None = None) -> dict[str, object]:
        in_scope = {source_id: record for source_id, record in self.sources.items() if selected_source_ids is None or source_id in selected_source_ids}
        return self.ledger.report(document_id, in_scope)
