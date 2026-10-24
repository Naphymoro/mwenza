"""Mwenza's research sandbox runner (phase H1b): run a student's analysis in a locked-down container and keep a
reproducibility capsule.

It runs on the host as the user that can use Docker, and listens on a Unix socket that only the mwenza-mcp container
mounts, so no container holds the Docker socket. Each run:

* takes its inputs only from the DeerFlow thread's uploads folder (named by the caller; the owner and thread come
  from DeerFlow's run context, never from the model), copying them into the capsule;
* runs Python or R in the pinned research image, by image ID, with no network, a read-only root filesystem, all
  Linux capabilities dropped, no privilege escalation, an unprivileged user, and CPU, memory, process and time
  limits;
* records a capsule: code, input copies, image ID, command, limits, outputs, stdout, stderr and SHA-256 hashes;
* copies the outputs and the capsule into the thread's outputs folder so the student can download them.

``POST /rerun`` repeats a capsule in a fresh container and compares output hashes: the reproducibility check.

Standard library only. Settings (environment): RUNNER_SOCKET, RUNNER_STORE, RUNNER_IMAGE, DEERFLOW_HOME,
RUNNER_CPUS, RUNNER_MEMORY, RUNNER_PIDS, RUNNER_TIMEOUT.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socketserver
import stat
import subprocess
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

HOME = Path.home()
SOCKET = Path(os.environ.get("RUNNER_SOCKET", HOME / ".local/share/mwenza-runner/socket/runner.sock"))  # its own folder: only this is mounted
STORE = Path(os.environ.get("RUNNER_STORE", HOME / ".local/share/mwenza-runner/capsules"))
IMAGE = os.environ.get("RUNNER_IMAGE", "mwenza-research:1")
DEERFLOW_HOME = Path(os.environ.get("DEERFLOW_HOME", "")).resolve() if os.environ.get("DEERFLOW_HOME") else None
LIMITS = {
    "cpus": os.environ.get("RUNNER_CPUS", "1"),
    "memory": os.environ.get("RUNNER_MEMORY", "1g"),
    "pids": int(os.environ.get("RUNNER_PIDS", "128")),
    "timeout_s": int(os.environ.get("RUNNER_TIMEOUT", "120")),
}
MAX_TIMEOUT = 600
MAX_CODE = 200_000
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_FILES = 50
MAX_STREAM = 20_000
PREVIEW = 2_000
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
FILE_NAME = re.compile(r"^[^/\\\x00]{1,255}$")
LANGUAGES = {"python": ("main.py", ["python", "/work/code/main.py"]), "r": ("main.R", ["Rscript", "/work/code/main.R"])}
TEXT_SUFFIXES = {".txt", ".csv", ".tsv", ".json", ".md", ".log", ".html", ".tex"}


class RunError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def clip(text: str, limit: int = MAX_STREAM) -> str:
    return text if len(text) <= limit else text[: limit // 2] + f"\n…[{len(text) - limit} characters cut]…\n" + text[-limit // 2 :]


def thread_dir(owner: str, thread: str, part: str) -> Path:
    if DEERFLOW_HOME is None:
        raise RunError("The runner has no DEERFLOW_HOME, so it cannot find the thread's files.", 500)
    if not ID.match(owner) or not ID.match(thread):
        raise RunError("Invalid owner or thread id.")
    path = (DEERFLOW_HOME / "users" / owner / "threads" / thread / "user-data" / part).resolve()
    if DEERFLOW_HOME not in path.parents:
        raise RunError("Invalid owner or thread id.")
    return path


def image_id(image: str) -> str:
    found = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True)
    if found.returncode != 0:
        raise RunError(f"The research image {image} is not available on this machine.", 503)
    return found.stdout.strip()


def collect_outputs(folder: Path) -> list[dict[str, Any]]:
    """Regular files only (symlinks are dropped), within the count and size limits."""
    outputs, total = [], 0
    for path in sorted(folder.rglob("*")):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            path.unlink()
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        total += info.st_size
        if len(outputs) >= MAX_OUTPUT_FILES or total > MAX_OUTPUT_BYTES:
            path.unlink()
            continue
        entry: dict[str, Any] = {"name": str(path.relative_to(folder)), "sha256": sha256_file(path), "bytes": info.st_size}
        if path.suffix.lower() in TEXT_SUFFIXES:
            entry["preview"] = path.read_text(encoding="utf-8", errors="replace")[:PREVIEW]
        outputs.append(entry)
    return outputs


def execute(capsule_dir: Path, outputs_dir: Path, language: str, image: str, timeout: int) -> dict[str, Any]:
    outputs_dir.mkdir(parents=True)
    outputs_dir.chmod(0o777)  # the container runs as an unprivileged user
    name = f"mwenza-run-{capsule_dir.name}-{outputs_dir.name}"
    command = [
        "docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,size=256m,mode=1777", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", str(LIMITS["pids"]), "--memory", LIMITS["memory"], "--memory-swap", LIMITS["memory"], "--cpus", LIMITS["cpus"],
        "--user", "65534:65534", "-w", "/work",
        # Inputs appear read-only at /work/inputs and at DeerFlow's own path, which the agent sees in its context.
        "-v", f"{capsule_dir / 'inputs'}:/work/inputs:ro", "-v", f"{capsule_dir / 'inputs'}:/mnt/user-data/uploads:ro", "-v", f"{capsule_dir / 'code'}:/work/code:ro", "-v", f"{outputs_dir}:/work/outputs:rw",
        image, *LANGUAGES[language][1],
    ]
    started = time.monotonic()
    try:
        finished = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        exit_code, stdout, stderr, timed_out = finished.returncode, finished.stdout, finished.stderr, False
    except subprocess.TimeoutExpired as expired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        exit_code, timed_out = None, True
        stdout = expired.stdout.decode(errors="replace") if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        stderr = (expired.stderr.decode(errors="replace") if isinstance(expired.stderr, bytes) else (expired.stderr or "")) + f"\n[stopped after {timeout} s]"
    shown = [part if not part.startswith(str(capsule_dir)) else part.replace(str(capsule_dir), "<capsule>") for part in command]
    return {
        "command": " ".join(shown), "exit_code": exit_code, "timed_out": timed_out, "duration_s": round(time.monotonic() - started, 2),
        "stdout": clip(stdout), "stderr": clip(stderr), "outputs": collect_outputs(outputs_dir),
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    language, code = request.get("language"), request.get("code")
    owner, thread = str(request.get("owner", "")), str(request.get("thread", ""))
    if language not in LANGUAGES:
        raise RunError("language must be python or r.")
    if not isinstance(code, str) or not code.strip() or len(code) > MAX_CODE:
        raise RunError("code is missing or too long.")
    timeout = min(int(request.get("timeout_s") or LIMITS["timeout_s"]), MAX_TIMEOUT)
    uploads = thread_dir(owner, thread, "uploads")
    names = request.get("inputs") or []
    if not isinstance(names, list) or not all(isinstance(name, str) and FILE_NAME.match(name) and name not in (".", "..") for name in names):
        raise RunError("inputs must be a list of file names from the student's uploads.")
    capsule_id = uuid.uuid4().hex[:12]
    capsule_dir = STORE / capsule_id
    (capsule_dir / "inputs").mkdir(parents=True)
    (capsule_dir / "code").mkdir()
    inputs, total = [], 0
    for name in names:
        source = uploads / name
        try:
            info = source.lstat()
        except FileNotFoundError:
            shutil.rmtree(capsule_dir)
            raise RunError(f"No uploaded file named {name!r} in this chat.", 404) from None
        if not stat.S_ISREG(info.st_mode):
            shutil.rmtree(capsule_dir)
            raise RunError(f"{name!r} is not a regular file.")
        total += info.st_size
        if total > MAX_INPUT_BYTES:
            shutil.rmtree(capsule_dir)
            raise RunError("The inputs are larger than the sandbox allows (50 MB).")
        copy = capsule_dir / "inputs" / name
        shutil.copyfile(source, copy)
        inputs.append({"name": name, "sha256": sha256_file(copy), "bytes": info.st_size})
    code_file = capsule_dir / "code" / LANGUAGES[language][0]
    code_file.write_text(code, encoding="utf-8")
    for folder in (capsule_dir / "inputs", capsule_dir / "code"):
        folder.chmod(0o755)
        for item in folder.iterdir():
            item.chmod(0o444)
    pinned = image_id(IMAGE)
    result = execute(capsule_dir, capsule_dir / "outputs", language, pinned, timeout)
    capsule = {
        "capsule_id": capsule_id, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "language": language,
        "image": IMAGE, "image_id": pinned, "network": "none", "limits": {**LIMITS, "timeout_s": timeout},
        "code_sha256": sha256_file(code_file), "inputs": inputs, "owner": owner, "thread": thread, **result,
    }
    (capsule_dir / "capsule.json").write_text(json.dumps(capsule, indent=1), encoding="utf-8")
    capsule["delivered_to"] = deliver(capsule_dir, capsule, owner, thread)
    (capsule_dir / "capsule.json").write_text(json.dumps(capsule, indent=1), encoding="utf-8")  # now with where it went
    return capsule


def deliver(capsule_dir: Path, capsule: dict[str, Any], owner: str, thread: str) -> str | None:
    """Copy outputs and the capsule into the thread's outputs folder; best effort."""
    try:
        target = thread_dir(owner, thread, "outputs") / f"analysis-{capsule['capsule_id']}"
        shutil.copytree(capsule_dir / "outputs", target)
        shutil.copyfile(capsule_dir / "capsule.json", target / "capsule.json")
        return f"/mnt/user-data/outputs/analysis-{capsule['capsule_id']}"
    except OSError:
        return None


def rerun(request: dict[str, Any]) -> dict[str, Any]:
    capsule_id = str(request.get("capsule_id", ""))
    if not re.match(r"^[0-9a-f]{12}$", capsule_id) or not (STORE / capsule_id / "capsule.json").exists():
        raise RunError("No capsule with that id.", 404)
    capsule_dir = STORE / capsule_id
    original = json.loads((capsule_dir / "capsule.json").read_text(encoding="utf-8"))
    current = image_id(original["image_id"])  # the very image the capsule ran on
    rerun_id = f"rerun-{uuid.uuid4().hex[:6]}"
    result = execute(capsule_dir, capsule_dir / rerun_id, original["language"], current, original["limits"]["timeout_s"])
    before = {item["name"]: item["sha256"] for item in original["outputs"]}
    after = {item["name"]: item["sha256"] for item in result["outputs"]}
    differences = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    same_stdout = result["stdout"] == original["stdout"]
    return {
        "capsule_id": capsule_id, "rerun_id": rerun_id, "image_id": current, "agree": not differences and same_stdout and result["exit_code"] == original["exit_code"],
        "output_differences": differences, "stdout_identical": same_stdout, "exit_code": result["exit_code"], "duration_s": result["duration_s"],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        print(f"{datetime.now().isoformat(timespec='seconds')} {format % args}", flush=True)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def address_string(self) -> str:  # Unix sockets have no client address
        return "local"

    def do_POST(self) -> None:
        handlers = {"/run": run, "/rerun": rerun}
        if self.path not in handlers:
            self.close_connection = True
            return self._send(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(request, dict):
                raise RunError("The request body must be a JSON object.")
            self._send(200, handlers[self.path](request))
        except RunError as exc:
            self._send(exc.status, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "The request body is not valid JSON."})


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main() -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        SOCKET.chmod(0o600)
        print(f"mwenza runner on {SOCKET}, image {IMAGE}, capsules in {STORE}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
