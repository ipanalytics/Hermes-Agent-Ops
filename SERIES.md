# Series map — how the folders continue each other

New modules extend old ones; the table below records which builds on which. The incident
autopsies in `03` are the reason most of the other folders exist.

## The threads

| # | Folder | Continues / is continued by |
|---|---|---|
| 01 | agent-wallet-guard (alerts on burn) | → **10** cost-dashboard (shows *where* the burn went) |
| 02 | gateway-supervisor (heals the gateway) | fed by watchdog recipes in **06**; escalation path documented in **03** incidents |
| 03 | agent-ops-playbook (the scar tissue) | **07** linter prevents one class of its incidents; **13** documents another (voice); decision-trees.md is the shared brain |
| 04 | role-profiles (the engine) | **11** persona-packs are the cartridges for this engine; **12** adds the topic walls |
| 05 | cron-of-crons (who watches whom) | **09** ops-as-data generates its watch-table from the job list |
| 06 | hermes-plugins-skills (packaging) | **08** session-housekeeping ships as skills too |
| 07 | fresh-prompt-linter | guards every agent-job prompt before it reaches 05's schedules |
| 08 | session-housekeeping | the lifecycle that prevents 03's "530K-token session" incident |
| 09 | ops-as-data | keeps 05's documentation true |
| 10 | cost-dashboard | makes 01's alerts explainable |
| 11 | domain-persona-packs | the reason to use 04 |
| 12 | topic-routing | the walls that make 04's multi-role safe |
| 13 | voice-input-hypotheses | the agent-side fix for a whole class of 03 mistakes |
| 14 | agent-data-intake | 02's unit pattern applied to peripheral receivers; 03's intake incident explained; the spool contract every device-side sender should ship |
| 15 | agent-tool-guardrails | **02**'s outside-judgement stance turned on commands and worktrees; guards what **07**-approved prompts actually do; the lane half pairs with Hermes' own worktree isolation |
| 16 | gepa-skill-tuner | the repair loop after **07**: the linter blocks a bad prompt, the tuner rewrites one against labelled traffic; its task sets are exactly what **15**'s gates and **03**'s incidents produce |
| 17 | model-slot-bakeoff | the measurement step behind **04**'s model pinning: a slot is worth what its tasks cost per call, and **16**'s optimization runs inherit that choice |

## Reading order

1. **Start at 03** — the incidents (10 minutes) explain why every other folder exists.
2. **Grab 04 + 11** to stand up their own roles.
3. **Deploy 01 + 10** before trusting any of it with real money.
4. **Ship every cron prompt through 07** and generate docs with 09.
5. **Watch it all** with 05, and let 02/06 keep the services alive.

## Contribution rules

Each folder owns its README and its artifacts. A PR that touches a folder updates the map
row. New code ships with a test that exercises it, and the README lists the real files.
