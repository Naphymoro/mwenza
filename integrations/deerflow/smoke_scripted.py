"""Model-free smoke test: real Mwenza MCP tools + DeerFlow-configured constitution middleware + a scripted model.

Run inside the DeerFlow gateway after install.sh, with the mwenza-mcp container up:

    docker cp integrations/deerflow/smoke_scripted.py deer-flow-gateway:/tmp/
    docker exec deer-flow-gateway sh -c "cd /app/backend && PYTHONPATH=. .venv/bin/python /tmp/smoke_scripted.py"

The "model" is a script, not an LLM: it searches, drafts a reply with an invented citation, and after the hidden
correction cites the first real result. Synthetic student question.
"""
import asyncio, json
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from deerflow.config import get_app_config
from deerflow.agents.middlewares.configured_extensions import load_configured_extension_middlewares
from deerflow.mcp.tools import get_mcp_tools

class Script(BaseChatModel):
    calls: list = []
    @property
    def _llm_type(self): return "scripted"
    def bind_tools(self, tools, **kw): return self
    def _generate(self, messages, stop=None, run_manager=None, **kw):
        self.calls.append(messages)
        tool_results = [m for m in messages if isinstance(m, ToolMessage)]
        corrected = messages[-1].__class__ is HumanMessage and getattr(messages[-1], "name", "") == "mwenza_constitution"
        if not tool_results:
            msg = AIMessage(content="", tool_calls=[{"name": "search_literature", "args": {"query": "distance to health facility delivery Kenya", "limit": 3}, "id": "c1", "type": "tool_call"}])
        elif not corrected:
            msg = AIMessage(content="Kamau and Njoroge (2018) proved distance is the only barrier (https://doi.org/10.9999/fabricated.2018).")
        else:
            body = json.loads(tool_results[-1].content[0]["text"] if isinstance(tool_results[-1].content, list) else tool_results[-1].content)
            w = body["results"][0]
            surname = w["authors"][0].split()[-1]
            msg = AIMessage(content=f"A good starting point is {surname} et al. ({w['year']}), '{w['title']}' (https://doi.org/{w['doi']}). Which part of distance matters most in your district: travel time, cost, or roads in the rainy season?")
        return ChatResult(generations=[ChatGeneration(message=msg)])

async def main():
    middleware = load_configured_extension_middlewares(get_app_config())
    tools = [t for t in await get_mcp_tools() if t.name in ("search_literature", "lookup_doi")]
    model = Script()
    agent = create_agent(model=model, tools=tools, middleware=middleware)
    state = await agent.ainvoke({"messages": [HumanMessage(content="[SYNTHETIC STUDENT] I study facility delivery in rural Kenya. What should I read on distance?")]},
                                context={"agent_name": "mwenza", "thread_id": "e2e", "run_id": "r1"})
    msgs = state["messages"]
    print("model calls:", len(model.calls))
    print("correction seen by model:", any(getattr(m, "name", "") == "mwenza_constitution" for m in model.calls[-1]))
    print("fabricated draft left in thread:", any("fabricated" in str(m.content) for m in msgs if isinstance(m, AIMessage)))
    print("correction saved in thread:", any(getattr(m, "name", "") == "mwenza_constitution" for m in msgs))
    print("final:", msgs[-1].content)
    print("final review attached:", msgs[-1].additional_kwargs.get("mwenza_constitution"))

asyncio.run(main())
