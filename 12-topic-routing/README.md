# 12 — topic-routing

**A whole multi-agent system in one chat app: Telegram topics as domains, ignore-lists as walls, the DM as the front desk.**

> We run several roles and dozens of cron digests in a single group where every
> domain gets its own topic. The human gets one bot to talk to; the roles get
> isolation; nothing leaks across walls. This folder is the reference architecture.

## The mapping

| Concept | Telegram mechanism | Why it works |
|---|---|---|
| Domain isolation | topic per domain (commutes, releases, health, kitchen, alerts, ops) | delivery is addressable per topic; the human reads what they want when they want |
| Walls | gateway-level ignore list per role profile | a role literally cannot see the private topic — enforcement is mechanical, not behavioral |
| Front desk | the DM / main topic | the human talks to ONE bot; routing is internal (see `04/docs/routing.md`) |
| Ops channel | a topic nobody reads by default | supervisors, guards, sweep reports go here; alerts that matter ALSO hit the DM |
| One-shot reminders | DM, fixed text, self-disable | zero context, zero tokens, impossible to miss |

## Rules that make it stick

1. **Delivery origin is a fact of the job record**, not an assumption — check where
   a job delivers before blaming "the bot".
2. **Roles report to their topic; the coordinator reports to the human.** A role's raw
   output never lands in the DM by default.
3. **Private topics exist only in the coordinator's world** — every other role has them
   in the ignore list AND in its SOUL boundaries.
4. **Alerts are the exception to the topic rule**: anything that needs a human *now*
   (balance floor, supervisor escalation, watchdog restart) goes to the DM, not only
   to the ops topic. Topics are for reading habits; the DM is for attention.
5. **Thread hygiene**: digests dedupe via continuity, so a topic that was quiet all week
   stays quiet — silence is a feature (see `05/delivery-policy.md`).

## Config snippets (example)

```yaml
# per role: which topics exist in its world
role: chef
ignore_topics: [private, ops, medicine]   # walls are mechanical
report_topic: kitchen

role: operator
ignore_topics: [private, kitchen]
report_topic: ops
```
