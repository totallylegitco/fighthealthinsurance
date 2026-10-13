# The chooser (Appeal Arena)

`/chooser/` is where visitors judge several AI drafts side by side on a
synthetic case, and `/chooser/rankings/` is the public scoreboard built from
those votes. The votes train the selector that picks drafts in the real
appeal flow, and rank the model backends against each other.

## What a visitor sees

- **The case.** For an appeal task: the treatment and diagnosis, a fictional
  insurer and denial reason, a short list of *case facts* (age range,
  symptom duration, what was tried, what the clinician documented) and the
  *evidence on file* (PubMed articles, with links). For a chat task: the
  conversation and the question the drafts answer.
- **The drafts**, blind. The API sends no model name, synthesized flag or
  metadata (`ChooserCandidateSerializer`), and no row id or
  `candidate_index` either: both run in generation order (internal model
  first, synthesized last). Each draft goes out as an opaque token
  (`chooser_tokens.candidate_token`, the id encrypted with a fresh nonce)
  that the vote endpoint resolves back, and the drafts are served in random
  order, so a vote is for the letter, not the brand.
- **House rules.** Pick the draft you would send; a draft that invents a
  study, a law, a test result, a date or a history that is not in the case is
  a foul and should never win; skip if unsure.
- **A flag per draft** ("Makes things up"). Flags ride along with the vote as
  `flagged_candidate_ids`; a flagged draft cannot be the chosen one, and the
  server rejects a vote that tries.
- A per-browser scoreboard (rounds judged, fouls called) in `localStorage`;
  nothing about it is sent anywhere.

## How a case is made (`chooser_tasks.py`)

1. **Seed pair.** When `CHOOSER_SEED_FROM_RANKINGS` is on (default) the
   scenario is built around a real `(treatment, condition)` pair from
   `condition_rankings.seed_pairs()`: pairs entered by at least k different
   people, both terms vouched for by a medical vocabulary (see below). The pool
   being empty (no refresh has run yet) falls back to the old behaviour,
   where the writer model invents the pair.
2. **Scenario.** A general-purpose backend writes the insurer, the denial
   reason and the case facts (`_scenario_prompt`). Facts are parsed from
   one semicolon-separated line or a bullet list (`_facts_from_response`)
   and stored in `context_json["facts"]`; a scenario without facts is still
   used.
3. **Evidence.** `_evidence_for` attaches up to `CHOOSER_EVIDENCE_LIMIT`
   articles for the pair to `context_json["evidence"]` as `{pmid, title,
   url}`. It reads the cached PubMed searches first (`PubMedQueryData` rows
   written by every search, any age) and only searches live when nothing is
   cached and `CHOOSER_PUBMED_LIVE_SEARCH` allows it (off in tests). Seeded
   pairs are exactly the ones real appeals already searched for, so a seeded
   task usually costs no NCBI call.
4. **Drafts.** Each backend is told the facts are the only facts and the
   evidence list is the only thing it may cite (`_build_appeal_prompt`), so a
   draft that makes things up is doing so against instructions, and the
   voter can check it against the same list.

## Rankings and privacy (`condition_rankings.py`, `public_rankings.py`)

The public page shows two things, both safe to publish:

- **Model rankings**: `ChooserVote` rows on tasks whose `source` is
  `synthetic`, cast since blind voting began (`public_rankings.blind_since`:
  when migration 0240 was applied, or `PUBLIC_RANKINGS_SINCE`), and nothing
  else. Win rate is votes won over votes shown in;
  "caught making things up" is flags over votes shown in. Models with fewer
  than `PUBLIC_RANKINGS_MIN_SHOWN` votes are listed as warming up. Real
  patients' picks, call logs, chat turns and session counts stay on the
  staff dashboard (`/timbit/...`, `ModelUsageDashboardView`).
- **Most-appealed conditions and treatments**: aggregates over
  `Denial.diagnosis` / `Denial.procedure`. A term is shown only if it

  1. comes from a denial that is not flagged for exclusion or from a test
     account (`TEST_ACCOUNT_EMAILS`);
  2. is shaped like a medical term (`looks_like_medical_term`: no digit
     runs, no pronouns, no addresses, no non-answers like "see attached");
  3. was entered by at least `CONDITION_RANKING_MIN_PEOPLE` (default 5)
     different people, counted by distinct hashed email after
     normalization, so one person filing a case five times, or spelling a
     term five ways, counts once. A term below that threshold is never
     shown, never seeded into a case, and never sent to an outside service;
  4. is vouched for by a vocabulary: the microsite list in the repo, RxNorm
     for drug-shaped treatments, then NCBI (a MeSH lookup, and for compound
     phrases a quoted title/abstract search with at least
     `CONDITION_RANKING_MIN_PUBMED_HITS` hits). Verdicts persist in
     `MedicalTermCheck`, so each term costs outside lookups once; a refresh
     spends at most `CONDITION_RANKING_LOOKUP_BUDGET` of them.

  Counts are rounded down to a multiple of the threshold ("25+").

The verdicts are refreshed in the background: the chooser refill actor calls
`condition_rankings.refresh_if_due()` after each tick (once an hour
fleet-wide, via the `ModelHealthAlertState` claim), and
`python manage.py refresh_condition_rankings [--budget N]` does it by hand.
A page load reads stored verdicts only and never calls NCBI. Page data is
cached for `PUBLIC_RANKINGS_CACHE_SECONDS`; `?format=json` returns the same
data for embedding.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `CHOOSER_SEED_FROM_RANKINGS` | `True` | Build appeal scenarios around a real, k-anonymous pair |
| `CHOOSER_EVIDENCE_LIMIT` | `5` | Articles attached to a scenario |
| `CHOOSER_PUBMED_LIVE_SEARCH` | `True` (`False` in tests) | Search PubMed when nothing is cached for the pair |
| `CHOOSER_PUBMED_SEARCH_TIMEOUT` | `20.0` | Seconds a live search may take |
| `CONDITION_RANKING_MIN_PEOPLE` | `5` | The k in k-anonymity: different people per term |
| `CONDITION_RANKING_LOOKUP_BUDGET` | `30` | Outside lookups per refresh |
| `CONDITION_RANKING_RECHECK_DAYS` | `365` | When a stored verdict is asked again |
| `CONDITION_RANKING_MIN_PUBMED_HITS` | `20` | Hits a quoted phrase needs in PubMed |
| `CONDITION_RANKING_REFRESH_SECONDS` | `3600` | How often `refresh_if_due` refreshes |
| `CONDITION_RANKING_LIMIT` | `25` | Rows per list on the public page |
| `PUBLIC_RANKINGS_CACHE_SECONDS` | `900` | How long the page's numbers are cached |
| `PUBLIC_RANKINGS_MIN_SHOWN` | `10` | Votes before a model is ranked rather than warming up |
| `PUBLIC_RANKINGS_SINCE` | migration 0240's applied time | Earliest vote the public page counts; `""` counts all |

## Exports

`charts:chooser_ranked_export` (staff only) carries each candidate's
`flag_count` beside the vote counts, so the preference data and the
fabrication flags travel together.
