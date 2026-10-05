---
id: TASK-115
title: Student cross-device login (magic link)
status: Later
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:45'
labels:
  - e2e-gap
  - backend
  - frontend
  - needs-decision
milestone: m-4
dependencies:
  - TASK-68
priority: high
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Students are recognised only by a resume token in the browser (app/persistence/models.py:1221-1233); clearing storage or switching device loses their identity. Email is collected but not a login.
Decision (needs confirm): passwordless emailed magic link: signed single-use token (15 min expiry) that binds the device to the existing student record. Alternative: student passwords via fastapi-users (more support burden).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Student can sign in on a second device via emailed link and resume their run
<!-- AC:END -->
