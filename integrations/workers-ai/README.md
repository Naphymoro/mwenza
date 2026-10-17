# Mwenza's model on Workers AI

A small Cloudflare Worker that gives DeerFlow an OpenAI-style `/v1/chat/completions` endpoint, answered by Workers AI. It handles streaming and tool calls. It follows NDIM's Worker (`nidm-rwanda-dashboard/cloudflare/engine-container/src/ai.ts`) but is separate, with its own token and cap.

- **Endpoint:** `https://mwenza-ai.couma.workers.dev/v1/chat/completions`, with `Authorization: Bearer $MWENZA_AI_TOKEN`. Without the token, every path returns 404.
- **Model:** fixed by the Worker (`MWENZA_AI_MODEL`, currently `@cf/zai-org/glm-5.3-flash`). Callers can't choose another.
- **Limits:**
  - Replies are capped at 3,000 tokens.
  - The Worker stops for the day once `MWENZA_AI_DAILY_NEURONS` (3,000) are used, and resets at 00:00 UTC.
  - Usage is counted per UTC day in the D1 database `mwenza-ai-usage`.
- **Content blocks:** list-style message content, as LangChain sends it, is flattened to text.

Workers AI's free 10,000 Neurons a day are per account. NDIM caps itself at 9,000, so together the two can go about 2,000 over on a day when both are busy. On the paid Workers plan that overage costs a few cents.

**What a turn costs:** a DeerFlow model call with the Mwenza agent's prompt costs about 210 Neurons. A supervision turn with two checks made 5 calls, about 1,065 Neurons, so 3,000 a day covers roughly three turns.

## Deploy

```bash
npm install
npx wrangler d1 migrations apply mwenza-ai-usage --remote
npx wrangler deploy
npx wrangler secret put MWENZA_AI_TOKEN    # the same value as MWENZA_AI_TOKEN in DeerFlow's .env
```

## DeerFlow model entry (`config.yaml`)

```yaml
  - name: mwenza-glm
    display_name: GLM-5.3-Flash (Workers AI, Mwenza)
    use: deerflow.models.patched_deepseek:PatchedChatDeepSeek
    model: "@cf/zai-org/glm-5.3-flash"
    api_base: https://mwenza-ai.couma.workers.dev/v1
    api_key: $MWENZA_AI_TOKEN
    timeout: 300.0
    max_retries: 1
    temperature: 0.3
    max_tokens: 3000
    supports_thinking: false
    supports_vision: false
    stream_usage: false
```

The gateway reads `.env` only when its container is created, so after adding the token, recreate it:

```bash
DEER_FLOW_ROOT="$PWD" docker compose -p deer-flow-dev -f docker/docker-compose-dev.yaml up -d --no-deps --no-build gateway
```

`docker restart` isn't enough. Until the variable exists, `config.yaml` fails to load for every agent.
