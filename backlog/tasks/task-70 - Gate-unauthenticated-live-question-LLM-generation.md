---
id: TASK-70
title: Gate unauthenticated live-question LLM generation
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - llm
  - backend
milestone: m-4
dependencies: []
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Student /live-question triggers paid LLM generation with no auth: cost-abuse path.
Evidence: app/web/routes/api/students.py:560
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Requires authenticated student session + per-student/per-course rate limit
<!-- AC:END -->
