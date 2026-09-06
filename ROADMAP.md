# Roadmap (draft)

1. **v0.1 — skeleton lands.** This structure, English docs, sanitized examples. Each folder's README is the pitch.
2. **v0.2 — first working tool.** `01 agent-wallet-guard` extracted, genericized (any OpenAI-compatible provider), with config + tests + a demo incident.
3. **v0.3 — supervisor + guard** genericized with install script.
4. **v0.4 — playbook content**: first 3–4 sanitized incident autopsies + decision trees.
5. **v0.5 — templates**: role-profiles skeleton + cron recipes; plugins/skills packaging; upstream PRs.

## Open questions for the owner

- One monorepo (this layout) vs splitting tools later — see top-level README rationale.
- Which incidents to publish first (most relatable > most severe).
- Naming: `hermes-agent-ops` vs alternatives.
- License final pick (MIT code + CC-BY-4.0 docs assumed).
