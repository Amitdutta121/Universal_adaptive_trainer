---
id: TASK-80
title: Make Alembic the only schema source (drop create_all at startup)
status: In Progress
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:46'
labels:
  - data
  - backend
milestone: m-0
dependencies: []
priority: medium
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
init_db runs create_all + alembic upgrade + create_all again at startup, so tables can exist that no migration creates. That drift is what would make a later move to Postgres painful.
Evidence: app/persistence/database.py:111-127; app/main.py:34
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create_all removed from startup; alembic upgrade head is the only way the schema is built
- [ ] #2 alembic check reports no drift between models and migrations
<!-- AC:END -->
