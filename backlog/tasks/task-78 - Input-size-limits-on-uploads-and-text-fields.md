---
id: TASK-78
title: Input size limits on uploads and text fields
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - security
  - backend
milestone: m-7
dependencies: []
priority: medium
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Uploads read fully into memory before size check (100MB). AnswerRequest.answer unbounded; only 24 max_length across 149 models.
Evidence: app/web/routes/api/books.py:99; app/ingestion/storage.py:85-90; app/web/routes/api/schemas.py:2411
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Streamed upload with early reject
- [ ] #2 max_length on all free-text request fields
<!-- AC:END -->
