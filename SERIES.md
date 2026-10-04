# Series map — how the folders continue each other

_Русская версия: [SERIES.ru.md](SERIES.ru.md)_

New modules extend old ones; the table below records which builds on which. The incident
autopsies in `03` are the reason most of the other folders exist.

## The threads

| # | Folder | Continues / is continued by |
|---|---|---|
| 01 | | agent-wallet-guard (alerts on burn) | → **10** cost-dashboard (shows *where* the burn went) |
| 02 | | gateway-supervisor (heals the gateway) | fed by watchdog recipes in **06**; escalation path documented in **03** incidents |
| 03 | | agent-ops-playbook (the scar tissue) | **07** linter prevents one class of its incidents; **13** documents another (voice); decision-trees.md is the shared brain |
| 04 | | role-profiles (the engine) | **11** persona-packs are the cartridges for this engine; **12** adds the topic walls |
| 05 | | cron-of-crons (who watches whom) | **09** ops-as-data generates its watch-table from the job list |
| 06 | | hermes-plugins-skills (packaging) | **08** session-housekeeping ships as skills too |
| 07 | | fresh-prompt-linter | guards every agent-job prompt before it reaches 05's schedules |
| 08 | | session-housekeeping | the lifecycle that prevents 03's "530K-token session" incident |
| 09 | | ops-as-data | keeps 05's documentation true |
| 10 | | cost-dashboard | makes 01's alerts explainable |
| 11 | | domain-persona-packs | the reason to use 04 |
| 12 | | topic-routing | the walls that make 04's multi-role safe |
| 13 | | voice-input-hypotheses | the agent-side fix for a whole class of 03 mistakes |
| 14 | | agent-data-intake | 02's unit pattern applied to peripheral receivers; 03's intake incident explained; the spool contract every device-side sender should ship |
| 15 | | agent-tool-guardrails | **02**'s outside-judgement stance turned on commands and worktrees; guards what **07**-approved prompts actually do; the lane half pairs with Hermes' own worktree isolation |
| 16 | | gepa-skill-tuner | the repair loop after **07**: the linter blocks a bad prompt, the tuner rewrites one against labelled traffic; its task sets are exactly what **15**'s gates and **03**'s incidents produce |
| 17 | | model-slot-bakeoff | the measurement step behind **04**'s model pinning: a slot is worth what its tasks cost per call, and **16**'s optimization runs inherit that choice |
| 18 | | harness-probes | the gate **15**'s lanes and **16**'s tuner need: an edit is admitted only when the probe baseline shows no regression; **20** supplies the runtime twin of the same idea |
| 19 | | cost-governance | the teeth **01** and **10** describe but do not carry — a cap that pauses and resumes — plus the per-outcome number **22** optimizes against |
| 20 | | task-evals-and-autopsy | **05**'s sweep brief fed by evidence: output checks, an error classifier and a compiled brief; **18** checks the harness, this checks the work |
| 21 | | blind-spot-audit | the measurement **07**, **15** and **18** cannot make for themselves: what their gates let through |
| 22 | | difficulty-router | **17**'s slot measurement applied continuously to every scheduled job, with a refusal rule |
| 23 | | research-intake | why **16** and **21** change at all: equal-window corpus counting and a journal that keeps adoptions and rejections with reasons |
| 24 | | llm-to-script | the cost lever behind **19**'s budget: the same artifacts produced without a model in the loop, with the shortlist tool that finds the next candidate |
| 25 | | querylog-domain-scout | → what **15** looks like on the wire: per-device domains from AdGuard logs |
| 26 | | ecosystem-map | → the picture **09** describes, rebuilt live on every run |
| 27 | | research-scout | → feeds **23** — arXiv OAI-PMH with a change gate and a stable fingerprint |
| 28 | | digest-delivery-health | → watches **05/10** — silence, failures and drift across digests |
| 29 | | thinking-layer-cost | → the reasoning half of **19** — spend per day against a cap |
| 30 | | schedule-audit | → when the jobs from **05** fire, and what belongs in the night |
| 31 | | compaction-effect-check | → before/after numbers for a context policy change |
| 32 | | routing-outcomes | → closes the loop for **22** — which tier actually succeeded |
| 33 | | multi-model-consilium | → feeds **17** and **32**: a second model's attack on a plan, and the author's answer to it, on one record |
| 34 | | skill-library-janitor | → the library-wide counterpart of **15**'s pre-write scanner: broken paths, dead scripts, drifted frontmatter |
| 35 | | context-compaction-engine | → the engine **31** measures: compaction by working state, carried across cycles without asking the model to re-summarise it; the 530K-token incident in **03** is the case it was built for, and **08** owns the lifecycle it compacts inside |

## Where to start

Read **03** first. Ten minutes of incident autopsies, and every other folder suddenly has a reason to
exist — it is the least interesting reading in the repository and the reason the rest of it holds
together.

After that, the order is set by consequence rather than convenience. Stand up your own roles (**04**, with
a persona pack from **11**), then put the money guard in place (**01** and **10**) before any of it is
trusted with real money. Every scheduled prompt goes through the linter (**07**) and the documentation is
generated (**09**) so it cannot drift from what actually runs; **05** watches the schedule while **02** and
**06** keep the services alive.

The later folders are the ones that pay for themselves once it has been running for a while: **18** gates
the harness, **19** caps the spend, **20** checks whether the work actually happened, **21** measures what
the gates miss, **22** routes jobs to the tier they deserve, and **24** removes the cost that never needed
a model in the first place.

## Working in this repository

Each folder owns its README and its artifacts, and a change inside a folder updates that folder's row in
the map above. New code arrives with a test that exercises it, and the README lists the files that are
really there — not the ones that were planned.
