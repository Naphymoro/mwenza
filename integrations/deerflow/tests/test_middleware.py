"""The constitution middleware in a real LangChain agent loop, driven by a scripted model (no LLM).

Runs where DeerFlow's dependencies are installed, for example inside the gateway container:
``python -m pytest /path/to/integrations/deerflow/tests`` with ``mwenza_deerflow`` importable.
All works, authors and DOIs are fictional.
"""

import json

import pytest

pytest.importorskip("langchain")

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from mwenza_deerflow.constitution import LABELS
from mwenza_deerflow.middleware import CORRECTION_NAME, MwenzaConstitutionMiddleware

RESULT = {"results": [{"title": "[SYNTHETIC] Distance to clinic and facility delivery", "authors": ["Achieng Otieno"], "year": 2021, "doi": "10.5555/synthetic.0001", "retracted": False, "preprint": False}]}
GROUNDED = "Otieno (2021) is a useful start (10.5555/synthetic.0001). Which districts does your study cover?"
INVENTED = "Otieno (2021) and Kamau (2018) both show this (10.5555/invented.9999)."


@tool
def search_literature(query: str) -> str:
    """Search scholarly literature."""
    return json.dumps(RESULT)


@tool
def lookup_doi(doi: str) -> list:
    """Look up a DOI. Returns MCP-style content blocks, as DeerFlow's MCP adapter does."""
    return [{"type": "text", "text": json.dumps({"result": RESULT["results"][0]})}]


@tool
def write_file(path: str, content: str) -> str:
    """Write a file."""
    WRITES.append(path)
    return "written"


WRITES: list = []


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return json.dumps({"results": [{"title": "Blog", "authors": ["Kamau"], "year": 2018, "doi": "10.5555/invented.9999"}]})


class ScriptedModel(GenericFakeChatModel):
    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}", "type": "tool_call"}])


def run(replies, agent_name="mwenza", tools=(search_literature,), first_tool="search_literature"):
    model = ScriptedModel(messages=iter([call(first_tool, {"doi": "10.5555/synthetic.0001"} if first_tool == "lookup_doi" else {"query": "distance facility delivery"}), *[AIMessage(content=text) for text in replies]]))
    model.seen = []
    agent = create_agent(model=model, tools=list(tools), middleware=[MwenzaConstitutionMiddleware()])
    state = agent.invoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] What should I read on distance and facility delivery?")]}, context={"agent_name": agent_name, "thread_id": "t1", "run_id": "r1"})
    return state["messages"], model.seen


def test_grounded_reply_passes_unchanged():
    messages, seen = run([GROUNDED])
    assert messages[-1].content == GROUNDED and "mwenza_constitution" not in messages[-1].additional_kwargs
    assert len(seen) == 2


def test_ungrounded_reply_is_withdrawn_and_revised_once():
    messages, seen = run([INVENTED, GROUNDED])
    assert messages[-1].content == GROUNDED
    assert not any(isinstance(message, AIMessage) and message.content == INVENTED for message in messages), "the withdrawn draft must not stay in the thread"
    correction = seen[2][-1]
    assert correction.name == CORRECTION_NAME and correction.additional_kwargs["hide_from_ui"]
    assert "Kamau (2018)" in correction.content and "10.5555/invented.9999" in correction.content
    assert not any(getattr(message, "name", None) == CORRECTION_NAME for message in messages), "the correction is never saved to the thread"


def test_second_failure_is_labelled_not_hidden():
    messages, seen = run([INVENTED, INVENTED])
    final = messages[-1]
    assert len(seen) == 3
    assert "Kamau (2018) " + LABELS["unverified-citation"] in final.content and LABELS["unverified-doi"] in final.content
    review = final.additional_kwargs["mwenza_constitution"]
    assert review["status"] == "blocked" and review["revisions"] == 1


def test_untrusted_tools_cannot_vouch_for_a_citation():
    messages, _ = run(["Kamau (2018) shows this.", "Kamau (2018) shows this."], tools=(web_search,), first_tool="web_search")
    assert LABELS["unverified-citation"] in messages[-1].content


def test_other_agents_are_left_alone():
    messages, seen = run([INVENTED], agent_name="ndim", tools=(web_search,), first_tool="web_search")
    assert messages[-1].content == INVENTED and len(seen) == 2


def test_evidence_is_read_from_mcp_content_blocks():
    messages, seen = run([GROUNDED], tools=(lookup_doi,), first_tool="lookup_doi")
    assert isinstance(messages[-2].content, list)
    assert messages[-1].content == GROUNDED and len(seen) == 2


def test_evidence_survives_when_a_later_middleware_truncates_the_result():
    """DeerFlow's output budget replaces large results with a preview; the evidence record must outlive that."""
    from langchain.agents.middleware import AgentMiddleware

    class Truncate(AgentMiddleware):
        def wrap_tool_call(self, request, handler):
            result = handler(request)
            return result.model_copy(update={"content": "[preview only: full output saved to /mnt/user-data/outputs/.tool-results/search_literature-abc.txt]"})

    model = ScriptedModel(messages=iter([call("search_literature", {"query": "distance"}), AIMessage(content=GROUNDED)]))
    model.seen = []
    agent = create_agent(model=model, tools=[search_literature], middleware=[Truncate(), MwenzaConstitutionMiddleware()])
    state = agent.invoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] Readings?")]}, context={"agent_name": "mwenza", "thread_id": "t2", "run_id": "r1"})
    tool_message = state["messages"][2]
    assert "preview only" in tool_message.content and tool_message.additional_kwargs["mwenza_evidence"]["dois"] == ["10.5555/synthetic.0001"]
    assert state["messages"][-1].content == GROUNDED and len(model.seen) == 2


def test_the_mwenza_agent_cannot_write_files_but_others_can():
    WRITES.clear()
    model = ScriptedModel(messages=iter([call("write_file", {"path": "/mnt/user-data/outputs/problem.md", "content": "[SYNTHETIC] paste me"}), AIMessage(content="What is the first move your problem statement needs to make?")]))
    model.seen = []
    agent = create_agent(model=model, tools=[write_file], middleware=[MwenzaConstitutionMiddleware()])
    state = agent.invoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] Write it for me")]}, context={"agent_name": "mwenza", "thread_id": "t3", "run_id": "r1"})
    refusal = state["messages"][2]
    assert WRITES == [] and refusal.status == "error" and "does not write files" in refusal.content
    model = ScriptedModel(messages=iter([call("write_file", {"path": "notes.md", "content": "x"}), AIMessage(content="done")]))
    model.seen = []
    create_agent(model=model, tools=[write_file], middleware=[MwenzaConstitutionMiddleware()]).invoke({"messages": [HumanMessage(content="hi")]}, context={"agent_name": "ndim", "thread_id": "t4", "run_id": "r1"})
    assert WRITES == ["notes.md"]


RUNS: list = []


@tool
def run_analysis(language: str, code: str, approval: str) -> str:
    """Run an analysis in the sandbox."""
    RUNS.append(approval)
    return '{"capsule_id": "0123456789ab", "stdout": "mean 3.2"}'


def run_with(student_message, approval):
    RUNS.clear()
    model = ScriptedModel(messages=iter([call("run_analysis", {"language": "python", "code": "print(1)", "approval": approval}), AIMessage(content="Which result would you like to look at first?")]))
    model.seen = []
    state = create_agent(model=model, tools=[run_analysis], middleware=[MwenzaConstitutionMiddleware()]).invoke(
        {"messages": [HumanMessage(content=student_message)]}, context={"agent_name": "mwenza", "thread_id": "t5", "run_id": "r1"})
    return state["messages"][2]


def test_code_runs_only_with_the_students_own_approval():
    exact = run_with("[SYNTHETIC STUDENT] Yes, run it", "Yes, run it")
    assert exact.status != "error" and RUNS == ["Yes, run it"]
    spacing = run_with("[SYNTHETIC STUDENT] Yes, RUN it   on the survey data please", "yes, run it on the survey data")
    assert spacing.status != "error" and RUNS == ["yes, run it on the survey data"]  # case and spacing are ignored
    invented = run_with("[SYNTHETIC STUDENT] What would the analysis show?", "The student approved this analysis")
    assert invented.status == "error" and "student's own words" in invented.content and RUNS == []
    empty = run_with("[SYNTHETIC STUDENT] ok", "")
    assert empty.status == "error" and RUNS == []
