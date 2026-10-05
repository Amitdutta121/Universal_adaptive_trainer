---
id: TASK-79.1
title: Run Alembic migrations and the app on Postgres
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - backend
  - data
milestone: m-0
dependencies: []
parent_task_id: TASK-79
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add the psycopg dependency in pyproject.toml; fix SQLite-only SQL in migrations (app/persistence/migrations/versions/) and app/persistence/database.py, app/persistence/async_database.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 alembic upgrade head succeeds on an empty Postgres 16
- [ ] #2 App boots against Postgres and /api/health is ok
<!-- AC:END -->
