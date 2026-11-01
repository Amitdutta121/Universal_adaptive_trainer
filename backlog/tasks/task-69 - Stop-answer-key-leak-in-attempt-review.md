---
id: TASK-69
title: Stop answer-key leak in attempt review
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - backend
milestone: m-4
dependencies: []
priority: high
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
/attempts/{id}/review returns the full answer key with course=None and no ownership check.
Evidence: app/web/routes/api/students.py:641-659
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Review only returns keys to the owning student after scoring
<!-- AC:END -->
