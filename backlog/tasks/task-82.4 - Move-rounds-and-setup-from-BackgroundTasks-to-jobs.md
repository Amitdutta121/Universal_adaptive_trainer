---
id: TASK-82.4
title: Move rounds and setup from BackgroundTasks to jobs
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
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evidence: app/web/routes/api/rounds.py:56; app/web/routes/api/setup.py:119 (FastAPI BackgroundTasks, lost on restart).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Killing the backend mid-round and restarting resumes or cleanly fails the round
<!-- AC:END -->
