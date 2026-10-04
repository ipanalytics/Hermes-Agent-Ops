# 12 — topic-routing

_Russian version: [README.ru.md](README.ru.md)_

A whole multi-agent system in one chat app: Telegram topics as domains, ignore-lists as walls, the DM as the front desk.

## What this folder is, and the words it uses

Before the rest makes sense, a short glossary. The rest of the README and the rest of the project use these terms, and I do not want a first-time reader to bounce off them.

- **Hermes** is the name of my home AI agent. It runs on a server I own, talks to me through Telegram, schedules its own jobs and runs dozens of scheduled digests that produce messages and files every hour, every morning, every week.
- A **model** is the program that actually answers — the LLM (large language model). When a role in Hermes answers, it is a model answering.
- A **provider** is the company that serves the model over an API. Model and provider are not the same thing: each provider has its own account, its own rate limits and its own billing. When I say "I changed the provider", I mean the billing counter, not the brain.
- A **token** is the unit the provider charges and the unit the model has a budget for. Roughly, a token is a piece of a word. Tokens matter for cost and for ceilings; this folder does not touch either, but every other folder does.
- A **session** is one ongoing conversation between me and Hermes: a system prompt, then a back-and-forth of user and assistant turns. Sessions are the unit of context, and they live in the Hermes database.
- A **cron** (or "scheduled job") is a job that fires unattended at a fixed time. Daily digests, hourly checks, overnight sweeps — they all live in the same scheduler. This folder is the address book those jobs deliver into.
- A **role** is a slice of the agent with its own system prompt, its own tools, its own rules and its own memory. A role is what answers when a topic gets a message. Several roles can run inside the same Hermes process.
- A **profile** is the recorded description of a role: who it is, what it knows, what it does not talk about, which topics exist in its world. Profiles are the file `04-role-profiles` works with.

And the Telegram-side words, which is what this folder actually uses:

- A **group** is one Telegram supergroup. Hermes runs as one bot inside one supergroup, and the whole multi-agent system lives inside that single group. There is not a separate bot per role.
- A **topic** is a thread inside that supergroup. Telegram opened forum-style threads in groups a few years ago, and each topic has its own message id space. To a role, a topic looks like an independent channel — but it is just a sub-stream inside the same group.
- A **DM** is a private chat between me and the bot, separate from the supergroup. The DM is where the bot and I actually talk; the supergroup is where roles publish to their own audiences.
- An **ignore list** is a per-role list of topics the gateway refuses to route to that role. A role literally cannot see a topic that is on its ignore list — the gateway drops the message before it reaches the model. That is the wall.
- The **gateway** is the small piece of code in front of the model that picks which role gets which message. The gateway is mechanical: it does not ask the model whether the message is for it, it just checks the role's profile and the topic id.

So: many roles, one Telegram supergroup, each role wired to its own topic, walls enforced by ignore lists, the DM kept private for the things that need me now.

## Why I wrote it

When Hermes was a single bot talking to me in a single chat, routing was simple: every message was for me and every message was from me. When I added the second role, the third, and a couple of dozen cron digests that have to land somewhere, three things broke in order:

1. **Two roles answered the same question.** A health digest and a kitchen digest both read the morning "what should I cook today" question and both answered. None of them was wrong; both of them were off-topic.
2. **A cron delivered into the wrong topic.** The morning commute digest landed in the kitchen topic because the job's delivery destination was set to the default group, and the kitchen topic was the most recently created thread. The kitchen role tried to digest the commute, and the commute role never saw the report.
3. **An alert I needed now sat in a topic I was not reading.** The wallet guard tripped at 03:00, wrote a careful report into the ops topic, and the topic was quiet enough that I did not open Telegram until 08:00 — five hours and a non-trivial bill later.

Each of those failures had the same root: the routing was a behavioural property of the model. The model was being asked "is this message for you?" and the model was answering differently on different days. Routing has to be a property of the *gateway*, not a property of the model, because the gateway is the only thing that knows the address and never gets tired.

## What this folder gives me

| Concept | Telegram mechanism | Why it works |
|---|---|---|
| Domain isolation | topic per domain (commutes, releases, health, kitchen, alerts, ops) | delivery is addressable per topic; I read what I want, when I want, and never see the rest unless I open it |
| Walls | gateway-level ignore list per role profile | a role literally cannot see the private topic — the enforcement is mechanical, not behavioural |
| Front desk | the DM / main topic | I talk to ONE bot; routing is internal (see `04/docs/routing.md`) |
| Ops channel | a topic nobody reads by default | supervisors, guards and sweep reports go here; alerts that matter ALSO hit the DM |
| One-shot reminders | DM, fixed text, self-disable | zero context, zero tokens, impossible to miss |

The mapping is the whole architecture. Five Telegram mechanisms carry five things the rest of the system relies on.

## The pattern

- **One bot, one supergroup, many topics.** I do not run a separate bot per role. Running five bots would multiply the bills, multiply the auth tokens and give me five things that could go down. One bot, one group, many threads — that is enough.
- **Roles live in their own topic and ignore everything else.** A role's "world" is a list of topics. Anything outside that list is not delivered to it; the gateway drops it before it reaches the prompt.
- **The DM is for me.** Private chat is the only place the human (me) and the bot have a real conversation. Roles report to their topics; the coordinator reports to the DM.
- **The ops topic is for machines.** Guard reports, sweep logs, scheduler health — anything that exists for a future "I will need this when something breaks" goes to the ops topic, and nothing else. Nobody reads it on a good day.
- **Alerts break the topic rule.** Anything that needs me right now — balance floor, supervisor escalation, watchdog restart — also lands in the DM. Topics are for reading habits; the DM is for attention.

## The rules that make it stick

1. **Delivery origin is a fact of the job record, not an assumption.** I check where a job actually delivers before blaming "the bot". A cron job's `report_topic` field is part of its declaration, and the gateway reads that field at delivery time, not at job creation. I caught one misroute that way — a job whose `report_topic` had been silently overwritten by a stale config import, sending health alerts into the kitchen topic for three days before anyone noticed.
2. **Roles report to their topic; the coordinator reports to me.** A role's raw output never lands in the DM by default. The coordinator is the one role that is allowed to speak to me directly, and only when something has crossed a threshold the topic cannot answer.
3. **Private topics exist only in the coordinator's world.** Every other role keeps them in the ignore list AND in its SOUL boundaries. SOUL is the role's persistent self — the prompt that says "you are X, you do not handle Y". Walls on the prompt AND on the gateway, not just one or the other. Either wall alone is enough to leak: the gateway wall stops delivery, but the prompt wall stops the model from trying to answer when a message does slip through (manual mentions, misconfigured @-replies).
4. **Alerts are the exception to the topic rule.** Anything that needs me *now* (balance floor, supervisor escalation, watchdog restart) goes to the DM, and not only to the ops topic. The point is that the DM is the one place Telegram notifies me on, regardless of whether I am reading topics.
5. **Thread hygiene.** Digests dedupe via continuity, so a topic that was quiet all week stays quiet — silence is a feature (see `05/delivery-policy.md`). A topic that pings me daily is a topic I have stopped opening; a topic that pings only when something is genuinely new is a topic I still trust.

These five rules are short. Each one is the post-mortem of a failure I lived through.

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

The wall is in `ignore_topics`, the inbox is in `report_topic`. Two lines per role, both checked by the gateway. The role itself never sees a message outside its world, so the prompt for that role does not have to argue with itself about whether to answer.

For me — the human — the corresponding config is in `04-role-profiles/docs/routing.md`: a list of which topics I read on which cadence, and which ones I open only on alert. Topics that do not appear on my list are not bad topics; they are just not for me.

## How I deploy it

The pattern is configuration, not code, so deployment is the same as for every other config in Hermes:

```bash
# 1. Make sure the Telegram supergroup has forum topics enabled and the bot is admin
# 2. Create the topics (one Telegram action per topic; the topic ids go into the config)
# 3. Drop the role profiles next to the existing ones
cp examples/profile.tmpl ~/.hermes/roles/chef.yaml
cp examples/profile.tmpl ~/.hermes/roles/operator.yaml

# 4. Wire the gateway to read the role list at startup
hermes config set gateway.roles_path ~/.hermes/roles
hermes restart
```

Three things are easy to forget:

- The bot has to be **admin** in the supergroup with rights to post in topics and to read the topic id of an incoming message. Without the admin rights, the gateway sees the message but cannot route it because it does not know which topic the message came from.
- The topic ids in the config have to be the **internal** Telegram ids, not the visible thread names. Telegram changes the thread name when I rename a topic; the id is stable. Mismatched ids are the most common cause of "the bot stopped talking to me" reports.
- The role's `ignore_topics` and its `report_topic` should be **mutually consistent**: if a topic is in `ignore_topics`, it must NOT be `report_topic`. The gateway does not enforce this — it is the configuration author's job — but the failure mode is silent: the role sees its own outgoing message arrive as if from a peer, and replies to itself.

## How a misroute would actually look

A concrete walk-through of the failure mode this pattern prevents, in case the rules above sound abstract:

1. The wallet guard fires at 03:00 and decides the daily cap has been crossed.
2. The guard's `report_topic` is `ops`. The wallet-guard role's `ignore_topics` does NOT include `ops`, so the guard is allowed to write to the ops topic. Good.
3. The guard's `escalation_dm` flag is `true`. The same alert ALSO lands in the DM. Good.
4. At 08:00 I read the DM, see the alert, and open the ops topic only if I need the history.
5. If `escalation_dm` had been `false` — or if the guard's role had been added to `ignore_topics` by mistake — the alert would have sat in the ops topic alone. The gateway would have delivered it, the guard would have written a careful report, and I would have missed it because nobody reads the ops topic on a good day.

The misroute is silent. There is no error, no log line louder than "delivered to ops topic", no alert. The pattern works because the rules prevent the silent failure modes, not because the rules are clever.

## What this folder does not cover

- **Telegram-side rate limits.** The bot is still one bot, and Telegram still rate-limits it. A topic that gets hit too fast will hit Telegram's per-chat limits regardless of how the routing is configured. The cap is documented in `08-session-housekeeping`.
- **Cross-topic state.** A role that needs to remember something it saw in another role's topic has to go through the coordinator. The pattern does not give roles a way to read each other's topics directly — that is the whole point of the walls.
- **Spam and abuse.** The ignore list is for *legitimate* role separation, not for blocking users. For that, Telegram's own bot permissions are the right tool. The two layers cooperate; the topic pattern is not a substitute.
- **Migration of an existing setup.** If there is already a bot per role, the migration to one bot with topics is not in this folder — it is an operational decision that depends on the topics that already exist in the supergroup.

## Limitations

- Telegram-specific. The pattern relies on Telegram's forum topics, which are a Telegram feature. Other chat platforms with similar primitives (Slack threads, Discord channels) would map differently, and the config snippets would not transfer without changes.
- Single-supergroup assumption. The whole architecture assumes one bot, one supergroup, many topics. Splitting into multiple supergroups works against the pattern, because the gateway becomes responsible for cross-group routing and the DM-as-front-desk story stops holding.
- The DM is not a queue. The DM is a place I read; it is not a structured inbox. Putting structured workflows there (queues, ack lists, retries) is a misuse of the front desk, and it tends to fail in the same way every queue does: the front desk grows until I stop reading it.
- Ignore lists are not ACLs. A role that wants to mention a topic outside its world can still mention it in a message it sends *to its own topic* — the wall stops incoming messages, not outgoing references. For that, the prompt (SOUL) is the second wall.
- "Nobody reads it" is a feature until it is not. The ops topic being quiet is a feature on a healthy day. It is a liability when something goes wrong and I forget the topic exists. The discipline is to keep at least one alert path going through the DM, so the ops topic can never be the only place a problem shows up.

## License

MIT License — see the `LICENSE` file in the repository for details.