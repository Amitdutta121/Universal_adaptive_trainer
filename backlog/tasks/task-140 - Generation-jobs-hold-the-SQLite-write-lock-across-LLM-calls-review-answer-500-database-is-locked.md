---
id: TASK-140
title: >-
  Generation jobs hold the SQLite write lock across LLM calls (review/answer 500
  database is locked)
status: Done
assignee: []
created_date: '2026-11-03 01:46'
updated_date: '2026-11-03 02:09'
labels:
  - backend
milestone: m-8
dependencies: []
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Round and live generation flush embedding-cache (and other) writes, then make LLM/embedder calls in the same transaction, holding SQLite's single write lock for 20-60s. Concurrent professor reviews and student answers wait 5s and 500. Fix: read -> LLM (no open write tx) -> short write tx; guard test; 503 for lock errors.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A round and a live job never hold an open write transaction during an LLM or embedder call (guard test with a second connection)
- [x] #2 Embedding-cache writes happen in the write phase, not mid-generation
- [x] #3 database is locked maps to 503 retryable, not 500 unknown_error
- [x] #4 SQLite busy timeout raised as hygiene via config
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Round and live jobs now commit the read phase (examples, embedding cache) before model calls; the round duplicate check no longer writes cache rows (embed_with persist=False). Lock errors return 503 database_busy; SQLite busy timeout is DATABASE_BUSY_TIMEOUT_SECONDS (15). ADR-071. Guard tests in tests/test_write_lock_discipline.py fail without the fix and pass with it; full suite: only the 7 known pre-existing failures plus one load-flaky grader timeout that passes alone.
<!-- SECTION:FINAL_SUMMARY:END -->
