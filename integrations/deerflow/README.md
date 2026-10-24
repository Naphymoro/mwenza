# Mwenza on DeerFlow

Phase H0 of `docs/analysis/AGENTIC_HARNESS_DESIGN.md`: Mwenza runs as an agent inside [DeerFlow 2.0](https://github.com/bytedance/deer-flow), joined only through DeerFlow's supported seams (MCP, a `SKILL.md` skill, a custom agent, and a config-declared middleware). All Mwenza logic stays in this repo.

| Piece | Where it lives here | Where it goes in DeerFlow |
| --- | --- | --- |
| MCP server (8 tools) | `backend/src/mwenza_engine/mcp_server.py`, run by `docker-compose.deerflow.yml` | `mcpServers.mwenza` in `extensions_config.json`, at `http://mwenza-mcp:8766/mcp` |
| Skill | `skills/mwenza/` | `skills/public/mwenza/` |
| Lead agent | `agent/SOUL.md` (config written by `install.sh`) | `backend/.deer-flow/agents/mwenza/` |
| Constitution middleware | `mwenza_deerflow/middleware.py` + `backend/src/mwenza_engine/constitution.py` | `backend/mwenza_deerflow/`, listed under `middlewares` in `extensions_config.json` |
| Model fallback middleware | `mwenza_deerflow/routing.py` | the same folder, listed after the constitution (only with `MWENZA_FALLBACK_MODEL`) |

## Install

With DeerFlow's Docker dev stack running (it creates the `deer-flow-dev_deer-flow-dev` network):

```bash
# from the mwenza repo
docker compose -f integrations/deerflow/docker-compose.deerflow.yml up -d --build
integrations/deerflow/install.sh /path/to/deer-flow
docker restart deer-flow-gateway      # only needed after the middleware changes
```

Add `MWENZA_FALLBACK_MODEL=mwenza-local-14b` to the install command once the local models are set up. `install.sh` is idempotent: run it again after changing the skill, the agent, the middleware or `constitution.py`. Everything stays container to container. The host firewall drops container-to-host traffic, and the MCP port is never published on the host because the server has no authentication. It keeps DNS-rebinding protection on with `--allowed-host mwenza-mcp`.

## What the agent can do

The `mwenza` agent sees only:
- the Mwenza MCP tools;
- read-only file tools, to read the skill and the student's uploads;
- DeerFlow's framework built-ins, such as `ask_clarification`.

It has no web search, shell, file writing or sub-agents, and memory is off until per-student memory exists (H2). When the skill is active, its `allowed-tools` narrows this further.

## The constitution middleware

On every final reply from the `mwenza` agent, or from any agent that has used a Mwenza tool in the thread, `MwenzaConstitutionMiddleware` checks the reply against the evidence in the conversation. Evidence means Mwenza tool results and the student's own messages. Web pages and sub-agent summaries don't count.

| Finding | Effect |
| --- | --- |
| DOI, link or author-year citation not in the evidence | blocks |
| Retracted work cited | blocks |
| Long declarative paragraph not addressed to the student (paste-ready thesis text) | blocks |
| After a sandbox run: a decimal number that isn't in the run's output, another Mwenza tool result or the student's text | blocks |
| Preprint cited without saying so | warns |

A reply the model cut off at its output limit (`finish_reason: length`) gets a line telling the student to say "continue". DeerFlow keeps the partial text but doesn't say it's partial.

Tool calls are checked too. The `mwenza` agent can't write files or run commands. `run_analysis` needs the student's approval in their own words. `check_reported_statistics` (as the student's words) and `check_sample_size` refuse any figure that isn't in the student's messages or uploaded files, apart from conventional alpha, power and confidence levels.

Evidence is recorded when a Mwenza tool returns, as `additional_kwargs["mwenza_evidence"]` on the tool message. DeerFlow moves results over 12,000 characters to a file and leaves only a preview, so the record is taken first. It's saved with the thread and never sent to the model.

A blocked reply is withdrawn from the thread and the agent is asked to revise it, once per run. The instruction travels inside the model request and is never saved as a message. If the revision still breaks a rule, the reply goes out with visible labels: unverified, retracted, or annotated example. Nothing is silently deleted. The review is attached as `additional_kwargs["mwenza_constitution"]`.

## Tests

- `backend/tests/test_constitution.py`: the checks, on synthetic data. Runs with the engine's test suite.
- `tests/test_middleware.py`: the middleware in a real LangChain agent loop with a scripted model (no LLM). It needs DeerFlow's dependencies, so run it in the gateway:

  ```bash
  mkdir -p /tmp/mw && cp -r integrations/deerflow/{mwenza_deerflow,tests} /tmp/mw/ && cp backend/src/mwenza_engine/constitution.py /tmp/mw/mwenza_deerflow/
  docker cp /tmp/mw deer-flow-gateway:/tmp/mwtest
  docker exec deer-flow-gateway sh -c 'cd /tmp/mwtest && PYTHONPATH=. /app/backend/.venv/bin/python -m pytest -q -p no:cacheprovider tests'
  ```

- `smoke_scripted.py`: an end-to-end smoke test inside the gateway. It uses the real MCP tools over the network and the middleware as DeerFlow loads it from config, with a scripted model that first cites a fabricated paper.

- `h0_llm.py`: the H0 completion test with the real model (`mwenza-glm` on Workers AI, see `../workers-ai`). A synthetic student asks for proposal feedback, asks the agent to ghost-write, then asks for literature.

## Models and routing

- **Main model:** `mwenza-glm`, which is GLM-5.3-Flash on Workers AI through the `mwenza-ai` Worker (`../workers-ai`). Pin it with `MWENZA_AGENT_MODEL=mwenza-glm install.sh ...`.
- **Fallback:** with `MWENZA_FALLBACK_MODEL=mwenza-local-14b install.sh ...`, `MwenzaModelFallbackMiddleware` continues a turn on that local model (`../local-models`) when the main model fails because it's unreachable, over its cap (a 429) or erroring.
  - After one such failure, the rest of the run goes straight to the fallback.
  - The reply carries `additional_kwargs["mwenza_model"]`, and Mwenza's page tells the student.
  - It only falls back from hosted to local, never the other way.
  - If the fallback model can't be built, the provider's original error is raised.
- **Private chats:** chosen by the engine, not here. With `MWENZA_DEERFLOW_PRIVATE_MODEL` set, a chat the student marks private runs every call on that local model; the flag is stored in the thread's metadata and can only be switched on. DeerFlow's other model calls also stay local:
  - title generation is off (`title.model_name: null`);
  - summarisation uses the run's own model;
  - the agent's memory is off.

## Mwenza's chat page

The engine's `/agent/chat` (`backend/src/mwenza_engine/deerflow_agent.py`) calls the gateway with DeerFlow's Internal Auth. DeerFlow must have an explicit `DEER_FLOW_INTERNAL_AUTH_TOKEN`; without one, each gateway worker makes up a random token. Put it in DeerFlow's `.env`, and the same value in Mwenza's `.env` as `MWENZA_DEERFLOW_TOKEN`.

DeerFlow's dev Compose file fills that variable from the shell that runs Compose, not from `.env`, and `make docker-start` doesn't export it. Export it when you (re)create the gateway, or it comes up empty:

```bash
cd deer-flow
export DEER_FLOW_INTERNAL_AUTH_TOKEN="$(grep -E '^DEER_FLOW_INTERNAL_AUTH_TOKEN=' .env | tail -1 | cut -d= -f2-)"
DEER_FLOW_ROOT="$PWD" docker compose -p deer-flow-dev -f docker/docker-compose-dev.yaml up -d --no-deps --no-build --force-recreate gateway
```

## Not yet done

- H2 onwards (committee room, per-student memory, the Forge): see `docs/analysis/AGENTIC_HARNESS_DESIGN.md`.
