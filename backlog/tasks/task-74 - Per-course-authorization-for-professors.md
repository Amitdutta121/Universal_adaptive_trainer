---
id: TASK-74
title: Per-course authorization for professors
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - backend
milestone: m-1
dependencies: []
priority: high
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Any professor sees every course; X-Course-Id is optional and omission means all courses. GENERIC_ASSESSMENT S5 also found question-detail/review/student routes not course-scoped.
Evidence: app/web/deps.py:41-42,89-95
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Course access checked against owner_id/membership on every course-scoped route
- [ ] #2 Cross-course access test returns 403/404
<!-- AC:END -->
