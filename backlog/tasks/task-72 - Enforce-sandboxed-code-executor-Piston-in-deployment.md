---
id: TASK-72
title: Enforce sandboxed code executor (Piston) in deployment
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - infra
milestone: m-5
dependencies: []
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Default EXECUTOR=local runs student code in an unsandboxed subprocess. Piston compose exists separately but is not wired into main compose.
Evidence: app/config.py:76; graders/executors/local.py:1-5; docker/piston/docker-compose.yml
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Prod compose includes Piston and sets EXECUTOR=piston
- [ ] #2 Code-type questions grade through Piston end to end
<!-- AC:END -->
