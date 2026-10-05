---
id: TASK-129
title: LTI 1.3 launch and grade passback (AGS)
status: Later
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:45'
labels:
  - e2e-gap
  - backend
  - needs-decision
milestone: m-10
dependencies: []
priority: low
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No LMS integration. Universities run courses in Canvas/Moodle.
Decision (needs confirm): PyLTI1p3 with a thin FastAPI adapter (the library ships Flask and Django adapters only). Alternative: a hosted LTI service such as LTIaaS.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Launch from a Canvas test instance signs student in
- [ ] #2 Chosen metric passes back to gradebook
<!-- AC:END -->
