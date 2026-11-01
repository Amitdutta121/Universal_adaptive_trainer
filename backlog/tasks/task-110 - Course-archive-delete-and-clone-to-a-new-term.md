---
id: TASK-110
title: 'Course archive, delete, and clone to a new term'
status: To Do
assignee: []
created_date: '2026-10-05 17:35'
labels:
  - e2e-gap
  - backend
  - frontend
milestone: m-8
dependencies: []
priority: medium
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
app/web/routes/api/courses.py only has GET/POST/PATCH (lines 44-176). Professors reuse courses each semester.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Archive hides course, keeps data
- [ ] #2 Clone copies taxonomy + approved questions, not students
- [ ] #3 Delete with confirmation
<!-- AC:END -->
