---
id: TASK-137
title: Live tutorial jobs race on lazy chunk embeddings for a newly imported book
status: Done
assignee: []
created_date: '2026-11-01 03:15'
updated_date: '2026-11-03 10:43'
labels:
  - bug
dependencies: []
ordinal: 88000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two live tutorial pregeneration jobs for the same course started together right after a fresh book import (no chunk_embeddings yet). Both embedded the same chunks and the second failed with sqlite3.IntegrityError: UNIQUE constraint failed: chunk_embeddings.chunk_id, chunk_embeddings.model (background_jobs id 5, 2026-11-01). Its block was not written. Evidence: app/tutorials/live.py (plan/enqueue), app/retrieval/chunks.py (embedding on first search), .dev/backend.out.log. Repro: import a new PDF, then answer two questions in a student session within a few seconds.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Two concurrent jobs embedding the same chunks no longer fail; the second reuses or skips existing rows
- [x] #2 A test covers concurrent first-time embedding of one chunk
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ChunkEmbeddingStore.backfill now catches the (chunk, model) IntegrityError, keeps the other writer's vectors and inserts only the rest. Covered by tests/test_source_embedding.py::test_two_writers_embedding_the_same_chunks_both_succeed. Landed with auto-embedding on import.
<!-- SECTION:FINAL_SUMMARY:END -->
