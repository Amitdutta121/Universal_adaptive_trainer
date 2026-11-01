---
id: TASK-68
title: Authenticate students on training-session and attempt routes
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - backend
  - blocker
  - needs-decision
milestone: m-4
dependencies: []
priority: high
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Student routes are public and keyed by sequential int ids; resume_token is never checked. Anyone can impersonate any student, read progress, answer for them.
Evidence: app/web/routes/api/students.py:404,475-490,534-662; app/web/routes/api/schemas.py:2322
Decision (needs confirm): student credential = the existing resume_token, made a random 32-byte secret (not guessable), sent as an httpOnly cookie and checked by one FastAPI dependency on every student route. Alternative: a full student account (that is task-115).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every /training-sessions/* and /attempts/* route requires the student token and rejects other students ids (403)
- [ ] #2 Test enumerating another student session id fails
<!-- AC:END -->
