from pathlib import Path

from mwenza_engine.pipeline import NotebookEngine


def test_agent_catalogue_and_run_are_auditable(tmp_path: Path):
    path = tmp_path / "paper.txt"
    path.write_text("Mwenza stores evidence with provenance.", encoding="utf-8")
    engine = NotebookEngine()
    source = engine.ingest(path)
    catalogue = engine.agents.catalogue()
    assert {agent["id"] for agent in catalogue["agents"]} >= {"librarian", "skeptic", "reproducer"}
    run = engine.agents.run("synthesiser", "What does Mwenza store?", {source.id})
    result = engine.agents.serialise_run(run)
    assert result["status"] == "completed"
    assert result["steps"][-1]["tool"] == "retrieve_evidence"
    assert result["answer"]["citations"]
