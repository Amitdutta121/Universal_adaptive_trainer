---
id: TASK-96
title: Browser pass over new answer inputs + accessibility
status: To Do
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:32'
labels:
  - frontend
  - testing
milestone: m-6
dependencies: []
priority: medium
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Open item from GENERIC_ASSESSMENT_MILESTONES. Only one aria-live in the app; error alerts not announced; login fields not in a form element.
Evidence: frontend/src/app/courses/[courseId]/curriculum/builder/taxonomy-builder.tsx:777; frontend/src/app/login/login-screen.tsx:47-90
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every answer input type exercised in Chrome
- [ ] #2 axe scan: no serious/critical issues on core pages
<!-- AC:END -->
