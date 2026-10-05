---
id: TASK-95
title: Course index page and course layout access check
status: To Do
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:32'
labels:
  - frontend
milestone: m-6
dependencies: []
priority: medium
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
/courses/[courseId] has no page.tsx so the bare URL 404s; no course layout verifying the course exists / is accessible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Bare course URL redirects to dashboard
- [ ] #2 Unknown/forbidden course shows a proper error
<!-- AC:END -->
