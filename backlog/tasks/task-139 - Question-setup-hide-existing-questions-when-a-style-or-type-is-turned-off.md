---
id: TASK-139
title: 'Question setup: hide existing questions when a style or type is turned off'
status: Done
assignee: []
created_date: '2026-11-02 23:11'
updated_date: '2026-11-03 01:02'
labels:
  - frontend
  - backend
milestone: m-8
dependencies:
  - TASK-138
priority: medium
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Phase 2 of the type-first setup (task-138). Turning a style off (course or subtopic scope) opens a dialog with its approved-question count and 'Also hide the N existing questions from students'; turning it back on offers 'Show the N hidden questions to students again'. Needs per-style approved-question counts (QuestionRow.style_id) and a new QuestionStatus.HIDDEN (not deleted, not REJECTED, which would feed style_rejects) with an Alembic migration. Disallowing a type in course Settings should offer the same hide choice.
Evidence: frontend/src/app/experiments/question-types/toggle-dialog.tsx, question-types-experience.tsx (requestToggle, slotsBelowTarget), setup-model.ts (turnOff/turnOn hidden counts, existingCount stand-in); frontend/src/app/courses/courses-screen.tsx CourseFormDialog
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Turning a style or type off with approved questions behind it opens the turn-off dialog with the count, per-scope, and an option to hide those questions
- [x] #2 Turning a style back on with hidden questions offers to show them again
- [x] #3 QuestionStatus.HIDDEN exists with an Alembic migration; hidden questions are not served to students and do not count as rejects for style_rejects
- [x] #4 An API returns approved-question counts per style (course and per subtopic)
- [x] #5 Disallowing a type in course Settings offers the same hide choice
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added QuestionStatus.HIDDEN (migration 0032_hidden_question_status, ADR-070), plus GET/POST /api/question-visibility for per-style/type/subtopic-cell counts and hiding/showing, scoped to the course. The setup dialog and course Settings now use the prototype's turn-off/turn-on dialog. Verified with backend tests in tests/test_question_visibility.py (counts, hide/show, not served, no style_rejects) and the isolation sweep, vitest dialog tests, and the real flow on course 2 (setup dialog course+subtopic, Settings hide+show, settings restored).
<!-- SECTION:FINAL_SUMMARY:END -->
