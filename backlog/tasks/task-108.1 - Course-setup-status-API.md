---
id: TASK-108.1
title: Course setup-status API
status: To Do
assignee: []
created_date: '2026-10-05 17:40'
labels:
  - backend
milestone: m-8
dependencies: []
parent_task_id: TASK-108
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GET /api/courses/{id}/setup-status returning each step (material, taxonomy, generate, review, freeze, share) with done/remaining counts, reusing existing coverage and review queries. Course routes: app/web/routes/api/courses.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Returns correct step states for an empty course and a fully set up course (tests)
<!-- AC:END -->
