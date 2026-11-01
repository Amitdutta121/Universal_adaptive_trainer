---
id: TASK-82.3
title: Move question and curriculum generation onto jobs
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
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evidence: app/web/routes/api/questions.py:120-227 (/generate, /generate-batch, /regenerate); app/web/routes/api/curriculum.py:113 (/curriculum/drafts).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the four endpoints returns a job id
<!-- AC:END -->
