# Benchmarks

Numbers measured on the deployment these modules were extracted from: a single VPS running an agent
gateway with ~70 scheduled jobs, a state store, and provider APIs. They are measurements, not
benchmarks — your sources, pricing and failure mix will differ. Every row states the window and how it
was measured, so a claim can be re-derived rather than believed.

## Where the tokens went (before)

Measured over 393 job runs, 28 days, from the runtime's usage ledger.

| Line | Tokens | Share | Notes |
|---|---|---|---|
| Total | 121.9M | 100% | 7.6% of runs ended in an error |
| Watchlist job (polled a source, decided per item) | 53.7M | 44% | 162 runs, ~331k input tokens per run |
| Three digest jobs | 26.3M | 22% | ~557k / 941k / 841k input tokens per run |
| Transport/train status | 13.9M | 11% | ~637k input tokens per run |
| Operator sweep bypassing the script | 5.4M | 4% | replaced by the deterministic sweep |
| Redundant health check | 3.3M | 2.6% | overlapped with the eval suite |

Input size per run is the actionable column: a job reading hundreds of thousands of input tokens per
run is either re-reading the world or re-deriving something a script already knows.

## After the conversions

| Change | Before | After | How it was made |
|---|---|---|---|
| Watchlist job | 53.7M tokens, 44% of spend | 0 recurring | deterministic script (folder 24) |
| Digest collection | 3 jobs × ~780k input/run | 1 collector + a formatter prompt | folder 24 |
| Cost visibility | tokens per model | cost per successful task per role | folder 19 |
| Spend control | an alert nobody reads at 04:00 | top-3 jobs paused once a day, resumed on schedule | folder 19 |
| Harness edits | no gate | 19 deterministic probes, regression ⇒ rejected | folder 18 |
| Routing | habit | measured tier per job, cost-raising repins refused | folder 22 |

Example report from folder 19 (shape, not a benchmark — one week, one deployment):

```
media   ok 34/41  $1.86  →  $0.055 per success
mail    ok 28/28  $1.15  →  $0.041 per success
infra   ok 96/99  $0.90  →  $0.009 per success
```

## Reliability

| Metric | Value | How measured |
|---|---|---|
| Runs ending in an error | 7.6% | usage ledger, 393 runs |
| Harness probes | 19 passing, regression ⇒ change rejected | folder 18, run hourly |
| Harness files under a sha256 manifest | 19 | integrity check; it caught a self-inflicted edit within a day |
| Failures that repeated daily without being classified | 0 after the classifier shipped | folder 20, one journal entry per new failure |
| Blind-spot audit | weekly sample of 12 accepted outputs | folder 21; the audit exists because the ledger cannot see this number |

## Economics of reasoning

| Metric | Value | How measured |
|---|---|---|
| Cost per day, all jobs | $1.46 | provider billing joined to the ledger, 708 calls/day |
| Share spent on context compression | $0.34/day (23%) | tagged compression calls |
| Cache reads per write | ×33.5 | billed cache reads vs. writes |
| Jobs that need no model at all | 42 of 68 (62%) | job list: deterministic script vs. model call |

The last row is the maturity metric I watch: the share of scheduled work that is a script. It only
moves in one direction if each new job starts as a collector and earns its model call.

## Research intake

| Metric | Value | How measured |
|---|---|---|
| Query API availability | rate-limited even for a one-term query, from two different networks | direct requests, same client, two egress paths |
| OAI-PMH yield | cs.AI 1 696 records/week, cs.CL 904/week | folder 23, ListRecords walk |
| Corpus used for direction counting | 10 781 records over 5 weekly windows | local JSONL, equal windows |
| Term shares | flat except cost/tokens, 15.6% → 16.9% | share per window; shares travel with the record count |
| Journal | 17 entries: 9 adopted, 2 in progress, 4 queued, 2 rejected | each rejection with a reason |

## Reading these numbers

- Ratios, not absolutes. The deployments behind them differ in size; the transferable part is the
  direction of each column.
- Every figure has a window. A percentage without one is a mood.
- The comparisons that survived review are the interesting ones: a model swap that was cheaper per
  token but dearer per task, a "newer" model that raised the price of mechanical work by 2.3–3.3×,
  and a rate-limit problem that was not about the IP address. All three are in the modules as rules,
  not as anecdotes.
