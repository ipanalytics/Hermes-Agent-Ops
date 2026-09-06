# Incident: the gateway that was alive but dead

**Class:** state-DB sidecar race ("deleted WAL")
**Severity:** full outage — bot silent in every chat, LLM cron jobs failing, process healthy

## Symptom
- Bot stopped answering. `ps` showed the gateway alive, heartbeat file fresh.
- User messages were not entering history — they piled up in a pending-messages directory.
- Cron LLM jobs failed; a live process held a *deleted* `state.db-wal`/`state.db-shm` inode.

## Evidence
- Log line: `FATAL: a live process holds a deleted state.db-wal or state.db-shm inode ... Refusing to open or write so a second WAL cannot be minted. Stop the gateway, dashboard, and cron writers`.
- This is a **split-brain guard**: the sidecar files were removed/recreated while a holder still had them open. Every NEW connection to the DB was refused (old holder kept writing into the deleted WAL → index corruption risk, e.g. broken delivery obligations).
- The corruption is *not* caused by updates — an update only *surfaces* it via its integrity check.

## Fix
1. **Quarantine** the damaged DB to a recovery dir (do not delete).
2. **Restore** from the most recent clean daily backup taken *before* the failure window.
3. Restart the gateway; run `integrity_check`.
4. Loss window = backup → restart (bounded, small).

## Why not "just run the update"
The update does not fix this class — it fails its snapshot integrity check and reports that "the source was already corrupted before the backup". Restore, don't patch.

## Prevention
- External supervisor watching for fresh `deleted ... .db-wal` FATALs in log tails and restarting on the *documented* recovery path (`02-agent-gateway-supervisor`).
- Daily consistent DB backups (sqlite online backup), kept ~1–2 days.
- If failures persist after restarts: escalate to a human "restore needed" — never auto-restore from a robot.

## Lesson
A healthy-looking process is not a healthy system. Watch the heartbeat *and* the fatal-marker log tail.
