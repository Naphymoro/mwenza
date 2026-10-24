"""Client for the research sandbox runner (integrations/sandbox/runner.py), over its Unix socket.

The runner executes a student's Python or R analysis in a locked-down container and returns a reproducibility
capsule. The owner and thread come from DeerFlow's run context (forwarded as headers by DeerFlow's
``headers_from_context``), never from the model, so an agent can only use files uploaded to its own chat.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from typing import Any, Mapping

OWNER_HEADER = "x-mwenza-owner"
THREAD_HEADER = "x-mwenza-thread"
STREAM_FOR_AGENT = 6_000


class SandboxError(Exception):
    pass


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("runner", timeout=timeout)
        self.socket_path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


class RunnerClient:
    def __init__(self, socket_path: str | None = None, timeout: float = 700.0) -> None:
        self.socket_path = socket_path or os.environ.get("MWENZA_RUNNER_SOCKET", "")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.socket_path) and os.path.exists(self.socket_path)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise SandboxError("The research sandbox is not set up on this Mwenza, so no code was run.")
        connection = _UnixConnection(self.socket_path, self.timeout)
        try:
            connection.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = json.loads(response.read() or b"{}")
        except (OSError, ValueError) as exc:
            raise SandboxError("The research sandbox did not answer. Try again in a minute.") from exc
        finally:
            connection.close()
        if response.status >= 400:
            raise SandboxError(payload.get("error") or f"The sandbox refused the run (HTTP {response.status}).")
        return payload

    def run(self, owner: str, thread: str, language: str, code: str, inputs: list[str]) -> dict[str, Any]:
        return self._post("/run", {"owner": owner, "thread": thread, "language": language, "code": code, "inputs": inputs})

    def rerun(self, capsule_id: str) -> dict[str, Any]:
        return self._post("/rerun", {"capsule_id": capsule_id})


def identity(headers: Mapping[str, str] | None) -> tuple[str, str]:
    """The DeerFlow owner and thread of the current run, from the headers DeerFlow forwards."""
    lowered = {key.lower(): value for key, value in (headers or {}).items()}
    owner, thread = lowered.get(OWNER_HEADER, "").strip(), lowered.get(THREAD_HEADER, "").strip()
    if not owner or not thread:
        raise SandboxError("Analyses can only run from a Mwenza chat, which tells the sandbox whose files to use. Nothing was run.")
    return owner, thread


def for_agent(capsule: dict[str, Any]) -> dict[str, Any]:
    """The capsule as the agent sees it: results, hashes and where the files are, with long streams clipped."""
    clip = lambda text: text if len(text) <= STREAM_FOR_AGENT else text[:STREAM_FOR_AGENT] + f"\n…[{len(text) - STREAM_FOR_AGENT} more characters in the capsule]"
    keys = ("capsule_id", "created_at", "language", "image_id", "network", "limits", "code_sha256", "inputs", "exit_code", "timed_out", "duration_s", "outputs", "delivered_to")
    result = {key: capsule.get(key) for key in keys}
    result["stdout"], result["stderr"] = clip(capsule.get("stdout", "")), clip(capsule.get("stderr", ""))
    result["evidence"] = {
        "kind": "computed", "capsule_id": capsule.get("capsule_id"),
        "note": "Cite this run by its capsule id. Report only what stdout and the output files show; do not round, extend or interpret beyond them without saying so.",
    }
    return result
