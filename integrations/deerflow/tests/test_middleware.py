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
