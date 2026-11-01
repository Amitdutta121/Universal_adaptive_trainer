---
id: TASK-75.1
title: Admin CLI to create professor accounts
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:44'
labels:
  - backend
milestone: m-1
dependencies: []
parent_task_id: TASK-75
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
python -m app.cli create-user --email --name using the fastapi-users user manager (see app/auth/). Works in production, unlike app/auth/seed.py:25.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Creates a user who can log in; refuses duplicates
<!-- AC:END -->
