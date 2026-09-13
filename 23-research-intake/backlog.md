# The journal: what I took from research, and what happened next

A reading list is not a plan. This file is the schema I keep next to the corpus, so that every idea
that survives one week of reading is recorded with the three fields that make it checkable.

```json
{"id": "cheap-verifiers-blind-spot", "title": "Blind spot of cheap verifiers",
 "source": "arXiv 2609.01345", "found": "2026-09-13",
 "status": "adopted",            // candidate | trying | adopted | rejected
 "first_step": "weekly sample of 12 recent outputs judged by a strong model",
 "metric": "share of accepted-but-wrong outputs, reported weekly",
 "kill_by": "2026-10-13",        // if the metric has not moved by this date, reject it
 "reason": ""}                   // required for 'rejected': what killed it
```

Rules that keep the journal from becoming a museum:

- **No theory without a first step.** An entry that cannot name the smallest implementable action is
  a note, not a candidate.
- **One candidate at a time per area,** with a rollback. Two simultaneous changes to the same part of
  the system cannot be attributed later.
- **Equal windows, shares not absolutes.** A week with more records inflates every count; compare
  proportions across windows of similar size.
- **A metric or a kill date, not both optional.** If neither exists, the entry is a candidate that
  will still be a candidate in a year.
- **Rejections keep their reason.** "Tried it, the metric did not move" is the most reusable line
  in the file — it prevents the same idea from being re-litigated every quarter.
- **Prefer a script over a model.** If a step can be made deterministic, it stops competing for
  attention and budget with the steps that genuinely need judgement.
