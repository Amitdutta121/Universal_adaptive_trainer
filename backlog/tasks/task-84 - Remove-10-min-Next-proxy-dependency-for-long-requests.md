---
id: TASK-84
title: Remove 10-min Next proxy dependency for long requests
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - frontend
  - infra
milestone: m-3
dependencies:
  - TASK-82
priority: medium
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
/api rewrite runs in prod with proxyTimeout 600_000; fragile behind LB/reverse proxy. API_ORIGIN baked at build time with silent fallback to 127.0.0.1:8000.
Evidence: frontend/next.config.ts:11,39; frontend/src/lib/env.ts:13
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No request through the proxy exceeds 30s (jobs instead)
- [ ] #2 Missing API_ORIGIN fails the build loudly
<!-- AC:END -->
