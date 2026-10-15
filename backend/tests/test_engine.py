from pathlib import Path

from mwenza_engine.graph import extract_graph
from mwenza_engine.ingest import extract_text_file
from mwenza_engine.pipeline import NotebookEngine


def test_text_ingestion_preserves_source_spans():
    record = extract_text_file(Path("notes.txt"), "src-1", b"AIMS Research\fMwenza evidence")
    assert record.status == "ready"
    assert [span.page for span in record.pages] == [1, 2]
    assert all(span.source_id == "src-1" for span in record.pages)
    assert all(span.extraction_method == "text" for span in record.pages)


def test_graph_candidates_keep_provenance():
    record = extract_text_file(Path("notes.txt"), "src-1", b"AIMS Research supports Mwenza in 2026.")
    entities, relations = extract_graph(record.pages)
    assert entities
    assert all(entity.source_id == "src-1" for entity in entities)
    assert all(relation.extraction_method == "co-occurrence-candidate" for relation in relations)


def test_query_returns_citations_and_abstains_without_evidence(tmp_path):
    path = tmp_path / "paper.txt"
    path.write_text("Mwenza stores source evidence and page-level provenance.", encoding="utf-8")
    engine = NotebookEngine()
    source = engine.ingest(path)
    answer = engine.query("What does Mwenza store?", {source.id})
    assert answer.grounded is True
    assert answer.abstained is False
    assert answer.citations[0].source_id == source.id
    unknown = engine.query("What is the population of Mars?", {source.id})
    assert unknown.abstained is True
    assert unknown.citations == ()
