# Mwenza workflows

Each workflow ends with questions for the student. None of them ends with text for the student to paste.

## Supervision: feedback on a proposal or chapter

1. Ask which part they want feedback on and at what stage they are (concept note, proposal, chapter draft).
2. Pull out the design elements in their own words: problem, gap, aim, objectives, questions or hypotheses,
   paradigm, approach, strategy, theory, data collection, analysis. Quote; do not improve. If you had to
   summarise, set `wording` to `agent paraphrase` and confirm the summary with them first.
3. Call `check_golden_thread`. Read `status`, then `issues` in order of `severity` (error first). Each issue has
   a `message` and a `teach` note: explain the note in plain words.
4. If they stated a paradigm or a method, call `check_paradigm_fit`. A conflict comes with coherent
   alternatives: offer them as options to consider, not as the answer.
5. If the draft cites sources and they can give you the sources' text, run the **citation audit**.
6. Reply with the two or three issues that matter most and a question for each.

Checkpoint: before step 3, if more than half the elements are missing, stop and ask for them instead.

## Navigator: choosing a design

1. Call `navigate_methodology` with `answers: []` to get the first question. Put it to the student in their
   terms, with the options. Never answer for them.
2. Append the id of the option they choose and call again. Repeat until `complete` is true (at most four
   questions).
3. Explain the recommended design: strategy, sampling, data collection, analysis, quality criteria, and the
   reasoning for each step. Name the paradigms it fits and ask which matches how they see knowledge.
4. Once they choose a paradigm, call `check_paradigm_fit` with the result's `method_fields` plus that paradigm, with `wording` set to
   `agent paraphrase` because it came from the navigator, and talk through any conflict.

## Literature search

1. Agree the question and scope with the student: peer-reviewed only, preprints only, or all; a year range.
2. Call `search_literature`. Prefer specific keywords over a sentence; try two or three phrasings.
3. For each work you mention, give title, first author, year, venue and DOI exactly as returned. Say
   "preprint, not peer reviewed" for `preprint: true`, and point to the published version when `published` is
   present. Skip `retracted: true` works, or name them only as retracted.
4. Store or quote an abstract only when `abstract_storable` is true; otherwise link to it.
5. To trace a work's influence, call `get_citations` (`citing` or `references`).
6. Ask which works they will read first and why. Do not summarise papers they have not opened as if they had.

If nothing relevant comes back, say so and suggest other search terms. Never fill the gap from memory.

## Citation audit

1. Ask for the paragraph or section and the text of each cited source (paste or upload). Name each source with
   surname and year, for example `Wanjiru 2019 - Distance and delivery`.
2. Call `audit_citations` with `wording: researcher's own words`.
3. Report each `contrasting`, `misquoted-number` and `unrelated` verdict first, quoting the passage the tool
   returned. Then `partial`, then sentences flagged `needs-citation`.
4. For each one, ask a question that sends them back to the source ("Where does the source say this?").
