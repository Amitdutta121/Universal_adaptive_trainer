---
id: TASK-79
title: Move to Postgres for production
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - data
  - backend
  - infra
  - needs-decision
milestone: m-0
dependencies: []
priority: high
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
SQLite is the only real DB (app/config.py:66, docker-compose.yml:10); no WAL/busy_timeout; sync+async engines on same file -> lock errors under background rounds. No psycopg dependency. Roadmap F1 says Postgres.
Evidence: app/persistence/async_database.py; pyproject.toml
Decision (needs confirm): Postgres 16 as a container in the prod compose on the same VM, nightly pg_dump to off-box storage (task-81). Alternative: managed Postgres (Neon, Supabase, RDS) if hosting moves off a single VM.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Postgres service in compose; alembic upgrade head passes on Postgres
- [ ] #2 Full pytest suite passes against Postgres
<!-- AC:END -->
