---
id: TASK-74
title: Per-course authorization for professors
status: Done
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 18:39'
labels:
  - security
  - backend
milestone: m-1
dependencies: []
priority: high
ordinal: 500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Any professor sees every course; X-Course-Id is optional and omission means all courses. GENERIC_ASSESSMENT S5 also found question-detail/review/student routes not course-scoped.
Evidence: app/web/deps.py:41-42,89-95
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Course access checked against owner_id/membership on every course-scoped route
- [x] #2 Cross-course access test returns 403/404
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CourseScope now requires X-Course-Id and an owned course (404 otherwise); by-id and cohort routes (topics/subtopics, evaluations, regenerate, batch runs, calibration, retrieval, students) check or filter by course; course list/overview show only own courses; migration 0009 backfills owners and adds judge_batch_runs.course_id; CourseGate shows 'Course not found' (ADR-058). Verified: tests/test_course_access.py (20 cases) + full suite (only pre-existing HEAD failures), vitest/biome, live Playwright run on migrated copy of dev DB.
<!-- SECTION:FINAL_SUMMARY:END -->
