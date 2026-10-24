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

## Reproducer

Both take `wording`, like the checks above.

| Tool | Inputs | Read first |
| --- | --- | --- |
| `check_reported_statistics` | `text` with APA-style results: `t(df) = x, p = y`, `F(df1, df2) = x`, `χ2(df, N = n) = x`, `r(df) = x`, `z = x` | `status`; `results[]` with `verdict` (`consistent`, `inconsistent`, `decision-error`), `computed_p`, `note`, `teach` |
| `check_sample_size` | `design` (`proportion`, `two-proportions`, `two-means`, `correlation`), `parameters`, `reported_n` | `computed_n`, `verdict` (`consistent`, `larger-than-needed`, `too-small`), `steps`, `achieved_power` |

## Sandbox

| Tool | Inputs | Read first |
| --- | --- | --- |
| `run_analysis` | `language` (`python` or `r`), `code`, `inputs` (uploaded file names), `approval` (the student's words) | `exit_code`, `stdout`, `stderr`, `outputs`, `capsule_id`, `delivered_to`; `evidence.note` |
| `rerun_analysis` | `capsule_id` | `agree`, `output_differences`, `stdout_identical` |

The sandbox has no network. Python has pandas, numpy, scipy, statsmodels, pingouin, lifelines and matplotlib; R has
dplyr, readr, tidyr, ggplot2, lme4, survival and psych. Limits: 1 CPU, 1 GB of memory, 120 s.

## Navigator

`navigate_methodology` takes `answers`: the option ids chosen so far (`[]` to start). It returns either
`next` (the question and its options) or, once `complete` is true, `design` (strategy, sampling, data
collection, analysis, quality criteria, `reasons`, `cautions`, fitting `paradigms`) and `method_fields`,
ready to pass to `check_paradigm_fit`.
