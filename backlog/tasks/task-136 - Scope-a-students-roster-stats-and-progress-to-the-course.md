---
id: TASK-136
title: Scope a student's roster stats and progress to the course
status: To Do
assignee: []
created_date: '2026-10-05 18:18'
labels:
  - security
  - backend
milestone: m-1
dependencies: []
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A student in two courses shows answered count, average score and mastery from both on either course's roster and student page (stats_by_student, _progress are not course-filtered). Access is already gated by task-74. Evidence: app/persistence/repositories.py StudentAttemptRepository.stats_by_student, app/web/routes/api/students.py _progress
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Roster figures and student progress count only the requesting course's sessions
<!-- AC:END -->
