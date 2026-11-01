---
id: TASK-123
title: Load test student sessions and generation
status: Later
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:45'
labels:
  - e2e-gap
  - testing
  - infra
milestone: m-5
dependencies: []
priority: medium
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No load testing (no locust/k6/artillery). Need to know capacity for one class (e.g. 200 concurrent students).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 k6 or locust script for join -> answer loop
- [ ] #2 Documented p95 latency and max concurrent students on target infra
<!-- AC:END -->
