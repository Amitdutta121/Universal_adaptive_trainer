---
id: TASK-82
title: Durable job queue for LLM generation
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - llm
  - backend
  - needs-decision
milestone: m-3
dependencies: []
priority: high
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Coverage generation loops gaps sequentially inside the HTTP request (~2 min); targets unbounded; running-state is a process-local set. /questions/generate, /generate-batch, /regenerate, /curriculum/drafts are also synchronous. Rounds use in-process BackgroundTasks, so a restart loses work.
Evidence: app/web/routes/api/coverage.py:84-85,117-247; app/web/routes/api/schemas.py:2028; app/web/routes/api/questions.py:120-227; app/web/routes/api/curriculum.py:113; app/web/routes/api/rounds.py:56; app/web/routes/api/setup.py:119
Decision (needs confirm): arq (async, Redis-backed, small) plus a Redis container; a job row in the DB is the source of truth for status. Alternative: Procrastinate (Postgres-backed, no Redis), but only after task-79 because it cannot run on SQLite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Generation endpoints return a job id; UI polls status
- [ ] #2 Jobs survive restart and work with >1 worker
- [ ] #3 Upper bound on targets per run
<!-- AC:END -->
