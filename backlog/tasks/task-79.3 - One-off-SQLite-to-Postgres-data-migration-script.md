---
id: TASK-79.3
title: One-off SQLite to Postgres data migration script
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - data
milestone: m-0
dependencies:
  - TASK-79.1
parent_task_id: TASK-79
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Script in scripts/ that copies data/adaptive_trainer.db into Postgres, preserving ids and resetting sequences.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Row counts match per table after migrating a copy of the real DB
- [ ] #2 App works against the migrated DB
<!-- AC:END -->
