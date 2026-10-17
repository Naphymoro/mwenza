from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .models import Answer
from .tools import tools_for_skills


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    purpose: str
    tools: tuple[str, ...]
    risk: str = "low"


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    role: str
    description: str
    skills: tuple[str, ...]
    operating_rules: tuple[str, ...]


@dataclass
class AgentRun:
    id: str
    agent_id: str
    objective: str
    status: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: Answer | None = None
    created_at: str = ""


SKILLS: tuple[Skill, ...] = (
    Skill("source-librarian", "Source librarian", "Find, scope, and organise evidence already present in the notebook.", ("list_sources", "retrieve_evidence")),
    Skill("claim-extractor", "Claim extraction", "Turn source passages into reviewable claims without inventing connective tissue.", ("retrieve_evidence", "extract_claims")),
    Skill("method-critic", "Methods critic", "Surface study-design, measurement, sampling, and inference limitations for human review.", ("retrieve_evidence", "flag_limitations"), "medium"),
    Skill("golden-thread", "Golden thread", "Check that problem, gap, questions, theory, design and analysis form one coherent argument.", ("check_alignment", "retrieve_evidence")),
    Skill("citation-auditor", "Citation auditor", "Verify that each cited source supports the claim made about it.", ("audit_citations", "retrieve_evidence")),
    Skill("contradiction-hunter", "Contradiction hunter", "Compare source-backed passages and identify disagreements that require inspection.", ("retrieve_evidence", "compare_evidence"), "medium"),
    Skill("research-scout", "Research scout", "Search published literature and plan lawful, provenance-preserving discovery.", ("search_literature", "plan_connector"), "medium"),
    Skill("reproducer", "Reproducer", "Define a reproducible analysis run and record its inputs, code, and outputs.", ("plan_run", "inspect_provenance"), "high"),
    Skill("evidence-editor", "Evidence editor", "Draft concise research artefacts with citations and explicit uncertainty.", ("retrieve_evidence", "draft_artifact")),
)

AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("librarian", "Librarian", "Evidence librarian", "Maps a question to the bounded source collection.", ("source-librarian", "claim-extractor"), ("Use only selected sources.", "Keep source scope visible.")),
    AgentSpec("methodologist", "Methodologist", "Scientific methods reviewer", "Finds methodological assumptions and limitations.", ("method-critic", "golden-thread", "claim-extractor"), ("Do not declare a study invalid without evidence.", "Separate critique from fact.", "Teach and question; never rewrite the student's argument.")),
    AgentSpec("skeptic", "Sceptic", "Adversarial evidence reviewer", "Searches for contradictions, missing evidence, and alternative explanations.", ("contradiction-hunter", "citation-auditor", "method-critic"), ("Prefer a precise uncertainty to false confidence.", "Make disagreements inspectable.")),
    AgentSpec("reproducer", "Reproducer", "Reproducibility engineer", "Turns a proposed analysis into a traceable execution plan.", ("reproducer",), ("Never execute untrusted code in the web process.", "Record inputs and environment.")),
    AgentSpec("scout", "Scout", "Research discovery planner", "Designs future monitoring and connector work with provenance safeguards.", ("research-scout",), ("Respect robots.txt, terms, rate limits, and licensing.", "Never bypass access controls.")),
    AgentSpec("synthesiser", "Synthesiser", "Grounded research synthesiser", "Produces a concise evidence-backed synthesis.", ("evidence-editor", "claim-extractor"), ("Cite every material claim.", "Abstain when evidence is insufficient.")),
)

WORKFLOWS: tuple[dict[str, Any], ...] = (
    {"id": "research-council", "name": "Research council", "description": "Synthesize evidence, challenge it, and review the method.", "stages": ("librarian", "synthesiser", "skeptic", "methodologist")},
    {"id": "reproducibility-review", "name": "Reproducibility review", "description": "Assess whether a proposed result can be rerun and audited.", "stages": ("librarian", "reproducer", "skeptic")},
)


def _serialise_skill(skill: Skill) -> dict[str, Any]:
    return asdict(skill)


def _serialise_agent(agent: AgentSpec) -> dict[str, Any]:
    result = asdict(agent)
    result["tools"] = tools_for_skills(agent.skills, SKILLS)
    return result


class AgentOrchestrator:
    """A deterministic orchestration boundary ready for model/tool adapters.

    This layer deliberately does not pretend that a language model has run.
    It creates an auditable plan and uses the existing grounded engine for the
    evidence step. Model providers can be added behind this contract later.
    """

    def __init__(self, query: Callable[..., Answer], source_count: Callable[[], int], evidence_count: Callable[[], int]):
        self.query = query
        self.source_count = source_count
        self.evidence_count = evidence_count
        self.runs: dict[str, AgentRun] = {}

    def catalogue(self) -> dict[str, Any]:
        return {"agents": [_serialise_agent(item) for item in AGENTS], "skills": [_serialise_skill(item) for item in SKILLS], "workflows": list(WORKFLOWS), "principles": ["evidence-first", "abstain-on-missing-evidence", "human-review", "reproducible-runs", "least-privilege-tools"]}

    def run(self, agent_id: str, objective: str, source_ids: set[str] | None = None) -> AgentRun:
        agent = next((item for item in AGENTS if item.id == agent_id), None)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        run_id = f"run-{len(self.runs) + 1:04d}"
        run = AgentRun(run_id, agent.id, objective, "running", created_at=datetime.now(timezone.utc).isoformat())
        run.steps.append({"tool": "scope_workspace", "status": "completed", "details": {"sources": self.source_count(), "evidence_spans": self.evidence_count()}})
        run.steps.append({"tool": "apply_policy", "status": "completed", "details": {"rules": list(agent.operating_rules)}})
        answer = self.query(objective, source_ids)
        run.steps.append({"tool": "retrieve_evidence", "status": "completed" if answer.citations else "abstained", "details": {"citations": len(answer.citations), "grounded": answer.grounded}})
        run.answer = answer
        run.status = "completed" if answer.grounded else "needs-review"
        self.runs[run_id] = run
        return run

    def serialise_run(self, run: AgentRun) -> dict[str, Any]:
        result = {"id": run.id, "agent_id": run.agent_id, "objective": run.objective, "status": run.status, "steps": run.steps, "created_at": run.created_at}
        if run.answer:
            result["answer"] = {"text": run.answer.text, "grounded": run.answer.grounded, "abstained": run.answer.abstained, "reason": run.answer.reason, "citations": [asdict(item) for item in run.answer.citations]}
        return result

    def workflow(self, workflow_id: str, objective: str, source_ids: set[str] | None = None) -> dict[str, Any]:
        workflow = next((item for item in WORKFLOWS if item["id"] == workflow_id), None)
        if workflow is None:
            raise ValueError(f"Unknown workflow: {workflow_id}")
        stages = []
        for agent_id in workflow["stages"]:
            run = self.run(agent_id, objective, source_ids)
            stages.append(self.serialise_run(run))
        grounded = all(stage.get("answer", {}).get("grounded", False) for stage in stages)
        citations = sorted({citation["source_id"] for stage in stages for citation in stage.get("answer", {}).get("citations", [])})
        return {"workflow_id": workflow_id, "objective": objective, "status": "completed" if grounded else "needs-review", "stages": stages, "citation_source_ids": citations}
