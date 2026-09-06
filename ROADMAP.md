# Roadmap (draft)

1. **v0.1 — skeleton lands.** This structure, English docs, sanitized examples. Each folder's README is the pitch. ✅
2. **v0.2 — real code.** 01–02 ship working sanitized artifacts; 03 incidents + decision trees; 04 templates; 05 briefs; 06 skill + recipes. ✅
3. **v0.3 — the series continues.** New working tools: 07 fresh-prompt linter, 09 ops-as-data exporter, 10 cost dashboard; pattern packs 08, 11, 12, 13; `SERIES.md` maps how folders extend each other. ✅
4. **v0.4 — tests & CI.** Python tools (01, 02, 07, 09, 10) get test suites; linter + exporter wired into a GitHub Action that self-checks this repo's own prompts and watch-table.
5. **v0.5 — live demo data.** Anonymized sample usage DB + generated sample dashboard committed, so the README claims are visible without running anything.
6. **v0.6 — community.** First external contributions: new persona packs, new cron recipes, new incident autopsies (attributed or anonymized).

## Open questions for the owner

- One monorepo (this layout) vs splitting tools later — see top-level README rationale.
- Which incidents to publish next (most relatable > most severe).
- Naming: `hermes-agent-ops` vs alternatives.
- License final pick (MIT code + CC-BY-4.0 docs assumed).
