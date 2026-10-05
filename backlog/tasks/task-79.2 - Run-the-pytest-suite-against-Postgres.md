---
id: TASK-79.2
title: Run the pytest suite against Postgres
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - testing
  - data
milestone: m-0
dependencies:
  - TASK-79.1
parent_task_id: TASK-79
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Parametrise the DB URL in tests/conftest.py so the suite runs on SQLite (default) and Postgres (env var); add a Postgres service for local runs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Full suite green on both SQLite and Postgres
<!-- AC:END -->
