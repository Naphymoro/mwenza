"""The DeerFlow chat client against a scripted gateway (httpx.MockTransport). All conversation content is synthetic."""

import json

import anyio
import httpx
from fastapi.testclient import TestClient

from mwenza_engine.deerflow_agent import UNAVAILABLE, DeerFlowAgent, DeerFlowSettings

SETTINGS = DeerFlowSettings(url="http://gateway.test", token="internal-secret", owner="mwenza-test")
QUESTION = "[SYNTHETIC STUDENT] Is my design coherent?"
REVIEW = {"status": "warnings", "findings": [], "revisions": 0}


def sse(*frames):
    return "".join(f"event: {event}\ndata: {json.dumps(data)}\n\n" for event, data in frames)


def human():
    return {"type": "human", "content": QUESTION, "id": "h1"}


def search_call():
    return {"type": "ai", "content": "", "tool_calls": [{"id": "c1", "name": "search_literature", "args": {"query": "distance"}}, {"id": "c2", "name": "read_file", "args": {"path": "/mnt/skills/public/mwenza/SKILL.md"}}]}


def answer(text="Which districts does your study cover?", **extra):
    return {"type": "ai", "content": [{"type": "text", "text": text}], "additional_kwargs": extra}


def gateway(stream_body, *, thread_status=200, run_status=200, seen=None, stored=None):
    """A scripted DeerFlow; ``stored`` is the existing thread's metadata (PATCH merges into it)."""
    stored = {} if stored is None else stored

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path == "/api/threads":
            stored.update(json.loads(request.content).get("metadata") or {})
            return httpx.Response(thread_status, json={"thread_id": "thread-0001"})
        if request.url.path == "/api/threads/thread-0001" and request.method == "GET":
            return httpx.Response(thread_status, json={"thread_id": "thread-0001", "metadata": dict(stored)})
        if request.url.path == "/api/threads/thread-0001" and request.method == "PATCH":
            stored.update(json.loads(request.content)["metadata"])
            return httpx.Response(200, json={"thread_id": "thread-0001", "metadata": dict(stored)})
        if request.url.path == "/api/threads/thread-0001/uploads":
            return httpx.Response(200, json={"success": True, "message": "ok", "files": [{"filename": "survey.csv", "size": 12, "path": "/x", "virtual_path": "/mnt/user-data/uploads/survey.csv", "artifact_url": "/a"}]})
        if request.url.path.endswith("/runs/stream"):
            return httpx.Response(run_status, text=stream_body, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def collect(agent, thread_id=None, private=False):
    async def main():
        return [event async for event in agent.chat(QUESTION, thread_id, private)]
    return anyio.run(main)


FULL_RUN = sse(
    ("metadata", {"run_id": "r1", "thread_id": "thread-0001"}),
    ("values", {"messages": [human()]}),
    ("values", {"messages": [human(), search_call()]}),
    ("custom", {"type": "llm_retry", "attempt": 1}),
    ("values", {"messages": [human(), search_call(), {"type": "tool", "name": "search_literature", "content": "{}"}]}),
    ("values", {"messages": [human(), search_call(), {"type": "tool", "name": "search_literature", "content": "{}"}, answer(mwenza_constitution=REVIEW)]}),
    ("end", None),
)


def test_a_turn_creates_a_thread_streams_steps_and_returns_the_checked_reply():
    seen = []
    events = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, seen=seen)))
    assert [event["event"] for event in events] == ["thread", "step", "step", "notice", "reply"]
    assert [event["label"] for event in events if event["event"] == "step"] == ["Searching open literature", "Reading Mwenza's guidance"]
    assert events[-1] == {"event": "reply", "text": "Which districts does your study cover?", "kind": "answer", "review": REVIEW, "route": "hosted"}
    assert events[0] == {"event": "thread", "thread_id": "thread-0001", "private": False}
    created, run = seen
    assert json.loads(created.content)["metadata"] == {"agent_name": "mwenza", "mwenza_private": False}
    assert created.headers["X-DeerFlow-Internal-Token"] == "internal-secret" and created.headers["X-DeerFlow-Owner-User-Id"] == "mwenza-test"
    assert run.headers["Cookie"] == f"csrf_token={run.headers['X-CSRF-Token']}"
    body = json.loads(run.content)
    assert body["assistant_id"] == "mwenza" and body["context"] == {"agent_name": "mwenza"} and body["input"]["messages"][0]["content"] == QUESTION
    assert "model_name" not in json.dumps(body), "the agent's own config picks the model, never the browser"
    assert body["config"]["context"]["secrets"] == {"mwenza_owner": "mwenza-test", "mwenza_thread": "thread-0001"}


def test_an_operator_model_override_is_sent_as_context():
    seen = []
    collect(DeerFlowAgent(DeerFlowSettings(url="http://gateway.test", token="t", model="mwenza-local-14b"), gateway(FULL_RUN, seen=seen)))
    assert json.loads(seen[-1].content)["context"] == {"agent_name": "mwenza", "model_name": "mwenza-local-14b"}


def test_an_existing_thread_is_continued_without_creating_one():
    seen = []
    events = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, seen=seen)), "thread-0001")
    assert [(request.method, request.url.path) for request in seen] == [("GET", "/api/threads/thread-0001"), ("POST", "/api/threads/thread-0001/runs/stream")]
    assert events[0] == {"event": "thread", "thread_id": "thread-0001", "private": False}


PRIVATE = DeerFlowSettings(url="http://gateway.test", token="t", private_model="mwenza-local-14b")


def test_a_private_chat_runs_every_turn_on_the_local_model_and_says_so():
    seen = []
    events = collect(DeerFlowAgent(PRIVATE, gateway(FULL_RUN, seen=seen)), private=True)
    assert json.loads(seen[0].content)["metadata"]["mwenza_private"] is True
    assert json.loads(seen[-1].content)["context"] == {"agent_name": "mwenza", "model_name": "mwenza-local-14b"}
    assert events[0]["private"] is True and events[-1]["route"] == "private"


def test_private_is_sticky_whatever_the_browser_sends_later():
    seen, stored = [], {"mwenza_private": True}
    events = collect(DeerFlowAgent(PRIVATE, gateway(FULL_RUN, seen=seen, stored=stored)), "thread-0001", private=False)
    assert json.loads(seen[-1].content)["context"]["model_name"] == "mwenza-local-14b" and events[-1]["route"] == "private"


def test_a_standard_chat_can_become_private_and_stays_private():
    seen, stored = [], {"agent_name": "mwenza"}
    collect(DeerFlowAgent(PRIVATE, gateway(FULL_RUN, seen=seen, stored=stored)), "thread-0001", private=True)
    assert ("PATCH", "/api/threads/thread-0001") in [(request.method, request.url.path) for request in seen]
    assert stored == {"agent_name": "mwenza", "mwenza_private": True}


def test_private_without_a_local_model_sends_nothing():
    seen = []
    asked = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, seen=seen)), private=True)
    stored_private = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, seen=seen, stored={"mwenza_private": True})), "thread-0001")
    assert asked == [{"event": "error", "message": asked[0]["message"]}] and "nothing was sent" in asked[0]["message"]
    assert stored_private[-1]["event"] == "error" and "nothing was sent" in stored_private[-1]["message"]
    assert not any(request.url.path.endswith("/runs/stream") for request in seen)


def test_a_fallback_reply_reports_its_route():
    run = sse(("values", {"messages": [human(), answer(mwenza_model={"route": "local-fallback", "model": "mwenza-local-14b", "reason": "RateLimitError"})]}), ("end", None))
    assert collect(DeerFlowAgent(SETTINGS, gateway(run)))[-1]["route"] == "local-fallback"


def test_a_clarification_question_is_the_reply():
    run = sse(("values", {"messages": [human(), {"type": "ai", "content": "", "tool_calls": [{"id": "q1", "name": "ask_clarification", "args": {}}]}, {"type": "tool", "name": "ask_clarification", "content": "Which paradigm do you hold?"}]}), ("end", None))
    reply = collect(DeerFlowAgent(SETTINGS, gateway(run)))[-1]
    assert reply == {"event": "reply", "text": "Which paradigm do you hold?", "kind": "question", "review": None}


def test_a_provider_outage_is_marked_unavailable():
    run = sse(("values", {"messages": [human(), answer("The configured LLM provider is temporarily unavailable.", deerflow_error_fallback=True)]}), ("end", None))
    assert collect(DeerFlowAgent(SETTINGS, gateway(run)))[-1] == {"event": "reply", "text": UNAVAILABLE, "kind": "unavailable", "review": None}


def test_refusals_and_outages_become_plain_errors():
    refused = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, thread_status=401)))
    gone = collect(DeerFlowAgent(SETTINGS, gateway(FULL_RUN, run_status=404)), "thread-0001")

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    unreachable = collect(DeerFlowAgent(SETTINGS, httpx.MockTransport(down)))
    empty = collect(DeerFlowAgent(SETTINGS, gateway(sse(("values", {"messages": [human()]}), ("end", None)))))
    assert refused == [{"event": "error", "message": refused[0]["message"]}] and "MWENZA_DEERFLOW_TOKEN" in refused[0]["message"]
    assert gone[-1]["event"] == "error" and "Start a new chat" in gone[-1]["message"]
    assert unreachable[-1]["event"] == "error" and "Is DeerFlow running" in unreachable[-1]["message"]
    assert empty[-1]["event"] == "error" and "without a reply" in empty[-1]["message"]


def test_settings_need_both_url_and_token(monkeypatch):
    for name in ("TOKEN", "AGENT", "OWNER", "TIMEOUT", "MODEL", "PRIVATE_MODEL"):  # a loaded .env must not leak in
        monkeypatch.delenv(f"MWENZA_DEERFLOW_{name}", raising=False)
    monkeypatch.setenv("MWENZA_DEERFLOW_URL", "http://127.0.0.1:2026/")
    assert DeerFlowSettings.from_env() is None
    monkeypatch.setenv("MWENZA_DEERFLOW_TOKEN", "t")
    assert DeerFlowSettings.from_env() == DeerFlowSettings(url="http://127.0.0.1:2026", token="t")


def test_api_reports_status_and_streams_events(monkeypatch):
    from mwenza_engine import api

    client = TestClient(api.app)
    monkeypatch.setattr(api, "research_agent", None)
    assert client.get("/agent/status").json() == {"enabled": False}
    assert client.post("/agent/chat", json={"message": QUESTION}).status_code == 503
    monkeypatch.setattr(api, "research_agent", DeerFlowAgent(SETTINGS, gateway(FULL_RUN)))
    assert client.get("/agent/status").json() == {"enabled": True, "agent": "mwenza", "gateway": "http://gateway.test", "private_available": False}
    response = client.post("/agent/chat", json={"message": QUESTION})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [line[7:] for line in response.text.splitlines() if line.startswith("event: ")] == ["thread", "step", "step", "notice", "reply"]
    assert client.post("/agent/chat", json={"message": QUESTION, "thread_id": "../etc"}).status_code == 422


def test_an_upload_lands_in_the_chats_thread():
    seen = []
    agent = DeerFlowAgent(PRIVATE, gateway(FULL_RUN, seen=seen))
    result = anyio.run(lambda: agent.upload("survey.csv", b"age\n31\n", None, True))
    assert result == {"thread_id": "thread-0001", "private": True, "files": ["survey.csv"], "details": [{"filename": "survey.csv", "size": 12}]}
    created, uploaded = seen
    assert json.loads(created.content)["metadata"]["mwenza_private"] is True
    assert uploaded.url.path == "/api/threads/thread-0001/uploads" and b"survey.csv" in uploaded.content


def test_api_upload_route(monkeypatch):
    from mwenza_engine import api

    monkeypatch.setattr(api, "research_agent", DeerFlowAgent(SETTINGS, gateway(FULL_RUN)))
    response = TestClient(api.app).post("/agent/upload", files={"file": ("survey.csv", b"age\n31\n", "text/csv")})
    assert response.status_code == 200 and response.json()["files"] == ["survey.csv"]


def test_files_just_attached_ride_on_the_next_message_and_steps_cover_this_turn_only():
    earlier = {"type": "ai", "content": "", "tool_calls": [{"id": "old", "name": "check_golden_thread", "args": {}}]}
    run = sse(("values", {"messages": [human(), earlier, {"type": "tool", "name": "check_golden_thread", "content": "{}"}, answer("Earlier."), human(), search_call(), answer()]}), ("end", None))
    seen = []
    async def main():
        return [event async for event in DeerFlowAgent(SETTINGS, gateway(run, seen=seen)).chat(QUESTION, "thread-0001", False, [{"filename": "survey.csv", "size": 12}])]
    events = anyio.run(main)
    assert [event["tool"] for event in events if event["event"] == "step"] == ["search_literature", "read_file"]
    sent = json.loads(seen[-1].content)["input"]["messages"][0]
    assert sent["additional_kwargs"]["files"] == [{"filename": "survey.csv", "size": 12, "path": "/mnt/user-data/uploads/survey.csv", "status": "uploaded"}]
