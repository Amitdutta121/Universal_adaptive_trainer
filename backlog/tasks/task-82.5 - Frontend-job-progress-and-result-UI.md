---
id: TASK-82.5
title: 'Frontend: job progress and result UI'
status: Later
assignee: []
created_date: '2026-10-05 17:40'
updated_date: '2026-10-05 17:45'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-82.2
  - TASK-82.3
  - TASK-82.4
parent_task_id: TASK-82
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the long awaited mutations with enqueue + poll (React Query refetchInterval) for coverage, generate, regenerate, curriculum drafts. Start from frontend/src/lib/api/queries.ts (useGenerateCoverageRun).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Progress visible; closing and reopening the tab shows the same job
- [ ] #2 Failure shows the error with a Retry button
<!-- AC:END -->
