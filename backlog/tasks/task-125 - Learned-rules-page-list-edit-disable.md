---
id: TASK-125
title: 'Learned rules page: list, edit, disable'
status: To Do
assignee: []
created_date: '2026-10-05 17:35'
labels:
  - e2e-gap
  - frontend
milestone: m-9
dependencies: []
priority: medium
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Judges screen only shows a rule count (frontend/src/app/courses/[courseId]/judges/judges-screen.tsx:105). Backend delete exists (app/web/routes/api/instructions.py:95) and a hook exists (frontend/src/lib/api/queries.ts:992) but no page uses it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 List rules with the reviews that produced them
- [ ] #2 Edit and disable a rule
<!-- AC:END -->
