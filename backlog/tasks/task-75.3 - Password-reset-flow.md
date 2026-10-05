---
id: TASK-75.3
title: Password reset flow
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:44'
labels:
  - backend
  - frontend
milestone: m-1
dependencies:
  - TASK-102
parent_task_id: TASK-75
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Expose the fastapi-users reset-password router (currently not exposed, app/config.py:161) and add Forgot password to frontend/src/app/login/login-screen.tsx.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reset email received; old password stops working
<!-- AC:END -->
