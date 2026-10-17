# Mwenza tool reference

All tools are read-only. Discovery tools call open scholarly APIs; the checks run locally and deterministically.

## Discovery

| Tool | Inputs | Read first |
| --- | --- | --- |
| `search_literature` | `query` (keywords, quotes for phrases; a DOI is looked up directly), `scope` (`all`, `peer-reviewed`, `preprints`), `limit` ≤ 25, `year_from`, `year_to` | `results[]`: `title`, `authors`, `year`, `venue`, `doi`, `preprint`, `retracted`, `published`, `abstract_storable`; `sources_status` says which sources answered |
| `lookup_doi` | `doi` | `result` (one record, same fields) |
| `get_citations` | `doi`, `direction` (`citing` or `references`), `limit` ≤ 50 | `results[]` |
| `check_published_version` | a bioRxiv or medRxiv `doi` (10.1101/...) | `published`: null if not yet published |

A source that times out appears in `sources_status`; say that the search was partial.

## Checks

All three take `wording`: `researcher's own words` or `agent paraphrase`. With a paraphrase the result carries
`confirm_with_researcher`; do that before reporting the status. Empty input is refused with what to ask for.

| Tool | Inputs | Read first |
| --- | --- | --- |
| `check_golden_thread` | `design`: `problem`, `gap`, `aim`, `objectives[]`, `questions[]`, `hypotheses[]`, `paradigm`, `approach`, `strategy`, `theory`, `constructs[]`, `data_collection[]`, `analysis[]`, `findings[]` | `status` (`aligned` or `needs-revision`), `issues[]` with `severity`, `message`, `teach` |
| `check_paradigm_fit` | `design`: `paradigm`, `approach`, `logic`, `strategy`, `time_horizon`, `sampling`, `sample_size`, `data_collection[]`, `analysis[]`, `quality[]`, `hypotheses[]`, `questions[]` | `status`, `issues[]` with `message`, `teach`, `ask`, `alternatives` |
| `audit_citations` | `text` (the student's draft), `sources[]` (`name` with surname and year, `text`, optional `id`), optional `references` linking `[1]`-style keys to source ids | `sentences[]`: each citation's `verdict` (`supported`, `partial`, `contrasting`, `misquoted-number`, `unrelated`, `unresolved`) and the matching `passage`; `flags` such as `needs-citation` |

## Navigator

`navigate_methodology` takes `answers`: the option ids chosen so far (`[]` to start). It returns either
`next` (the question and its options) or, once `complete` is true, `design` (strategy, sampling, data
collection, analysis, quality criteria, `reasons`, `cautions`, fitting `paradigms`) and `method_fields`,
ready to pass to `check_paradigm_fit`.
