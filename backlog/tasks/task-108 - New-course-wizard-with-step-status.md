---
id: TASK-108
title: New-course wizard with step status
status: To Do
assignee: []
created_date: '2026-10-05 17:35'
labels:
  - e2e-gap
  - frontend
milestone: m-8
dependencies: []
priority: high
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No wizard; only guidance is a Next-step hint on coverage (frontend/src/app/courses/[courseId]/coverage/components/readiness-summary-card.tsx:78). Each step is a separate page.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Stepper: subject -> material -> taxonomy -> generate -> review -> freeze -> share link
- [ ] #2 Each step shows what is left; course resumes at the step where it stopped
<!-- AC:END -->
