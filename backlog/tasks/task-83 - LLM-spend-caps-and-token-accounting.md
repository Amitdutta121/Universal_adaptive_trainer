---
id: TASK-83
title: LLM spend caps and token accounting
status: To Do
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:32'
labels:
  - llm
  - backend
milestone: m-5
dependencies: []
priority: high
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No rate limiting, token usage tracking, or budget cap anywhere in app/.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-call token usage persisted
- [ ] #2 Configurable per-course/daily spend cap blocks generation when exceeded
<!-- AC:END -->
