---
id: TASK-82.2
title: Move coverage generation onto jobs
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - backend
  - llm
milestone: m-3
dependencies:
  - TASK-82.1
parent_task_id: TASK-82
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evidence: app/web/routes/api/coverage.py:84-85,117-247 (sequential loop in the request, process-local running set); app/web/routes/api/schemas.py:2028 (unbounded targets).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 POST /api/coverage/generation-runs returns a job id in under 1s
- [ ] #2 Targets per run are capped
- [ ] #3 The process-local running set is gone
<!-- AC:END -->
