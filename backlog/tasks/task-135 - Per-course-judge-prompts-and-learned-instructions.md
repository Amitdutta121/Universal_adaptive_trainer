---
id: TASK-135
title: Per-course judge prompts and learned instructions
status: Done
assignee: []
created_date: '2026-10-05 18:18'
updated_date: '2026-10-05 19:24'
labels:
  - security
  - backend
milestone: m-1
dependencies: []
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Judge prompts and learned instructions are keyed by subject (ADR-056), so a professor's edit or relearn changes every course of that subject, including other professors'. Found while doing task-74 (ADR-058). Evidence: app/web/routes/api/judge_prompts.py, app/web/routes/api/instructions.py, app/subjects
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One professor's judge-prompt edit or learned rule does not change another professor's course
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Judge prompts and learned instructions keyed by SubjectProfile.personal_key (preset@owner), migration 0010 rekeys existing rows (ADR-059). Verified: test_course_access judge isolation test + every-page review video.
<!-- SECTION:FINAL_SUMMARY:END -->
