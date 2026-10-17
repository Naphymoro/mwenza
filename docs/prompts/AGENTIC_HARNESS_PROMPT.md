# Mwenza agentic harness and self-improvement prompt

This prompt asks for a design analysis that turns Mwenza from a set of deterministic checks with an early agent catalogue into a fully agentic research partner. The agent works in sandboxes and improves its own harness over time. The design draws on Google and Carnegie Mellon's Harmony Harness, ByteDance's DeerFlow 2.0, Tsinghua's OpenMAIC and Manus-style task sandboxes. It asks for analysis only; code waits for approval.

## The prompt

```text
Role: Act as an agent-systems architect and a doctoral research-methodology supervisor
designing Mwenza's agent runtime.

Context: Mwenza (this repo) is a source-grounded research workspace for postgraduate
students, focused on African scholarship. It already has:
- deterministic methodology checks (golden thread, paradigm-method fit, citation audit,
  method navigator) and a provenance ledger;
- open literature discovery and its own MCP server (backend/src/mwenza_engine/mcp_server.py);
- an agent catalogue (agents.py: librarian, methodologist, sceptic, reproducer, scout,
  synthesiser) with least-privilege skills and tools, but no language model connected
  (model_gateway.py is a stub).
Mwenza's rules: every material claim points to inspectable evidence; it abstains when
evidence is missing; it teaches and questions rather than ghost-writes; it records
provenance; tools are least-privilege; it must work on low bandwidth.

Goal: Make Mwenza fully agentic:
1. A harness: a lead agent that plans, delegates to sub-agents, uses skills and tools,
   remembers the student's project, and asks the human at decision points.
2. Sandboxes, like Manus: each task gets an isolated workspace with a file system,
   code execution (R, Python, Stata-like stats), a browser for open sources and
   document tools, so agents can actually run analyses, reproduce statistics and build
   artefacts.
3. Recursive self-improvement: the harness (prompts, skills, tools, orchestration)
   improves itself from evaluated experience, and the improvement procedure itself
   improves, in the spirit of Harmony Harness (multi-objective, factorized evolution,
   per-task composition).
4. Multi-agent learning experiences, inspired by OpenMAIC: a virtual supervisory
   committee, a viva simulator and a reviewer #2, staged as a classroom-like session.

Sources to learn from (public papers, docs and code under their licences only; cite
each one used, and mark anything unverified):
- Harmony Harness: Multi-Objective Self-Evolution of Agent Harnesses (arXiv 2610.15150)
- DeerFlow 2.0 (github.com/bytedance/deer-flow, MIT)
- OpenMAIC (github.com/THU-MAIC/OpenMAIC, MIT) and the MAIC paper (JCST 2026)
- Manus's published description of its per-task sandbox
- Self-evolving skill libraries: SkillRL, MetaSkill-Evolve, Ratchet, Memento-Skills
- Open sandbox runtimes (for example E2B, Microsandbox, gVisor, Docker)

Hard constraints:
- Self-improvement may never weaken the evidence contract, abstention, academic
  integrity, privacy or tool permissions. These are fixed, outside what evolves.
- Student work is never used to improve the harness without explicit consent.
- Every evolved change is evaluated on held-out tasks and approved by a human before
  it ships.
- Sandboxes have no network by default, no host access and resource limits; untrusted
  code never runs in the web process.
- Copy no protected expression: borrow ideas; reuse code only under its licence, with
  attribution.

Phase 1 is analysis only, no code. Produce a design document that covers:
1. What each source does, from primary sources, and what Mwenza should take from it.
2. Build-versus-adopt: build a harness, adopt DeerFlow as the runtime, or use an agent
   SDK, with a recommendation.
3. The architecture: lead agent and sub-agents, skills, tools, memory, human-in-the-loop,
   model gateway (including local models for low bandwidth).
4. The sandbox design: runtime, isolation, resource limits, network policy, file
   handling, and how results return as evidence with provenance.
5. The self-improvement loop: what evolves, the objectives, operators, evaluation suite,
   safety gates, and how the improvement procedure improves.
6. The OpenMAIC-style learning sessions.
7. Risks, costs, an evaluation plan tied to docs/EVALUATION.md, and a phased build plan.

Output: a design document with sources linked and unverified claims marked. Stop for my
approval before writing code. After approval, build in phases with tests (synthetic,
clearly labelled data) and browser checks; I approve each commit to main.
```

## How this prompt was built

The original request was: "implement something along the Harmony harness of Google and recursive self-learning; I need Mwenza to be fully agentic as well, with possible sandboxes like Manus AI; let it draw inspiration from DeerFlow and OpenMAIC."

| Original intent | What the prompt now does | Why |
| --- | --- | --- |
| "Harmony harness of Google" | Names the paper (Google and Carnegie Mellon, arXiv 2610.15150) and its three ideas: multi-objective evolution, factorized operators, per-task composition | "Harmony" also matches unrelated products, and the paper is research, not a Google product to install |
| "Recursive self-learning" | Separates improving the harness from improving the improvement procedure, and fixes the guardrails outside what evolves | Unbounded self-modification could optimise away integrity rules; recursion must be bounded and audited |
| "Fully agentic" | Spells out the harness: lead agent, sub-agents, skills, memory, human checkpoints | Makes "agentic" buildable and testable |
| "Sandboxes like Manus" | Specifies per-task isolated workspaces with execution, files and browser, and their network and resource policy | Running code for students is the biggest security risk; the policy comes first |
| "Inspiration from DeerFlow and OpenMAIC" | Asks for a build-versus-adopt decision and what to take from each | Both are MIT-licensed, so adoption is possible; you already run a DeerFlow fork |
| (implicit) Mwenza's principles | Keeps the evidence contract, abstention, no ghost-writing and provenance as hard constraints | Agency must strengthen Mwenza's guarantees, not bypass them |
| (workflow) | Analysis first, then phased builds with approval before each commit | Matches how earlier Mwenza phases were built |
