# Series map — how the folders continue each other

The numbered folders are one evolving story, not islands: new ideas extend old
ones. The incident autopsies in `03` explain why most other folders exist.

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

## How a newcomer should read it

1. **Start at 03** — the incidents (10 minutes) explain why every other folder exists.
2. **Grab 04 + 11** to stand up their own roles.
3. **Deploy 01 + 10** before trusting any of it with real money.
4. **Ship every cron prompt through 07** and generate docs with 09.
5. **Watch it all** with 05, and let 02/06 keep the services alive.

## Contribution shape

Each folder owns its README pitch + artifacts. A PR that touches a folder should
update the map row. Folders with code (01, 02, 07, 09, 10) get tests before the
docs do — the code is the proof, the README is the promise.
