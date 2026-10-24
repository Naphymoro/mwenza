# Local models for Mwenza on DeerFlow

These let DeerFlow's agents use the Ollama on this machine's GPU, for private chats and as a fallback when the hosted model is unavailable. DeerFlow runs in Docker, and the host firewall drops container-to-host traffic, so the connection goes through a Unix socket:

```
DeerFlow gateway ──HTTP──► ollama-relay container ──Unix socket──► socat (host, user service) ──► Ollama 127.0.0.1:11434
```

| Piece | What it does |
| --- | --- |
| `mwenza-ollama-bridge.service` | A systemd user service. `socat` serves Ollama on `~/.local/share/mwenza-ollama/ollama.sock` (mode 600) |
| `relay.py` (container `ollama-relay`) | Standard library only. Serves only `POST /v1/chat/completions` for the named models and `GET /v1/models`, and needs a bearer token. Ollama's model-management API (pull, copy, delete) is never exposed to DeerFlow or its sandboxes |
| `docker-compose.deerflow.yml` | Runs the relay on DeerFlow's network as the host user, so it can open the socket. Nothing is published on the host |

## Set up

```bash
# 1. Models with a context window large enough for the agent's prompt (about 9,600 tokens on the first call; it grows with tool results)
curl -s http://127.0.0.1:11434/api/create -d '{"model":"mwenza-qwen3-14b","from":"qwen3:14b","parameters":{"num_ctx":32768},"stream":false}'
curl -s http://127.0.0.1:11434/api/create -d '{"model":"mwenza-qwen3-8b","from":"qwen3:8b","parameters":{"num_ctx":32768},"stream":false}'

# 2. The host bridge
install -D -m 644 mwenza-ollama-bridge.service ~/.config/systemd/user/mwenza-ollama-bridge.service
systemctl --user daemon-reload && systemctl --user enable --now mwenza-ollama-bridge

# 3. The relay: RELAY_TOKEN, UID and GID go in .env next to the compose file (gitignored)
docker compose -f docker-compose.deerflow.yml up -d --build
```

Put the same token in DeerFlow's `.env` as `MWENZA_LOCAL_TOKEN`, then recreate the gateway so it loads it. See `../deerflow/README.md` for the exact command, which must export `DEER_FLOW_INTERNAL_AUTH_TOKEN`. Only then add the models to DeerFlow's `config.yaml`:

```yaml
  - name: mwenza-local-14b
    display_name: Qwen3 14B (local, Mwenza)
    use: langchain_openai:ChatOpenAI
    model: mwenza-qwen3-14b
    base_url: http://ollama-relay:11434/v1
    api_key: $MWENZA_LOCAL_TOKEN
    timeout: 600.0
    max_retries: 1
    temperature: 0.3
    max_tokens: 3000
    extra_body:
      reasoning_effort: none        # Qwen3 thinking off, so replies carry no <think> text
    context_window: 32768
    supports_thinking: false
    supports_vision: false
```

The order matters. A `$VARIABLE` in `config.yaml` that the gateway doesn't have stops the config loading for every agent.

## Measured on this machine (RTX 2000 Ada, 16 GB)

| Model | First call (load) | Warm call, 17k-token prompt | GPU memory |
| --- | --- | --- | --- |
| `mwenza-qwen3-8b` | 16 s | 1.2 s | |
| `mwenza-qwen3-14b` | 32 s | 1.8 s | 14.4 GB (fully on GPU) |

Both call tools correctly. In the H0 test the 14B model ghost-wrote and invented a DOI when it led a supervision chat. The constitution caught both, but its teaching is weaker than the hosted model's. See §8 of `docs/analysis/AGENTIC_HARNESS_DESIGN.md`.

Gotcha: Ollama refuses requests whose `Host` header isn't localhost, so the relay addresses it as `127.0.0.1:11434` even over the socket.
