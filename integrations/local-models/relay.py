"""A narrow HTTP relay from DeerFlow's Docker network to the host's Ollama, over a Unix socket.

The host firewall drops container-to-host traffic, so the host exposes Ollama as a Unix socket
(mwenza-ollama-bridge.service runs socat) and this relay, in a container on DeerFlow's network, serves it again.
Ollama's own API can also pull, copy and delete models, so the relay passes on only what an agent needs:
POST /v1/chat/completions for the allowed models, and GET /v1/models. Callers need the relay token.

Standard library only. Settings (environment):
    RELAY_SOCKET   the Unix socket, default /run/ollama/ollama.sock
    RELAY_MODELS   comma-separated model names callers may use
    RELAY_TOKEN    bearer token callers must send
    RELAY_PORT     default 11434
"""

from __future__ import annotations

import hmac
import http.client
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOCKET = os.environ.get("RELAY_SOCKET", "/run/ollama/ollama.sock")
MODELS = {name.strip() for name in os.environ.get("RELAY_MODELS", "").split(",") if name.strip()}
TOKEN = os.environ.get("RELAY_TOKEN", "")
MAX_BODY = 8 * 1024 * 1024
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "upgrade"}


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 900) -> None:
        super().__init__("127.0.0.1", 11434, timeout=timeout)  # Ollama only serves requests addressed to localhost
        self.path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Relay(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "mwenza-ollama-relay"

    def log_message(self, format: str, *args) -> None:  # one line per request, never bodies
        print(f"{self.address_string()} {format % args}", flush=True)

    def _refuse(self, status: int, message: str) -> None:
        self.close_connection = True  # an unread request body must not be parsed as the next request
        body = json.dumps({"error": {"message": message}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        sent = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return bool(TOKEN) and hmac.compare_digest(sent, TOKEN)

    def do_GET(self) -> None:
        if not self._authorised():
            return self._refuse(401, "Missing or wrong relay token.")
        if self.path != "/v1/models":
            return self._refuse(404, "Not found.")
        body = json.dumps({"object": "list", "data": [{"id": name, "object": "model", "owned_by": "local"} for name in sorted(MODELS)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._authorised():
            return self._refuse(401, "Missing or wrong relay token.")
        if self.path != "/v1/chat/completions":
            return self._refuse(404, "Not found.")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._refuse(413 if length > MAX_BODY else 400, "Request body missing or too large.")
        raw = self.rfile.read(length)
        try:
            model = json.loads(raw).get("model")
        except (ValueError, AttributeError):
            return self._refuse(400, "The request body is not a JSON object.")
        if model not in MODELS:
            return self._refuse(403, f"Model {model!r} is not offered by this relay.")
        upstream = UnixConnection(SOCKET)
        try:
            upstream.request("POST", "/v1/chat/completions", body=raw, headers={"Content-Type": "application/json"})
            response = upstream.getresponse()
        except OSError:
            upstream.close()
            return self._refuse(502, "The local model server is not reachable.")
        self.send_response(response.status)
        for name, value in response.getheaders():
            if name.lower() not in HOP_BY_HOP:
                self.send_header(name, value)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while chunk := response.read1(65536):
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        finally:
            upstream.close()


def main() -> None:
    if not TOKEN or not MODELS:
        raise SystemExit("Set RELAY_TOKEN and RELAY_MODELS.")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("RELAY_PORT", "11434"))), Relay).serve_forever()


if __name__ == "__main__":
    main()
