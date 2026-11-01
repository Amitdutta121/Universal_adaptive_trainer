---
id: TASK-85
title: 'm5: auto-embed on ingest + /api/retrieval/status'
status: To Do
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:32'
labels:
  - llm
  - backend
milestone: m-3
dependencies: []
priority: medium
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Book embedding is still manual; no backfill call after import, no status route.
Evidence: docs/MILESTONES.md:258; app/ingestion/service.py
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ingest triggers SectionEmbeddingStore.backfill
- [ ] #2 GET /api/retrieval/status reports per-book freshness
<!-- AC:END -->
