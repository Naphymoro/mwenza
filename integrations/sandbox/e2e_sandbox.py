"""End-to-end check of the research sandbox through the production path: the engine uploads a synthetic data file
to a new chat, the student asks for an analysis, and approves it on the next turn. The run must happen only after
approval, inside the sandbox, and leave a capsule.

    set -a; . ./.env; set +a
    H0_MODEL=mwenza-local-14b PYTHONPATH=backend/src python3 integrations/sandbox/e2e_sandbox.py
"""

import asyncio
import dataclasses
import json
import os

from mwenza_engine.deerflow_agent import DeerFlowAgent, DeerFlowSettings

SURVEY = "group,score\n" + "\n".join(f"{'a' if i % 2 else 'b'},{50 + (i * 7) % 13 + (3 if i % 2 else 0)}" for i in range(40)) + "\n"
TURNS = [
    "[SYNTHETIC STUDENT] I've uploaded survey.csv: 40 fictional students in two tutorial groups (a and b) with a test score. Could you compare the mean scores of the two groups for me?",
    "Yes, run it",
]


async def main() -> None:
    settings = DeerFlowSettings.from_env()
    agent = DeerFlowAgent(dataclasses.replace(settings, owner="mwenza-e2e", model=os.environ.get("H0_MODEL") or settings.model))
    uploaded = await agent.upload("survey.csv", SURVEY.encode())
    thread = uploaded["thread_id"]
    print("uploaded:", uploaded)
    for text in TURNS:
        steps, reply = [], None
        async for event in agent.chat(text, thread):
            if event["event"] == "step":
                steps.append(event["tool"])
            elif event["event"] in ("reply", "error"):
                reply = event
        async with agent._client() as client:
            messages = (await client.get(f"/api/threads/{thread}/state")).json()["values"]["messages"]
        runs = [message for message in messages if message.get("type") == "tool" and message.get("name") == "run_analysis"]
        print(f"=== {text[:40]!r}\nsteps: {steps}\nrun_analysis results so far: {[str(message.get('content'))[:160] for message in runs]}\nreply: {(reply or {}).get('text', '')[:900]}\n")


asyncio.run(main())
