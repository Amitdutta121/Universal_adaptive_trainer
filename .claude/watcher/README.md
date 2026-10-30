# Watcher

Passive cross-session reviewer. Runs every 20 min: cron `3fb9a7cd` in the main session spawns a throwaway general-purpose subagent per tick (keeps the main context small).

- `collect.sh` — read-only signal gatherer -> `snapshot.txt`
- `blame-sessions.sh <file>...` — which Claude session(s) edited a file (last 24h), with task labels
- `self-session-id` — this watcher session's id (update if the watcher restarts in a new session)
- `PROCEDURE.md` — what the loop does each tick
- `report.md` — current state (overwritten each tick) — **read this**
- `log.md` — one line per tick

It never edits source or runs git-write commands. Findings only.
Every conflict/hotspot is attributed to the sessions that caused it.
