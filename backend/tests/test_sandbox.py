"""The sandbox tools and runner client, with a fake runner (the real runner is tested in integrations/sandbox)."""

import json

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from mwenza_engine.mcp_server import build_server
from mwenza_engine.sandbox import RunnerClient, SandboxError, for_agent, identity
from test_open_discovery import FakeOpenApis, discovery

CAPSULE = {
    "capsule_id": "0123456789ab", "created_at": "2026-10-18T00:00:00+00:00", "language": "python", "image_id": "sha256:abc", "network": "none",
    "limits": {"cpus": "1", "memory": "1g", "pids": 128, "timeout_s": 120}, "code_sha256": "c0de", "inputs": [{"name": "survey.csv", "sha256": "1np", "bytes": 10}],
    "exit_code": 0, "timed_out": False, "duration_s": 1.2, "outputs": [], "delivered_to": "/mnt/user-data/outputs/analysis-0123456789ab",
    "stdout": "mean age 31.2\n" + "x" * 10_000, "stderr": "", "owner": "mwenza-test", "thread": "t-1",
}


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, *args):
        self.calls.append(("run", args))
        return dict(CAPSULE)

    def rerun(self, capsule_id):
        self.calls.append(("rerun", capsule_id))
        return {"capsule_id": capsule_id, "agree": True, "output_differences": []}


def call(tool, arguments, runner=None, who=("mwenza-test", "t-1")):
    server = build_server(discovery(FakeOpenApis()), runner=runner or FakeRunner(), identity=(lambda headers: who) if who else identity)

    async def main():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return anyio.run(main)


def payload(result):
    assert not result.is_error, result.content
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


ARGS = {"language": "python", "code": "import pandas as pd\nprint(pd.read_csv('/work/inputs/survey.csv').age.mean())", "approval": "Yes, run it", "inputs": ["survey.csv"]}


def test_run_analysis_uses_the_runs_own_thread_and_returns_computed_evidence():
    runner = FakeRunner()
    body = payload(call("run_analysis", ARGS, runner))
    assert runner.calls == [("run", ("mwenza-test", "t-1", "python", ARGS["code"], ["survey.csv"]))]
    assert body["evidence"]["kind"] == "computed" and body["evidence"]["capsule_id"] == "0123456789ab"
    assert body["stdout"].startswith("mean age 31.2") and "more characters in the capsule" in body["stdout"]
    assert "owner" not in body and "thread" not in body


def test_without_a_chat_identity_nothing_runs():
    runner = FakeRunner()
    result = call("run_analysis", ARGS, runner, who=None)  # the in-memory client carries no headers
    assert result.is_error and "only run from a Mwenza chat" in result.content[0].text and runner.calls == []


def test_a_missing_sandbox_says_so():
    result = call("run_analysis", ARGS, RunnerClient("/nonexistent/runner.sock"))
    assert result.is_error and "not set up" in result.content[0].text


def test_rerun_and_bad_capsule_ids():
    assert payload(call("rerun_analysis", {"capsule_id": "0123456789ab"}))["agree"] is True
    assert call("rerun_analysis", {"capsule_id": "../../etc"}).is_error


def test_identity_reads_forwarded_headers_case_insensitively():
    assert identity({"X-Mwenza-Owner": "mwenza-local", "X-Mwenza-Thread": "abc-123"}) == ("mwenza-local", "abc-123")
    with pytest.raises(SandboxError):
        identity({"X-Mwenza-Owner": "mwenza-local"})
    with pytest.raises(SandboxError):
        identity(None)


def test_for_agent_drops_identity_and_keeps_hashes():
    shown = for_agent(CAPSULE)
    assert shown["inputs"][0]["sha256"] == "1np" and shown["image_id"] == "sha256:abc" and "owner" not in shown
