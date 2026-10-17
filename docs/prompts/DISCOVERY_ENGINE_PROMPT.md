# Mwenza scholarly discovery engine prompt

This prompt asks for a design analysis of Mwenza's own literature discovery layer: one that matches the capabilities of Ai2's Asta Scientific Corpus Tool but is built from openly licensed data, so Mwenza can be licensed, including commercially. It asks for analysis only; code waits for approval.

## The prompt

```text
Role: Act as a research-infrastructure architect and research librarian building
Mwenza's own scholarly discovery engine.

Context: Mwenza (this repo) has an optional Asta connector (backend/src/mwenza_engine/discovery.py).
Asta's licence restricts it to academic, non-commercial use and forbids reverse
engineering, so Mwenza needs its own discovery layer that it can license, including
commercially. Mwenza's rules: every answer points to inspectable evidence, it abstains
when evidence is missing, it records provenance, it uses least-privilege tools, and it
prioritises African research and low-bandwidth use.

Goal: Give Mwenza literature search that matches Asta's capabilities, built only from
openly licensed data and clean-room design:
- paper search by relevance and title
- passage (snippet) search over open-access full text
- citation graph (papers citing / cited by)
- author lookup

Hard constraints:
- Do not reverse-engineer, scrape or copy Asta, Semantic Scholar or any service whose
  terms forbid it. Learn only from public documentation, published papers, and
  open-source code used under its licence (for example AstaBench, Ai2 Scholar QA,
  OpenScholar, PaperQA2). Cite each one you use.
- Every data source must allow Mwenza's intended use. Record its licence, attribution
  rule and rate limits in the capability registry.
- Store full text only for open-access papers whose licence permits it; otherwise keep
  metadata and abstracts where allowed, and link out.

Phase 1 is analysis only, no code. Produce a design document that covers:
1. How Asta and Semantic Scholar get their data, from official sources only.
2. A comparison of open alternatives: OpenAlex, Crossref, OpenCitations, Unpaywall,
   Europe PMC / PMC open-access subset, arXiv, CORE, DOAJ, AJOL and African
   institutional repositories. For each: coverage (especially African journals), data
   type (metadata, abstracts, full text, citations), licence and commercial use, API
   and bulk-download options, rate limits, update frequency. Verify licences on each
   source's official page and mark anything unverified.
3. An architecture:
   - federated live search versus a local index, and the hybrid between them;
   - deduplication by DOI and title;
   - an open-access full-text pipeline (PDF → page-aware evidence spans, reusing
     Mwenza's ingest);
   - hybrid lexical plus embedding retrieval;
   - snippet ranking;
   - a citation graph;
   - caching and rate-limit compliance;
   - offline / low-bandwidth mode;
   - exposing Mwenza's own MCP server so other agents can use it.
4. How results enter the existing evidence contract (EvidenceSpan, citation auditor,
   golden thread gap evidence, provenance ledger) without breaking abstention.
5. An evaluation plan against open benchmarks (for example ScholarQABench or AstaBench
   literature tasks), with recall@k, citation precision and an African-coverage metric
   added to docs/EVALUATION.md.
6. Costs (hosting, storage, embedding compute) for a small deployment and a
   university-wide one.
7. A phased build plan: MVP connector first, then local index, then full-text snippets
   and citation graph.

Output: a design document with sources linked and unverified claims marked. Stop for
my approval before writing code. After approval, build in phases with tests and
browser checks; I approve each commit to main.
```

## How this prompt was built

The original request was to analyse Asta with Mwenza's reverse-engineering tool (REA), read its design, and build an equally robust discovery engine, and to find out where Asta gets its sources. The prompt keeps that goal but changes the method.

| Original intent | What the prompt now does | Why |
| --- | --- | --- |
| "Use REA to analyse Asta and read its design" | Learns only from public documentation, published papers and open-source code under its licence | Asta's licence forbids reverse engineering and decompiling its tools and corpus, and Asta runs on Ai2's servers, so REA could only see its public interface anyway. A clean-room design keeps Mwenza licensable. |
| "An equally robust solution" | Names the capabilities to match: relevance and title search, snippet search, citation graph, author lookup | "Robust" becomes something that can be built and tested |
| "Where does Asta get its sources?" | Makes it step 1, answered from official sources, then compares open alternatives on licence, coverage, African content and cost | Knowing the data supply chain decides what Mwenza can legally build on |
| "Something similar for Mwenza" | Requires results to flow into Mwenza's evidence contract, citation audit, golden thread and provenance ledger | Discovery must strengthen Mwenza's existing guarantees, not bypass them |
| (implicit) "as good as Asta" | Adds evaluation on open benchmarks plus an African-coverage metric | Makes the comparison measurable |
| (implicit) licensing Mwenza | Requires a recorded licence, attribution rule and rate limit for every data source | Avoids repeating the Asta problem with another source |
| (workflow) | Analysis first, then phased builds with approval before each commit | Matches how Mwenza's Phase 1 features were built |
