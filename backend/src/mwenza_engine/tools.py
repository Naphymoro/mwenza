from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    description: str
    risk: str = "low"
    approval_required: bool = False


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("scope_workspace", "Scope workspace", "Resolve the selected sources and current evidence boundary."),
    ToolSpec("list_sources", "List sources", "Inspect source metadata without reading outside the workspace."),
    ToolSpec("retrieve_evidence", "Retrieve evidence", "Search page-aware evidence with citations."),
    ToolSpec("extract_claims", "Extract claims", "Prepare reviewable claim candidates from evidence passages."),
    ToolSpec("compare_evidence", "Compare evidence", "Place source passages side by side for human review."),
    ToolSpec("flag_limitations", "Flag limitations", "Identify method and evidence limitations for review."),
    ToolSpec("check_alignment", "Check golden thread", "Test alignment across problem, gap, questions, theory, design and analysis."),
    ToolSpec("audit_citations", "Audit citations", "Check each cited claim in a draft against the passage it cites."),
    ToolSpec("inspect_graph", "Inspect graph", "Read provenance-linked entities and candidate relations."),
    ToolSpec("draft_artifact", "Draft artifact", "Create a citation-aware research artefact."),
    ToolSpec("plan_connector", "Plan connector", "Design a compliant future source connector.", "medium", True),
    ToolSpec("plan_run", "Plan analysis run", "Create a reproducible execution plan without running code.", "medium", True),
    ToolSpec("execute_code", "Execute code", "Run approved code in an isolated sandbox.", "high", True),
)


def tool_catalogue() -> list[dict[str, Any]]:
    return [asdict(item) for item in TOOLS]


def tools_for_skills(skill_ids: tuple[str, ...], skills: tuple[Any, ...]) -> list[str]:
    allowed = {tool for skill in skills if skill.id in skill_ids for tool in skill.tools}
    return sorted(allowed)
