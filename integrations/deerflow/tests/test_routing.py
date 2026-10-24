"""Hosted-to-local fallback in a real LangChain agent loop, with scripted models (no LLM). Synthetic content."""

import httpx
import openai
import pytest

pytest.importorskip("langchain")

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from mwenza_deerflow.routing import ROUTE_KEY, MwenzaModelFallbackMiddleware


class Scripted(GenericFakeChatModel):
    model_name: str = "scripted"
    error: object = None
    calls: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return super()._generate(messages, *args, **kwargs)


def cap_reached():
    request = httpx.Request("POST", "https://mwenza-ai.example/v1/chat/completions")
    return openai.RateLimitError("Mwenza's model has used today's allowance.", response=httpx.Response(429, request=request), body=None)


@tool
def navigate_methodology(answers: list[str]) -> str:
    """Walk the method navigator."""
    return '{"complete": false}'


def run(hosted, local, agent_name="mwenza"):
    router = MwenzaModelFallbackMiddleware()
    router._model = local
    agent = create_agent(model=hosted, tools=[navigate_methodology], middleware=[router])
    return agent.invoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] Help me choose a design")]}, context={"agent_name": agent_name, "thread_id": "t1", "run_id": "r1"})["messages"]


def local_model(*replies):
    return Scripted(model_name="mwenza-qwen3-14b", messages=iter([*replies]))


def test_a_capped_hosted_model_hands_the_whole_run_to_the_local_model():
    hosted = Scripted(model_name="@cf/zai-org/glm-5.3-flash", messages=iter([]), error=cap_reached())
    local = local_model(AIMessage(content="", tool_calls=[{"name": "navigate_methodology", "args": {"answers": []}, "id": "c1", "type": "tool_call"}]), AIMessage(content="What does your main question ask you to do?"))
    messages = run(hosted, local)
    assert messages[-1].content == "What does your main question ask you to do?"
    assert messages[-1].additional_kwargs[ROUTE_KEY] == {"route": "local-fallback", "model": "mwenza-local-14b", "reason": "RateLimitError"}
    assert hosted.calls == 1 and local.calls == 2, "after one failure the run stays on the local model"


def test_a_healthy_hosted_model_is_used_and_unmarked():
    hosted = Scripted(model_name="@cf/zai-org/glm-5.3-flash", messages=iter([AIMessage(content="Which paradigm fits?")]))
    local = local_model()
    messages = run(hosted, local)
    assert ROUTE_KEY not in messages[-1].additional_kwargs and local.calls == 0


def test_other_errors_other_agents_and_local_runs_do_not_fall_back():
    local = local_model(AIMessage(content="should not be used"))
    with pytest.raises(ValueError):
        run(Scripted(model_name="@cf/zai-org/glm-5.3-flash", messages=iter([]), error=ValueError("bad request")), local)
    with pytest.raises(openai.RateLimitError):
        run(Scripted(model_name="@cf/zai-org/glm-5.3-flash", messages=iter([]), error=cap_reached()), local, agent_name="ndim")
    with pytest.raises(openai.RateLimitError):  # a private run already on the local model is never moved anywhere
        run(Scripted(model_name="mwenza-qwen3-14b", messages=iter([]), error=cap_reached()), local)
    assert local.calls == 0


def test_a_missing_fallback_model_surfaces_the_providers_own_error():
    hosted = Scripted(model_name="@cf/zai-org/glm-5.3-flash", messages=iter([]), error=cap_reached())
    router = MwenzaModelFallbackMiddleware(fallback="not-in-config")

    def broken():
        raise ValueError("model not-in-config is not configured")

    router._fallback_model = broken
    agent = create_agent(model=hosted, tools=[navigate_methodology], middleware=[router])
    with pytest.raises(openai.RateLimitError):
        agent.invoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] hi")]}, context={"agent_name": "mwenza", "thread_id": "t9", "run_id": "r1"})
