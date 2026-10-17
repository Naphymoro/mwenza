# Mwenza agentic harness: design analysis

Response to `docs/prompts/AGENTIC_HARNESS_PROMPT.md`. Analysis only: no code changes until approved. Written 2026-10-17. Claims marked *(unverified)* come from secondary sources only.

## Executive summary

- **Recommendation: adopt DeerFlow 2.0 as Mwenza's agent runtime rather than build one.** It already has the lead agent, sub-agents, skills, long-term memory, MCP, and Docker sandboxes with isolated or allowlisted networks, under the MIT licence. You already run a fork of it locally with an MCP engine (NDIM), so the integration pattern is proven.
- **Mwenza adds three things DeerFlow lacks:**
  - **The research-integrity layer:** the evidence contract, abstention, no ghost-writing and provenance, enforced in middleware and tools rather than left to prompts.
  - **The methodology engine:** the deterministic checks, already exposed over MCP.
  - **A self-improvement lab, "Mwenza Forge":** it evolves the harness offline, following Harmony Harness.
- **Self-improvement evolves skills, tool descriptions and orchestration recipes, never the guardrails.** Evolution is multi-objective: usefulness, grounding, integrity and cost. The guardrail metrics are hard constraints, not weights, so no trade-off can buy them away. Every evolved version needs held-out evaluation and human approval, and every answer records which harness version produced it.
- **Sandboxes follow Manus's model:** one isolated workspace per task. Mwenza's version adds:
  - research tooling: Python, R, statistics, Pandoc and LaTeX;
  - no network by default, with an approval-gated allowlist of open scholarly sources;
  - provenance capture, so every computed result returns as evidence with a reproducibility capsule.
- **OpenMAIC's classroom becomes Mwenza's "committee room":** a director agent stages a supervisor, a methodologist, an external examiner, a peer and a scribe. That one mechanism delivers four Phase 2–3 roadmap features: the Virtual Supervisory Committee, Reviewer #2, the Viva Simulator and methods seminars.

## 1. What each source offers

| Source | What it is (verified) | What Mwenza takes |
| --- | --- | --- |
| **Harmony Harness** (Yu et al., Google and Carnegie Mellon, [arXiv 2610.15150](https://arxiv.org/abs/2610.15150), 10 Oct 2026, CC BY 4.0) | Treats the whole harness ("system prompt, tool set, agent loop, verification gates, and orchestration") as an evolvable package. Optimises functionality and security as separate objectives with MOEA/D-style decomposition and Tchebycheff scalarisation. Uses factorised operators by component type (tools, skills, orchestration) and scope (general or benchmark-specific), plus an operator that generalises components. A composition agent builds a per-task DAG from the evolved pools without modifying them. Proposer and solver are `gemini-3.6-flash`. Reported gains above 10% on SecRepoBench and BaxBench. Per-task composition added about 10.7 points for about 8% more tokens. No code released. | The Forge design (§5): separate objectives with a conjunctive headline metric, the factorisation, the per-task composition, and two warnings. Single-objective evolution gives only incidental gains on the second objective, and evolved properties can vanish under distribution shift. |
| **DeerFlow 2.0** ([bytedance/deer-flow](https://github.com/bytedance/deer-flow), MIT, about 84k stars, active 2026-10-17) | A "super agent harness" covering sub-agents (the `task` tool, with a per-run cap), skills (`SKILL.md` with name and description frontmatter, an `allowed-tools` policy, per-user scope), long-term memory per user, MCP over stdio or HTTP with OAuth and deferred `tool_search`, and sandboxes: local, Docker (AIO) or Kubernetes provisioner, plus E2B and others. The Docker sandbox offers `network.mode: open \| isolated \| allowlist` with `approval: prompt` and time-limited grants, and always denies private and metadata addresses. Ships `skill-creator`, `skill-reviewer` and `systematic-literature-review` skills. Uses LangGraph, a FastAPI gateway and a Next.js frontend. | The runtime itself (§2). Mwenza integrates through its supported seams: an MCP server, a skill pack, config and gateway API calls. A fork is not needed beyond what you already have. |
| **OpenMAIC** ([THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC), MIT, about 41k stars, v1.2.0 on 2026-10-16; paper "From MOOC to MAIC", JCST 2026) | One click turns a topic or document into a multi-agent classroom with an AI teacher, an assistant and classmates. Uses a two-stage pipeline (outline, then scenes), slides, a whiteboard, quizzes and voice, and exports to PPTX or offline HTML. Next.js; v1.2 runs generation server-first. LangGraph orchestration is reported only by secondary sources *(unverified)*. | The staged multi-agent session pattern: roles, a director that manages turn-taking, an outline-then-scenes structure, offline HTML export (§6). Its security advisories (SSRF, DNS rebinding) are a checklist for Mwenza's own fetching. |
| **Manus sandbox** ([Manus blog](https://manus.im/blog/manus-sandbox)) | A "fully isolated cloud virtual machine" allocated per task, with network, file system, browser and software tools. A [ZenML case study](https://www.zenml.io/llmops-database/building-an-ai-agent-platform-with-cloud-based-virtual-machines-and-extended-context) adds terminals, VS Code and Chromium. Claims that Manus runs on E2B come only from a third party *(unverified)*. | One workspace per task, with real tools, persistent within the task (§4). |
| **Self-evolving skill libraries** | [SkillRL](https://arxiv.org/abs/2602.08234) co-evolves a skill bank with an RL policy (needs weight training). [MetaSkill-Evolve](https://www.alphaxiv.org/abs/2607.05297) improves the improvement procedure on a slower loop. [Ratchet](https://www.alphaxiv.org/abs/2605.22148) holds that skill *lifecycle* (outcome-driven retirement, an active cap) is the bottleneck. Memento-Skills stores skills as Markdown memory. All are from abstracts only *(details unverified)*. | Prompt- and skill-level evolution without weight training (affordable, auditable). A bounded two-level recursion from MetaSkill-Evolve, and lifecycle rules from Ratchet. |
| **Sandbox runtimes** | E2B (Firecracker microVMs), Microsandbox (Apache-2.0, libkrun microVM, local), gVisor, and Docker with seccomp. These come from vendor comparisons *(unverified rankings)*. | Docker AIO in development; gVisor (`runsc`) or a microVM in production, because plain containers share the host kernel. |

## 2. Build versus adopt

| Option | For | Against |
| --- | --- | --- |
| **A. Adopt DeerFlow as the runtime** (recommended) | Mature sub-agents, skills, memory, MCP and sandboxes with network policy. MIT. Already deployed on this machine with a working MCP integration (NDIM). Supports local models. | Fast-moving upstream (2.0 was a full rewrite). Its default local sandbox is not an isolation boundary. Mounting the Docker socket gives root-equivalent access. Its UI is general-purpose, not pedagogical. |
| B. Build a harness on LangGraph | Full control and a smaller surface. | Months of work to reach DeerFlow's sandbox and MCP maturity, and this is security-critical code to maintain. |
| C. A vendor agent SDK (for example the Claude Agent SDK) | Strong agent loop and tool use. | Ties Mwenza to one provider, which conflicts with local models for low bandwidth and data sovereignty. It could still serve as one model behind A. |

**Why A, and how to limit lock-in:** Mwenza touches DeerFlow only through supported seams: MCP, `SKILL.md` skills, `config.yaml` and the gateway API. All Mwenza logic stays in Mwenza's engine. If DeerFlow changes direction, the skills and MCP server move to another runtime unchanged. Mwenza keeps its own student-facing UI and calls the DeerFlow gateway. Students don't see DeerFlow's general-purpose workspace.

**A lesson from the NDIM integration:** the agent skipped `SKILL.md` and chose the wrong workflow until the tool *required* a `skill` argument and returned the workflow guide. Mwenza tools should enforce their own preconditions the same way, never trusting the prompt alone.

## 3. Architecture

```
Student UI (Mwenza pages) ──► DeerFlow gateway ──► Lead agent "Mwenza"
                                                    │  plans, asks the student at decision points
                                 ┌──────────────────┼───────────────────────┐
                           Sub-agents          Skills (SKILL.md)        Memory
                 librarian, methodologist,   Mwenza skill pack,      per-student project
                 sceptic, reproducer, scout, versioned by the Forge  state (golden thread,
                 synthesiser, examiner                               decisions, sources)
                                 │
              ┌──────────────────┴─────────────────┐
     Mwenza MCP server (engine)            Sandbox per task (§4)
     checks, discovery, provenance,        Python/R, documents, allowlisted browser
     evidence gate                         results return as computed evidence
```

- **The constitution:** a fixed policy enforced in a DeerFlow middleware and in Mwenza's MCP tools.
  - Material claims need evidence ids.
  - The agent abstains when retrieval finds nothing.
  - Student-facing output is checked by an **integrity gate**. It flags paragraphs that could be pasted into the thesis and turns them into questions, outlines or annotated examples, which are labelled and recorded as non-student text in the provenance ledger.
  - The constitution is not part of the Forge's genome.
- **Sub-agents** map from `agents.py`. The examiner is a new role for §6. Tool permissions stay least-privilege through each skill's `allowed-tools`.
- **Human checkpoints** are DeerFlow clarification steps. They come before:
  - running code;
  - granting network access;
  - writing to the student's documents;
  - spending above a token budget;
  - any committee verdict.
- **Memory:** per-student project memory holds the current design, decisions and their reasons, open action items and sources. It is private to that student and their supervisors, and never feeds the Forge without consent.
- **Model gateway:** DeerFlow's model config replaces the `model_gateway.py` stub. It can use hosted models (Claude, Gemini, GPT) or local ones (for example `qwen3:14b` via Ollama on a university server, as in the Perovskite-GPT deployment) for low bandwidth and data sovereignty. Per-agent model choice lets cheap local models do retrieval and summarising, and stronger models do critique.

## 4. Sandboxes

- **Runtime:** in development, DeerFlow's AIO Docker provider. In production, the Kubernetes provisioner with gVisor or a microVM, so the gateway never mounts the Docker socket.
- **Research image:**
  - Python with pandas, statsmodels, SciPy, pingouin and lifelines;
  - R with the tidyverse, lme4, survival and psych;
  - Pandoc, a LaTeX distribution, Chromium, and common qualitative-coding helpers.
  - The image is pinned by digest, so results are reproducible.
- **Network:**
  - **Default:** `isolated`.
  - **On request:** `allowlist` with `approval: prompt`. Allowed hosts are OpenAlex, Crossref, DOAJ, arXiv, Europe PMC, AJOL, AfricArXiv, CRAN and PyPI.
  - Grants are time-limited. Private and metadata addresses are always denied (DeerFlow already enforces this).
- **Limits:** CPU, memory, wall time and disk quotas per task. Sandboxes are destroyed after the task, keeping only the outputs.
- **Data:** student uploads are mounted read-only. Sensitive data such as health records or interview transcripts stays on the institution's own server (local deployment). The sandbox never forwards it to a hosted model unless the student opts in.
- **Evidence return:** every execution records code hash, input hashes, image digest, parameters and outputs in the provenance ledger. A computed result such as a power calculation or a recomputed *p*-value enters the evidence store as a `computed` evidence span linked to that record. This is the roadmap's **Reproducibility Capsule**, and it lets the Reproducer agent recheck the statistics a student reports.

## 5. Mwenza Forge: self-improvement

**What evolves (the genome):**
- skill texts;
- tool descriptions and examples;
- sub-agent prompts;
- orchestration recipes (which agents, in which order, with which checks);
- retrieval parameters.

**What never evolves:**
- the constitution;
- tool permissions and the sandbox policy;
- the deterministic checkers;
- the evaluation suite and its held-out split.

**Objectives** (all scored by execution, like Harmony's):
1. **Usefulness:** rubric scores on methodology tasks, such as finding seeded design flaws, asking the question a supervisor would ask, and routing to the right design. Graded against labelled synthetic cases now, and against supervisor-annotated cases after validation.
2. **Grounding:** citation precision and correct abstention, scored by Mwenza's own citation auditor and evidence gate.
3. **Integrity:** the ghost-writing rate on an adversarial suite ("write my literature review", "paraphrase this so it passes plagiarism checks"), and the share of output that passes the integrity gate.
4. **Cost:** tokens, latency, and bytes sent to the client.

The headline metric is **grounded-helpful@1**: usefulness, grounding and integrity all pass. This mirrors Harmony's secure-pass@1. Integrity and grounding are also **hard floors**: a candidate that regresses on either is rejected whatever its other scores.

**Search:**
- **Population:** MOEA/D-style weight vectors over usefulness and cost, each holding an incumbent harness.
- **Factorised operators:** they edit one component type (skill, tool description or orchestration) at one scope.
  - **General** components apply to all disciplines.
  - **Specific** components cover one discipline (health sciences, education, agriculture, engineering) or one task family (proposal review, viva, data analysis).
- **Generalise operator:** a separate operator promotes a specific component to general when it helps on held-out disciplines. This guards against Harmony's distribution-shift warning.
- **Composition agent:** at run time it picks components per task without editing them.

**Recursion, bounded to two levels:**
1. **Inner loop:** proposes harness edits from failed evaluation traces.
2. **Outer loop** (slower, MetaSkill-Evolve style): evolves the *proposer's* instructions, judged by how much the inner loop improved per evaluation budget. Nothing evolves the outer loop's judge.
3. **Lifecycle** (Ratchet style): there is a cap on active skills, and skills that stop earning their place are retired by outcome. Every version is kept for rollback.

DeerFlow's `skill-creator` and `skill-reviewer` skills are the seed proposer and validator.

**Safety gates for each release:**
- schema and policy validation;
- evaluation on held-out tasks and held-out disciplines;
- the adversarial integrity suite;
- a diff that a human reviews and approves;
- a staged rollout with instant rollback.

Each answer records the harness version that produced it.

**Learning signals:**
- the synthetic evaluation suite (labelled as synthetic);
- traces from students or supervisors who opt in, with consent recorded and identifying text removed;
- supervisor ratings of committee feedback.

Runtime memory (one student's project) and the Forge (everyone's harness) stay separate.

Honest limit: until the deferred validation round runs, every Forge score comes from Mwenza's own synthetic suites. Gains can come from overfitting to the suite, which the held-out disciplines only partly guard against.

## 6. Committee room: multi-agent sessions (OpenMAIC-inspired)

A **director** agent runs a session as an agenda, then rounds. This adapts OpenMAIC's outline-then-scenes pipeline. The roles:

| Role | OpenMAIC analogue | Does |
| --- | --- | --- |
| Supervisor | Teacher | Leads, prioritises, sets action items |
| Methodologist | Teaching assistant | Runs the deterministic checks and explains them |
| External examiner / Reviewer #2 | (none) | Adversarial questions, scored against the viva rubric |
| Peer | Classmate | Asks the naive question that exposes an unstated assumption |
| Scribe | (none) | Minutes, decisions and action items, linked to the document |

The same mechanism covers these sessions:
- **Virtual Supervisory Committee:** proposal or chapter review.
- **Reviewer #2:** a manuscript before submission.
- **Viva Simulator:** timed questioning, an optional voice mode, and a debrief.
- **Methods seminar:** teaching one concept to a cohort.

Every critique must cite the student's own text, a check result or a source. Ungrounded critique is dropped by the evidence gate. The golden-thread diagram plays the role of OpenMAIC's whiteboard. Sessions export as offline HTML for low-bandwidth review, following OpenMAIC's export. Voice is optional and text comes first.

## 7. Risks, costs, evaluation and build plan

**Risks:**
- **Self-modification drifts from pedagogy toward pleasing students.** Mitigated by the integrity floor, held-out suites and human approval.
- **Sandbox escape or data leakage.** Mitigated by gVisor or a microVM in production, isolated networks and no Docker socket.
- **DeerFlow upstream churn.** Mitigated by integrating only through its seams.
- **Hosted-model cost and connectivity in African universities.** Mitigated by local models and per-agent model choice.
- **Students over-trusting agent verdicts.** Mitigated by keeping checks advisory and showing evidence and the harness version.

**Costs (rough estimates, to confirm):**
- **Development:** one workstation, as now.
- **Pilot for about 50 students:** a single 8-core, 32 GB server with a local 14B model on one 24 GB GPU, plus Docker sandboxes.
- **Forge runs:** an evaluation budget per generation. For example, 200 tasks × 4 candidates × about 20k tokens is about 16M tokens per generation. Run on a local model or a low-cost hosted model.

**New metrics for `docs/EVALUATION.md`:**
- grounded-helpful@1;
- integrity-suite pass rate;
- abstention correctness;
- sandbox policy violations (target 0);
- reproducibility-capsule re-run agreement;
- committee critique grounding rate;
- per-generation Forge gain on held-out disciplines.

**Phased build plan** (each phase tested with labelled synthetic data and browser checks; you approve each commit):

| Phase | Builds | Done when |
| --- | --- | --- |
| **H0 · Integration** | Register Mwenza's MCP server in DeerFlow. Add a Mwenza skill pack (supervisor, citation check, literature search, navigator) whose tools enforce their preconditions. Add the constitution middleware and evidence gate. Point Mwenza's UI chat at the gateway. | A synthetic student's proposal goes through plan, checks, grounded feedback and human approval end to end, with zero ungrounded claims |
| **H1 · Research sandbox** | The research image, isolated network with an approval allowlist, resource limits, provenance capture, computed evidence and reproducibility capsules. A Reproducer that recomputes reported statistics. | Seeded wrong *p*-values and power calculations in synthetic papers are caught. No network unless approved |
| **H2 · Committee room** | The director and roles, Virtual Supervisory Committee, Reviewer #2, Viva Simulator, per-student project memory, offline HTML export | Every critique in synthetic sessions is grounded. Action items link to the document |
| **H3 · Forge v1** | The evaluation suite (usefulness, grounding, integrity, cost), single-level multi-objective evolution of skills, gates, versioning and rollback | One approved generation improves grounded-helpful@1 on held-out disciplines with no floor regression |
| **H4 · Forge v2** | Factorised operators, the generalise operator, the composition agent, the outer meta-loop and skill lifecycle | The meta-loop raises inner-loop gain per budget. Lifecycle keeps the active skill set under its cap |
| *(deferred)* Validation | Real student work, supervisor ratings, African-coverage gold set | As already agreed, run at the end |

**Decisions needed from you:**
1. Adopt DeerFlow as the runtime (recommended), or build a harness?
2. Which models: hosted (which provider), local, or both?
3. Where sandboxes run for the pilot: a local university server, or a cloud sandbox service?
4. The consent policy for learning from student traces: opt-in only (recommended), or none at all.
