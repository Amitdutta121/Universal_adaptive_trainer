---
id: TASK-75
title: Professor account provisioning and password reset
status: To Do
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:47'
labels:
  - security
  - backend
  - frontend
milestone: m-1
dependencies: []
priority: high
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Only a dev-seeded account exists; no registration/admin/invite route; no password reset (app/config.py:161). A prod deploy has no way to get a professor in.
Evidence: app/auth/seed.py:25; app/web/routes/api/auth.py:3-4
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Admin CLI or invite flow creates professor accounts
- [ ] #2 Password reset flow works
<!-- AC:END -->
