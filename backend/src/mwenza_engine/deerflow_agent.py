"""Mwenza's research chat through the DeerFlow gateway (phase H0 of docs/analysis/AGENTIC_HARNESS_DESIGN.md).

The engine, not the browser, talks to DeerFlow. It authenticates with DeerFlow's Internal Auth (a deployment
secret plus an owner id), always asks for the ``mwenza`` agent, and passes back a short event stream the page can
show: which tools the agent is using, retry notices, and the final reply with the constitution's review.

Token-by-token text is deliberately not forwarded. The constitution middleware may withdraw a draft reply and ask
for a revision, and a student must never see text that was withdrawn.

Settings (environment):
    MWENZA_DEERFLOW_URL     the gateway's public entry, e.g. http://127.0.0.1:2026 (unset: the chat stays local)
    MWENZA_DEERFLOW_TOKEN   DeerFlow's DEER_FLOW_INTERNAL_AUTH_TOKEN
    MWENZA_DEERFLOW_AGENT   the custom agent, default "mwenza"
    MWENZA_DEERFLOW_OWNER   the DeerFlow owner id for this workspace, default "mwenza-local"
    MWENZA_DEERFLOW_MODEL   optional: a DeerFlow model to use instead of the agent's own (operator setting, for
                            tests; the browser can never choose the model)
    MWENZA_DEERFLOW_PRIVATE_MODEL  a local DeerFlow model for private chats (unset: private chats are not offered)

Private chats: the student can mark a chat private (it holds interview transcripts, health records and the like),
and every model call in it then uses the private model, so its content never reaches a hosted model. The flag is
stored in the DeerFlow thread's metadata and only ever turned on: a later request cannot make a private chat
standard again, whatever the browser sends. Replies say which route answered (``route``): "hosted", "private"
(the local private model) or "local-fallback" (the hosted model was unavailable; see mwenza_deerflow/routing.py).

The owner id is fixed per engine because Mwenza has no student accounts yet; DeerFlow trusts whatever owner the
engine names, so per-student isolation must come from Mwenza's own sign-in before a multi-student deployment.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

TOOL_STEPS = {
    "search_literature": "Searching open literature",
    "lookup_doi": "Looking up a DOI",
    "get_citations": "Following citation links",
    "check_published_version": "Checking for a published version",
    "check_golden_thread": "Checking the golden thread",
    "check_paradigm_fit": "Checking paradigm-method fit",
    "navigate_methodology": "Walking the method navigator",
    "audit_citations": "Auditing citations against sources",
    "check_reported_statistics": "Recomputing reported statistics",
    "check_sample_size": "Recomputing the sample size",
    "run_analysis": "Running your analysis in the sandbox",
    "rerun_analysis": "Re-running the analysis to check it reproduces",
    "list_uploaded_files": "Looking at your uploads",
    "ask_clarification": "Asking you a question",
    "write_todos": "Planning the steps",
}


PRIVATE_KEY = "mwenza_private"
UNAVAILABLE = "Mwenza's model isn't answering right now. It may be busy, or it may have used today's allowance, which resets at 00:00 UTC. Try again later."


class AgentError(Exception):
    """A problem the student should see in plain words."""


@dataclass(frozen=True)
class DeerFlowSettings:
    url: str
    token: str
    agent: str = "mwenza"
    owner: str = "mwenza-local"
    timeout: float = 600.0
    model: str | None = None
    private_model: str | None = None

    @classmethod
    def from_env(cls) -> "DeerFlowSettings | None":
        url, token = os.environ.get("MWENZA_DEERFLOW_URL", "").strip().rstrip("/"), os.environ.get("MWENZA_DEERFLOW_TOKEN", "").strip()
        if not url or not token:
            return None
        return cls(url, token, os.environ.get("MWENZA_DEERFLOW_AGENT", "mwenza"), os.environ.get("MWENZA_DEERFLOW_OWNER", "mwenza-local"), float(os.environ.get("MWENZA_DEERFLOW_TIMEOUT", "600")), os.environ.get("MWENZA_DEERFLOW_MODEL") or None, os.environ.get("MWENZA_DEERFLOW_PRIVATE_MODEL") or None)


def step_label(name: str, args: dict[str, Any]) -> str:
    if name == "read_file":
        path = str(args.get("path", ""))
        return "Reading Mwenza's guidance" if "/skills/" in path else "Reading search results" if ".tool-results" in path else "Reading your files"
    return TOOL_STEPS.get(name, "Working")


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block if isinstance(block, str) else str(block.get("text", "")) for block in content if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text"))
    return ""


async def sse_frames(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, Any]]:
    """(event, data) pairs from a Server-Sent Events body."""
    event, data = "message", []
    async for line in lines:
        if line == "":
            if data:
                payload = "\n".join(data)
                try:
                    yield event, json.loads(payload)
                except ValueError:
                    yield event, payload
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


def final_reply(messages: list[dict[str, Any]], private: bool = False) -> dict[str, Any] | None:
    """The reply to the student's latest message: the last AI text, or a clarification question."""
    start = max((index for index, message in enumerate(messages) if message.get("type") == "human"), default=-1)
    for message in reversed(messages[start + 1:]):
        if message.get("type") == "tool" and message.get("name") == "ask_clarification":
            return {"text": text_of(message.get("content")), "kind": "question", "review": None}
        if message.get("type") == "ai" and text_of(message.get("content")).strip() and not message.get("tool_calls"):
            extra = message.get("additional_kwargs") or {}
            if extra.get("deerflow_error_fallback"):
                return {"text": UNAVAILABLE, "kind": "unavailable", "review": None}  # DeerFlow's own text speaks to operators
            route = "private" if private else (extra.get("mwenza_model") or {}).get("route", "hosted")
            return {"text": text_of(message.get("content")), "kind": "answer", "review": extra.get("mwenza_constitution"), "route": route}
    return None


class DeerFlowAgent:
    def __init__(self, settings: DeerFlowSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    @classmethod
    def from_env(cls) -> "DeerFlowAgent | None":
        settings = DeerFlowSettings.from_env()
        return cls(settings) if settings else None

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "agent": self.settings.agent, "gateway": self.settings.url, "private_available": bool(self.settings.private_model)}

    def _client(self) -> httpx.AsyncClient:
        # The CSRF check is a double-submit (cookie equals header) meant for browsers; a server-side caller
        # satisfies it with a fresh random value, as DeerFlow's own IM workers do.
        csrf = secrets.token_urlsafe(16)
        headers = {"X-DeerFlow-Internal-Token": self.settings.token, "X-DeerFlow-Owner-User-Id": self.settings.owner, "X-CSRF-Token": csrf, "Cookie": f"csrf_token={csrf}"}
        return httpx.AsyncClient(base_url=self.settings.url, headers=headers, timeout=httpx.Timeout(self.settings.timeout, connect=10.0), transport=self.transport)

    async def _privacy(self, client: httpx.AsyncClient, thread_id: str | None, private: bool) -> tuple[str, bool]:
        """Create the thread or read its stored privacy; private is sticky once set."""
        if private and not self.settings.private_model:
            raise AgentError("Private chats aren't available on this Mwenza: no local model is set up, so nothing was sent.")
        if not thread_id:
            created = await client.post("/api/threads", json={"metadata": {"agent_name": self.settings.agent, PRIVATE_KEY: private}})
            if created.status_code >= 400:
                raise AgentError(self._refusal(created.status_code))
            return created.json()["thread_id"], private
        found = await client.get(f"/api/threads/{thread_id}")
        if found.status_code >= 400:
            raise AgentError(self._refusal(found.status_code))
        stored = bool((found.json().get("metadata") or {}).get(PRIVATE_KEY))
        if stored and not self.settings.private_model:
            raise AgentError("This chat is private, but no local model is set up now, so nothing was sent. Start a new chat or ask your administrator.")
        if private and not stored:
            marked = await client.patch(f"/api/threads/{thread_id}", json={"metadata": {PRIVATE_KEY: True}})
            if marked.status_code >= 400:
                raise AgentError(self._refusal(marked.status_code))
        return thread_id, stored or private

    async def chat(self, message: str, thread_id: str | None = None, private: bool = False, files: list[dict[str, Any]] | None = None) -> AsyncIterator[dict[str, Any]]:
        """Run one student turn; yields thread, step, notice, reply and error events."""
        try:
            async with self._client() as client:
                thread_id, private = await self._privacy(client, thread_id, private)
                yield {"event": "thread", "thread_id": thread_id, "private": private}
                model = self.settings.private_model if private else self.settings.model
                body = {
                    "assistant_id": self.settings.agent,
                    "input": {"messages": [self._message(message, files)]},
                    "context": {"agent_name": self.settings.agent, **({"model_name": model} if model else {})},
                    # Out-of-band, never shown to the model: DeerFlow forwards these to Mwenza's MCP server as headers
                    # (headers_from_context), so sandbox runs use this chat's uploads and no one else's.
                    "config": {"context": {"secrets": {"mwenza_owner": self.settings.owner, "mwenza_thread": thread_id}}},
                    "stream_mode": ["values", "custom"],
                }
                seen_calls: set[str] = set()
                messages: list[dict[str, Any]] = []
                async with client.stream("POST", f"/api/threads/{thread_id}/runs/stream", json=body) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise AgentError(self._refusal(response.status_code))
                    async for event, data in sse_frames(response.aiter_lines()):
                        if event == "values" and isinstance(data, dict):
                            messages = data.get("messages") or messages
                            turn = max((index for index, item in enumerate(messages) if item.get("type") == "human"), default=0)
                            for item in messages[turn:]:  # this turn's tool calls only
                                for call in item.get("tool_calls") or []:
                                    if call.get("id") and call["id"] not in seen_calls:
                                        seen_calls.add(call["id"])
                                        yield {"event": "step", "tool": call.get("name"), "label": step_label(call.get("name", ""), call.get("args") or {})}
                        elif event == "custom" and isinstance(data, dict) and data.get("type") == "llm_retry":
                            yield {"event": "notice", "message": "The model is busy; trying again."}
                        elif event == "error":
                            raise AgentError("The research agent stopped with an error. Try again in a minute.")
                reply = final_reply(messages, private)
                if reply is None:
                    raise AgentError("The research agent finished without a reply. Try asking again.")
                yield {"event": "reply", **reply}
        except AgentError as exc:
            yield {"event": "error", "message": str(exc)}
        except httpx.HTTPError:
            yield {"event": "error", "message": f"Couldn't reach the research agent at {self.settings.url}. Is DeerFlow running?"}

    @staticmethod
    def _message(text: str, files: list[dict[str, Any]] | None) -> dict[str, Any]:
        """A user message; files just attached ride along the way DeerFlow's own frontend sends them, so DeerFlow's
        UploadsMiddleware tells the model their names and paths."""
        message: dict[str, Any] = {"role": "user", "content": text}
        if files:
            message["additional_kwargs"] = {"files": [{"filename": item["filename"], "size": int(item.get("size") or 0), "path": f"/mnt/user-data/uploads/{item['filename']}", "status": "uploaded"} for item in files]}
        return message

    async def upload(self, filename: str, content: bytes, thread_id: str | None = None, private: bool = False) -> dict[str, Any]:
        """Put a student's file in the chat's uploads (creating the chat if needed), for the agent and the sandbox."""
        async with self._client() as client:
            thread_id, private = await self._privacy(client, thread_id, private)
            response = await client.post(f"/api/threads/{thread_id}/uploads", files={"files": (filename, content)})
            if response.status_code >= 400:
                raise AgentError(self._refusal(response.status_code))
            stored = [{"filename": item.get("filename"), "size": item.get("size") or len(content)} for item in (response.json().get("files") or []) if item.get("filename")]
            stored = stored or [{"filename": filename, "size": len(content)}]
            return {"thread_id": thread_id, "private": private, "files": [item["filename"] for item in stored], "details": stored}

    @staticmethod
    def _refusal(status: int) -> str:
        if status in (401, 403):
            return "The research agent refused the engine's credentials. Check MWENZA_DEERFLOW_TOKEN against DeerFlow's DEER_FLOW_INTERNAL_AUTH_TOKEN."
        if status == 404:
            return "That conversation no longer exists on the research agent. Start a new chat."
        if status == 409:
            return "The research agent is still answering your last message."
        return f"The research agent rejected the request (HTTP {status})."
