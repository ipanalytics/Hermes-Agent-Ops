# Roadmap

1. **v0.1 — skeleton lands.** This structure, English docs, sanitized examples. Each folder's README is the pitch. ✅
2. **v0.2 — real code.** 01–02 ship working sanitized artifacts; 03 incidents + decision trees; 04 templates; 05 briefs; 06 skill + recipes. ✅
3. **v0.3 — the series continues.** New working tools: 07 fresh-prompt linter, 09 ops-as-data exporter, 10 cost dashboard; pattern packs 08, 11, 12, 13; `SERIES.md` maps how folders extend each other. ✅
4. **v0.3.1 — operations hardening.** `02` rebuilt on systemd (units + polkit grant + update flow, no cron guard); `14-agent-data-intake` ships; "alert noise budget" policy in `05`; new autopsy `auto-update-restart-chain` in `03`. ✅
5. **v0.4 — tests & CI.** Python tools (01, 02, 07, 09, 10, 14) get test suites; linter + exporter wired into a GitHub Action that self-checks this repo's own prompts and watch-table.
6. **v0.5 — live demo data.** Anonymized sample usage DB + generated sample dashboard committed, so the README claims are visible without running anything.
7. **v0.6 — community.** First external contributions: new persona packs, new cron recipes, new incident autopsies (attributed or anonymized).
