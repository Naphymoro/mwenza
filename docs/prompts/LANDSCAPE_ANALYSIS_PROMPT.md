# Mwenza landscape and methodology-engine analysis prompt

This prompt asks for a competitive and pedagogical analysis that will guide
Mwenza's next phase. It asks for analysis only: no code and no repo changes
until the findings are approved.

## The prompt

> **Role:** Act as a senior research-methodology professor (doctoral
> supervisor level) and AI product strategist.
>
> **Context:** Mwenza is my source-grounded research notebook (see
> `README.md`, `docs/ENGINE_ARCHITECTURE.md`, `docs/EVALUATION.md`). How it
> works:
> - Answers cite only the sources the user picked. When the evidence isn't
>   there, Mwenza says so instead of making something up.
> - Governed agents (librarian, methodologist, sceptic, reproducer, scout,
>   synthesiser) run with visible traces and least-privilege tools.
> - It focuses on African research and learning.
>
> **Goal:** I want Mwenza to go beyond being a NotebookLM or Notion clone. It
> should be a **postgraduate research-methodology expert** that guides
> students from idea to published paper. Its job is to teach and enforce
> rigour, not to ghost-write.
>
> **Task: analysis only. Don't write any code yet.**
>
> 1. **Landscape scan.** Survey similar projects on Hugging Face (Spaces,
>    models, datasets, papers) and beyond. Cover research assistants,
>    literature-review tools, academic writing aids and autonomous
>    "AI scientist" agents. Examples: NotebookLM, Notion AI, Elicit,
>    Consensus, SciSpace, Scite, Semantic Scholar, ResearchRabbit, Undermind,
>    Paperpal, Jenni, PaperQA2, OpenScholar, STORM, GPT Researcher, Sakana AI
>    Scientist, Agent Laboratory, plus Anthropic's Claude-for-science
>    offerings.
>    For each one, record:
>    - core features
>    - target user
>    - grounding/citation approach
>    - methodology depth
>    - licence and openness
>    - weaknesses
> 2. **Comparison matrix.** Put Mwenza and the best 10–15 tools side by side
>    on: grounding, citation verification, methodology guidance, writing
>    support, collaboration and knowledge organisation (Notion-like),
>    multimodal outputs (NotebookLM-like), reproducibility, academic
>    integrity, offline/low-bandwidth use and African context.
> 3. **Gap analysis.** List what no existing tool does well, especially at
>    postgraduate level.
> 4. **Methodology engine spec.** Say what Mwenza must master, and how it
>    would guide, critique and check each item:
>    - problem statements and research gaps
>    - research questions, objectives and hypotheses
>    - theoretical vs conceptual frameworks, and theoretical underpinnings
>    - literature review types (systematic/PRISMA, scoping, narrative)
>    - research paradigms and philosophy (ontology, epistemology)
>    - design, sampling, instruments, validity and reliability
>    - analysis plans (quantitative, qualitative, mixed)
>    - ethics
>    - limitations
>    - thesis and journal article structure (IMRaD)
>    - journal selection, peer-review response and publication strategy
> 5. **"Out-of-this-world" differentiators.** Propose 10 or more novel
>    features, each with a rationale, feasibility rating and which existing
>    Mwenza agent or boundary it builds on. Examples: a supervisor-simulation
>    agent, a golden thread checker that tests alignment across problem →
>    questions → theory → method → findings, a reviewer #2 sceptic,
>    citation-claim verification, and a methodology decision tree.
> 6. **Licensing and IP guardrails.** Explain how to take inspiration from
>    Claude, NotebookLM and Notion without infringing: clean-room design,
>    original UI and prompts, and using models only through their APIs under
>    their terms.
> 7. **Prioritised roadmap.** Phases 1–3, from MVP to flagship, with success
>    metrics tied to `docs/EVALUATION.md`.
>
> **Output:** A structured report with an executive summary, the comparison
> table, the gap list, the feature specs and the roadmap. Cite sources with
> links. Mark anything unverified. Stick to analysis: no code and no repo
> changes until I approve.

## How this prompt was built

The original request was ambitious but loose. It asked for a Hugging Face
analysis, a "futuristic" research tool combining NotebookLM and Notion,
postgraduate methodology expertise, and Claude-science-style capability
without licence problems. Each part was made specific so the analysis is
repeatable and its output can be acted on.

| Original intent | What the prompt now does | Why |
| --- | --- | --- |
| "Analyse Hugging Face and similar projects" | Names concrete tool categories and examples, and fixes the six fields to record for each tool | Without set fields, tool surveys turn into marketing summaries that can't be compared |
| "Out of this world, not something already done" | Asks for 10+ differentiators, each with rationale, feasibility and the Mwenza boundary it extends | Novelty only counts against a mapped landscape and must build on what Mwenza already has |
| "Power of NotebookLM and Notion" | Turns both into comparison dimensions: multimodal outputs, and collaboration/knowledge organisation | Lets us measure Mwenza against them rather than copy them |
| "Expert in postgraduate research methodology" | Lists the methodology competencies the engine must cover, from problem statement to publication | Spells out what "expert" means so the result can be tested |
| "Guide students on writing papers" | States that Mwenza teaches and enforces rigour rather than ghost-writing | Protects academic integrity and fits Mwenza's grounding-and-abstention rules |
| "Emulate Claude science without infringing licences" | Adds a licensing and IP section: clean-room design, original UI and prompts, API use under the provider's terms | Separates borrowing ideas, which is fine, from copying protected expression or breaking terms of service |
| "I need the analysis first" | Says analysis only: no code or repo changes until approved | Stops implementation from starting before the strategy is agreed |

### Design principles carried into the prompt

- **Ground it in Mwenza's existing philosophy.** The prompt points at the
  repo's own architecture and evaluation docs. Recommendations then extend
  the evidence contract, the abstention behaviour and the governed agents
  instead of replacing them.
- **Assign an expert role.** Framing the analyst as a doctoral supervisor and
  product strategist gets both pedagogical depth and product judgement.
- **Require structured, cited output.** The comparison matrix, gap list,
  specs and roadmap can be reviewed and tracked. Asking for citations and
  flagging unverified claims keeps the analysis honest.
- **Tie success to measurement.** The roadmap metrics connect back to
  `docs/EVALUATION.md`, so "on steroids" is a target we can measure.
