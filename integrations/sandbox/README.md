# Mwenza research sandbox

Phase H1b of `docs/analysis/AGENTIC_HARNESS_DESIGN.md`. A student's own analysis (Python or R on data they attached to the chat) runs in a locked-down container. The result comes back as computed evidence with a reproducibility capsule.

```
page (Attach data) ─► engine /agent/upload ─► DeerFlow thread uploads
agent ─ run_analysis(code, inputs, approval) ─► mwenza-mcp ─Unix socket─► runner.py (host, systemd user service)
                                                                             └─► docker run mwenza-research (locked down)
```

## Safeguards

| Where | What |
| --- | --- |
| Constitution middleware | `run_analysis` goes ahead only if its `approval` is in the student's latest message, so running code is a human checkpoint the model can't fake |
| DeerFlow → MCP | The chat's owner and thread travel as run secrets, forwarded as headers by `headers_from_context`, never through the model. The runner reads only that chat's uploads |
| Runner | Inputs must be named regular files in the uploads folder: no paths, no symlinks, 50 MB in total. Copies go into the capsule |
| Container | `--network none`, `--read-only` with a 256 MB `/tmp`, `--cap-drop ALL`, `no-new-privileges`, user 65534, 1 CPU, 1 GB of memory with no swap, 128 processes, a 120 s time limit (600 s at most). Code and inputs are read-only; only `/work/outputs` is writable |
| Host | No container holds the Docker socket. Only the mwenza-mcp container mounts the runner's socket folder (mode 600), and it runs as the host user |

Inputs appear at `/work/inputs/<name>` and at DeerFlow's own path, `/mnt/user-data/uploads/<name>`, because that's the path the agent sees in its context.

## Capsules

Each run writes `~/.local/share/mwenza-runner/capsules/<id>/` with the code, input copies, outputs and `capsule.json`. The JSON holds:
- the language;
- the image name and image ID (the digest the run used);
- the network setting and the limits;
- the code's SHA-256, plus each input's and output's name, size and SHA-256;
- the command, exit code, duration, stdout and stderr;
- where the outputs were delivered.

The outputs and the capsule are also copied to the chat's `outputs/analysis-<id>/` folder, so the student can download them. `rerun_analysis` repeats a capsule in a fresh container, on the same image ID, and reports whether the outputs and stdout are identical.

## Install

```bash
docker build -f integrations/sandbox/Dockerfile.research -t mwenza-research:1 integrations/sandbox   # also done by the installer
integrations/sandbox/install-runner.sh /path/to/deer-flow                                         # systemd user service
docker compose -f integrations/deerflow/docker-compose.deerflow.yml up -d --build                  # mwenza-mcp, with the socket mounted
integrations/deerflow/install.sh /path/to/deer-flow                                                # adds the header mapping
```

`integrations/deerflow/.env` needs `UID` and `GID` (the host user's), so the MCP container can open the socket.

## Tests

- `tests/test_runner.py` uses real Docker and the image (skipped without them). It covers:
  - a Python and an R analysis;
  - a complete capsule and its delivery;
  - a rerun that agrees for a deterministic analysis and disagrees for an unseeded random one;
  - no network;
  - no writes outside the outputs folder;
  - a runaway loop stopped at the time limit;
  - path traversal, unknown files and a planted symlink refused.
- `backend/tests/test_sandbox.py` covers the MCP tools with a fake runner.
- `integrations/deerflow/tests/test_middleware.py` covers the approval checkpoint.
- `e2e_sandbox.py` runs the production path end to end.

## Not yet

- A network allowlist (CRAN or PyPI on request). The image carries the common packages, so the network stays off.
- Recording capsules in the engine's provenance ledger as computed evidence spans.
- A constitution check that every number in a reply that cites a capsule appears in that capsule's output.
