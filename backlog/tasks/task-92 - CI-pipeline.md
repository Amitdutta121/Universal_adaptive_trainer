---
id: TASK-92
title: CI pipeline
status: To Do
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:45'
labels:
  - infra
  - testing
milestone: m-5
dependencies: []
priority: high
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No .github/workflows. Gates exist only locally: pytest, biome lint, tsc, vitest.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 main protected on green CI
- [ ] #2 PR workflow runs pytest, ruff, biome lint, tsc, vitest
<!-- AC:END -->
