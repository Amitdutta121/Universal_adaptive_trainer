---
id: TASK-82.1
title: 'Job infrastructure: jobs table, worker process, status API'
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - backend
  - llm
milestone: m-3
dependencies: []
parent_task_id: TASK-82
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a jobs table (Alembic revision), the worker (per the task-82 decision), a worker service in docker-compose.yml, and GET /api/jobs/{id} returning status, progress, result, error.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A dummy job enqueued from a test runs in the worker and its status moves queued -> running -> done
- [ ] #2 A failed job records its error and can be retried
<!-- AC:END -->
