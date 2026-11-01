---
id: TASK-73
title: Rate limiting and brute-force protection
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - backend
milestone: m-5
dependencies: []
priority: high
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No rate limits on POST /students, /students/resume, login. Unique student names allow name probing.
Evidence: app/web/routes/api/students.py:332-360; app/web/routes/api/auth.py:17
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Login/resume/enrol throttled per IP; backoff on repeated failure
<!-- AC:END -->
