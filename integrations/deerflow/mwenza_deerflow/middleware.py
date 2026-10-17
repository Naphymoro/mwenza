"""DeerFlow middleware that enforces Mwenza's constitution on every reply meant for a student.

Load it from DeerFlow's ``extensions_config.json``::

    "middlewares": [{"class": "mwenza_deerflow.middleware:MwenzaConstitutionMiddleware", "kwargs": {"agents": ["mwenza"]}}]

When the agent produces a final reply (no tool calls), the reply is checked against the evidence
in the conversation: results of Mwenza's own tools, and what the student wrote. A reply that breaks
a rule is withdrawn and the agent is asked, once per run, to revise it; the instruction travels
inside the model request and is never saved as a visible message. If the revision still breaks a
rule, the reply is sent with labels (unverified, retracted, annotated example) rather than silently.
The review is attached to the message as ``additional_kwargs["mwenza_constitution"]``.

The checks live in ``constitution.py``, a vendored copy of ``mwenza_engine/constitution.py``.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse, hook_config
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from .constitution import DRAFT_WORDS, Evidence, correction_prompt, remediate, review_reply

MWENZA_TOOLS = ("search_literature", "lookup_doi", "get_citations", "check_published_version", "check_golden_thread", "check_paradigm_fit", "navigate_methodology", "audit_citations")
CORRECTION_NAME = "mwenza_constitution"


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block if isinstance(block, str) else str(block.get("text", "")) for block in content if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text"))
    return ""


def with_text(content: Any, text: str) -> Any:
    """Replace a message's visible text, keeping any non-text blocks (reasoning, images) in place."""
    if not isinstance(content, list):
        return text
    result, placed = [], False
    for block in content:
        if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text"):
            if not placed:
                result.append({"type": "text", "text": text})
                placed = True
        else:
            result.append(block)
    return result if placed else [*result, {"type": "text", "text": text}]


def is_final_reply(message: AIMessage) -> bool:
    if message.tool_calls or getattr(message, "invalid_tool_calls", None):
        return False
    extra = message.additional_kwargs or {}
    if extra.get("tool_calls") or extra.get("function_call") or extra.get("deerflow_error_fallback") or extra.get("model_length_termination"):
        return False
    return (message.response_metadata or {}).get("finish_reason") not in {"tool_calls", "function_call"}


class MwenzaConstitutionMiddleware(AgentMiddleware):
    """Check final replies for grounding and integrity; ask for one revision, then label."""

    def __init__(self, agents: list[str] | None = None, tools: list[str] | None = None, max_revisions: int = 1, draft_words: int = DRAFT_WORDS, trusted_tools: list[str] | None = None) -> None:
        super().__init__()
        self.agents = set(agents or ["mwenza"])
        self.mwenza_tools = tuple(tools or MWENZA_TOOLS)  # not `tools`: AgentMiddleware.tools adds tools to the agent
        # Tool results that count as evidence. Default: Mwenza's tools only, so a web page or a
        # sub-agent's summary cannot vouch for a citation.
        self.trusted_tools = tuple(trusted_tools or self.mwenza_tools)
        self.max_revisions = max_revisions
        self.draft_words = draft_words
        self._lock = threading.Lock()
        self._revisions: dict[tuple[str, str], int] = {}
        self._pending: dict[tuple[str, str], str] = {}

    @staticmethod
    def _key(runtime: Any) -> tuple[str, str]:
        context = getattr(runtime, "context", None) or {}
        return str(context.get("thread_id") or "default"), str(context.get("run_id") or "default")

    @staticmethod
    def _matches(name: str | None, names: tuple[str, ...]) -> bool:
        return bool(name) and any(name == tool or name.endswith("_" + tool) for tool in names)

    def _active(self, messages: list[Any], runtime: Any) -> bool:
        context = getattr(runtime, "context", None) or {}
        if context.get("agent_name") in self.agents:
            return True
        return any(isinstance(message, ToolMessage) and self._matches(message.name, self.mwenza_tools) for message in messages)

    def _evidence(self, messages: list[Any]) -> Evidence:
        tool_outputs = [text_of(message.content) for message in messages if isinstance(message, ToolMessage) and self._matches(message.name, self.trusted_tools)]
        provided = [text_of(message.content) for message in messages if isinstance(message, HumanMessage) and not (message.additional_kwargs or {}).get("hide_from_ui") and message.name != CORRECTION_NAME]
        return Evidence.collect(tool_outputs, provided)

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not is_final_reply(last) or not self._active(messages, runtime):
            return None
        reply = text_of(last.content)
        if not reply.strip():
            return None
        review = review_reply(reply, self._evidence(messages), self.draft_words)
        if not review.findings:
            return None
        key = self._key(runtime)
        with self._lock:
            revisions = self._revisions.get(key, 0)
            if review.blocking and revisions < self.max_revisions:
                self._revisions[key] = revisions + 1
                self._pending[key] = correction_prompt(reply, review)
                return {"messages": [RemoveMessage(id=last.id)], "jump_to": "model"}
        extra = dict(last.additional_kwargs or {})
        extra["mwenza_constitution"] = review.to_dict() | {"revisions": revisions}
        return {"messages": [last.model_copy(update={"content": with_text(last.content, remediate(reply, review)), "additional_kwargs": extra})]}

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    def _augment(self, request: ModelRequest) -> ModelRequest:
        with self._lock:
            prompt = self._pending.pop(self._key(request.runtime), None)
        if prompt is None:
            return request
        return request.override(messages=[*request.messages, HumanMessage(content=prompt, name=CORRECTION_NAME, additional_kwargs={"hide_from_ui": True})])

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelCallResult:
        return handler(self._augment(request))

    async def awrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]) -> ModelCallResult:
        return await handler(self._augment(request))

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        key = self._key(runtime)
        with self._lock:
            self._revisions.pop(key, None)
            self._pending.pop(key, None)
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)
