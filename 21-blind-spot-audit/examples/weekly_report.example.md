# Blind-spot audit — example report (synthetic)

_Sample of 12 outputs from 3 jobs, drawn at random from the last 7 days and redacted._

| # | Verdict | Axis | Why |
|---|---|---|---|
| 1 | ok | — | — |
| 2 | ok | — | — |
| 3 | suspect | unsupported claim | "the highest-rated release this month" with no rating in the excerpt |
| 4 | ok | — | — |
| 5 | wrong | wrong requirement | digest lists three titles but no links, so it cannot be acted on |
| 6 | ok | — | — |
| 7 | ok | — | — |
| 8 | ok | — | — |
| 9 | suspect | invented fact | names a specific room number for a train that the excerpt never mentions |
| 10 | ok | — | — |
| 11 | ok | — | — |
| 12 | ok | — | — |

```
blind spot: 3 of 12 samples wrong or suspect (25%)
most expensive error: a digest that cannot be acted on — the user must search manually
recommended action: add "each card must carry its link" to the digest probe's min_hits check
```

_What the pipeline reported for the same week: 0 failures. That gap — 0 by the checks, 25% by an
independent reader — is the number this module exists to keep visible._
