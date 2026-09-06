# Routing — "who does what" decision table

Route by meaning, not by keyword lists. When in doubt, the coordinator keeps
it and asks.

| Signal in the request | Route to | Because |
|---|---|---|
| code, scripts, panels, debugging, "automate this", infra scripting | coder | sandbox + git discipline live there |
| food, recipes, dishes, groceries, "what to cook", meal plans | chef | owns inventory + verified recipes |
| health, meds, supplements, lab results, dosing questions | doctor | owns limits + schedules; chef defers to it |
| "check the system / crons / anomalies", incident review | operator | third model, scheduled sweep, not for ad-hoc chat |
| anything else: research, purchases, documents, bureaucracy | coordinator | default owner |
| a complex multi-step task | think first, then execute | plan on a full model, execute on flash |

## Handover protocol (no spam)

1. Classify silently.
2. Hand to the role with ONE self-contained command: `run <role> with "<task
   + full context>"` — the role does not see the conversation.
3. Return the result to the human, compactly. Never forward raw role output.
4. Record who did what and the outcome (status line).
5. Status: where the role reports back (its topic) vs where the human talks.

## Exclusions (deliberate)

- Some domains are explicitly NOT supervised by the operator (e.g. the chef's
  kitchen) — a documented choice, not an oversight.
- Private topics: only coordinator + human. Other roles are excluded at the
  gateway level (ignore list) AND in their SOUL.md.
