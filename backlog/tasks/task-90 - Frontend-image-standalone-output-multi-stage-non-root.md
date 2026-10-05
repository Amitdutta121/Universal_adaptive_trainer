---
id: TASK-90
title: 'Frontend image: standalone output, multi-stage, non-root'
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - infra
  - frontend
milestone: m-5
dependencies: []
priority: medium
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No output: standalone; single-stage node:20 as root with full source + node_modules.
Evidence: frontend/Dockerfile:1-22
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Multi-stage image using .next/standalone, non-root, HEALTHCHECK
<!-- AC:END -->
