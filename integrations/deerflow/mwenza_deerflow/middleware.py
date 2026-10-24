"""DeerFlow middleware that enforces Mwenza's constitution on every reply meant for a student.

Load it from DeerFlow's ``extensions_config.json``::

    "middlewares": [{"class": "mwenza_deerflow.middleware:MwenzaConstitutionMiddleware", "kwargs": {"agents": ["mwenza"]}}]

When the agent produces a final reply (no tool calls), the reply is checked against the evidence
in the conversation: results of Mwenza's own tools, and what the student wrote. A reply that breaks
a rule is withdrawn and the agent is asked, once per run, to revise it; the instruction travels
inside the model request and is never saved as a visible message. If the revision still breaks a
rule, the reply is sent with labels (unverified, retracted, annotated example) rather than silently.
The review is attached to the message as ``additional_kwargs["mwenza_constitution"]``.

Evidence is recorded when a Mwenza tool returns, before DeerFlow's ToolOutputBudgetMiddleware (which sits outside
this one) moves a large result to a file and leaves a preview: the raw result's works, DOIs and links are stored as
``additional_kwargs["mwenza_evidence"]`` on the tool message. That record is saved with the thread, never sent to the
model, and cannot be changed from the sandbox.

The checks live in ``constitution.py``, a vendored copy of ``mwenza_engine/constitution.py``.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse, hook_config
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from .constitution import DRAFT_WORDS, Evidence, correction_prompt, remediate, review_reply

MWENZA_TOOLS = (
    "search_literature",
    "lookup_doi",
    "get_citations",
    "check_published_version",
    "check_golden_thread",
    "check_paradigm_fit",
    "navigate_methodology",
    "audit_citations",
    "check_reported_statistics",
    "check_sample_size",
    "run_analysis",
    "rerun_analysis",
)
# Writing tools let a model hand a student finished text outside the reply the constitution reads, so the mwenza
# agent never gets them, whichever path builds its tool set (the embedded client ignores agent tool groups).
WRITING_TOOLS = ("write_file", "str_replace", "bash", "edit_file", "python_repl")
WRITING_REFUSAL = "Mwenza does not write files or run commands for students. Give the student questions, an outline or a labelled example in your reply instead."
# Running code is a human checkpoint: run_analysis carries the student's approval, which must be their own words.
APPROVAL_TOOLS = ("run_analysis",)
APPROVAL_REFUSAL = "Not run: the approval must be the student's own words, quoted from their latest message. Show them what the analysis will do (data, method, outputs), ask whether to run it, and pass their reply as approval."
# The Reproducer checks figures the student reported. A figure the model made up and passed in as the student's
# own is refused, so a check can never vouch for invented results (Qwen3 did this on a data upload).
STUDENT_FIGURE_TOOLS = ("check_reported_statistics", "check_sample_size")
CONVENTIONAL = {"alpha": (0.05, 0.01, 0.1), "power": (0.8, 0.9, 0.95), "confidence": (0.9, 0.95, 0.99)}
FIGURE = re.compile(r"(?<![\w.])[-−]?(\d*\.?\d+)(\s?%)?")
UPLOADS = "/mnt/user-data/uploads/"
FIGURE_REFUSAL = (
    "Not checked: {figures} did not come from the student's messages or files. Check only figures the student reported, and ask them for any that are missing; "
    "never fill them in yourself. To get results from their data, propose an analysis (run_analysis) and ask for their approval."
)
CORRECTION_NAME = "mwenza_constitution"
EVIDENCE_KEY = "mwenza_evidence"
CUT_NOTICE = "\n\n(My answer was cut short here. Say 'continue' and I'll finish it.)"


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


def was_cut(message: AIMessage) -> bool:
    """The model hit its output limit. DeerFlow keeps the partial text but does not tell the student."""
    return (message.response_metadata or {}).get("finish_reason") == "length"


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
        provided = [text_of(message.content) for message in messages if isinstance(message, HumanMessage) and not (message.additional_kwargs or {}).get("hide_from_ui") and message.name != CORRECTION_NAME]
        evidence = Evidence.collect((), provided)
        for message in messages:
            if isinstance(message, ToolMessage) and self._matches(message.name, self.trusted_tools):
                record = (message.additional_kwargs or {}).get(EVIDENCE_KEY)
                if isinstance(record, dict):
                    evidence.merge(record)
                else:
                    evidence.add_text(text_of(message.content), "tool")  # recorded before this middleware existed
        return evidence

    def _record(self, result: Any) -> Any:
        if not isinstance(result, ToolMessage) or result.status == "error" or not self._matches(result.name, self.trusted_tools):
            return result
        extra = dict(result.additional_kwargs or {})
        extra[EVIDENCE_KEY] = Evidence.collect([text_of(result.content)]).to_dict()
        return result.model_copy(update={"additional_kwargs": extra})

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.lower().split())

    def _approved(self, request: ToolCallRequest) -> bool:
        """The approval quotes the student's latest visible message."""
        approval = self._normalise(str((request.tool_call.get("args") or {}).get("approval", "")))
        state = request.state if isinstance(request.state, dict) else {"messages": getattr(request.state, "messages", [])}
        latest = next((message for message in reversed(state.get("messages") or []) if isinstance(message, HumanMessage) and not (message.additional_kwargs or {}).get("hide_from_ui") and message.name != CORRECTION_NAME), None)
        return len(approval) >= 2 and latest is not None and approval in self._normalise(text_of(latest.content))

    @staticmethod
    def _student_figures(messages: list[Any]) -> set[float]:
        """Every number in the student's own messages and in the files they uploaded that the agent read."""
        upload_calls = {call.get("id") for message in messages if isinstance(message, AIMessage) for call in message.tool_calls or [] if str((call.get("args") or {}).get("path", "")).startswith(UPLOADS)}
        texts = [text_of(message.content) for message in messages if isinstance(message, HumanMessage) and not (message.additional_kwargs or {}).get("hide_from_ui") and message.name != CORRECTION_NAME]
        texts += [text_of(message.content) for message in messages if isinstance(message, ToolMessage) and message.tool_call_id in upload_calls]
        figures: set[float] = set()
        for match in FIGURE.finditer("\n".join(texts)):
            value = float(match.group(1))
            figures |= {value, value / 100} if match.group(2) else {value}
        return figures

    def _unsourced_figures(self, request: ToolCallRequest) -> list[str]:
        call = request.tool_call
        args = call.get("args") or {}
        if self._matches(call.get("name"), ("check_reported_statistics",)) and args.get("wording") == "researcher's own words":
            claimed = [(match.group(0).strip(), float(match.group(1)) / (100 if match.group(2) else 1)) for match in FIGURE.finditer(str(args.get("text", "")))]
        elif self._matches(call.get("name"), ("check_sample_size",)):
            parameters = args.get("parameters") if isinstance(args.get("parameters"), dict) else {}
            claimed = [(f"{key} = {value}", float(value)) for key, value in parameters.items() if isinstance(value, (int, float)) and not isinstance(value, bool) and value not in CONVENTIONAL.get(key, ())]
            if isinstance(args.get("reported_n"), int):
                claimed.append((f"n = {args['reported_n']}", float(args["reported_n"])))
        else:
            return []
        state = request.state if isinstance(request.state, dict) else {"messages": getattr(request.state, "messages", [])}
        known = self._student_figures(state.get("messages") or [])
        return list(dict.fromkeys(label for label, value in claimed if not any(abs(value - figure) <= 1e-9 for figure in known)))

    def _refuse_writing(self, request: ToolCallRequest) -> ToolMessage | None:
        call = request.tool_call
        context = getattr(request.runtime, "context", None) or {}
        if call.get("name") in WRITING_TOOLS and context.get("agent_name") in self.agents:
            return ToolMessage(content=WRITING_REFUSAL, name=call.get("name"), tool_call_id=call.get("id") or "", status="error")
        if self._matches(call.get("name"), APPROVAL_TOOLS) and not self._approved(request):
            return ToolMessage(content=APPROVAL_REFUSAL, name=call.get("name"), tool_call_id=call.get("id") or "", status="error")
        context = getattr(request.runtime, "context", None) or {}
        if context.get("agent_name") in self.agents and (unsourced := self._unsourced_figures(request)):
            return ToolMessage(content=FIGURE_REFUSAL.format(figures=", ".join(unsourced)), name=call.get("name"), tool_call_id=call.get("id") or "", status="error")
        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]) -> ToolMessage | Command:
        return self._refuse_writing(request) or self._record(handler(request))

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]) -> ToolMessage | Command:
        return self._refuse_writing(request) or self._record(await handler(request))

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
        notice = CUT_NOTICE if was_cut(last) else ""
        if not review.findings:
            return {"messages": [last.model_copy(update={"content": with_text(last.content, reply + notice)})]} if notice else None
        key = self._key(runtime)
        with self._lock:
            revisions = self._revisions.get(key, 0)
            if review.blocking and revisions < self.max_revisions:
                self._revisions[key] = revisions + 1
                self._pending[key] = correction_prompt(reply, review)
                return {"messages": [RemoveMessage(id=last.id)], "jump_to": "model"}
        extra = dict(last.additional_kwargs or {})
        extra["mwenza_constitution"] = review.to_dict() | {"revisions": revisions}
        return {"messages": [last.model_copy(update={"content": with_text(last.content, remediate(reply, review) + notice), "additional_kwargs": extra})]}

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
