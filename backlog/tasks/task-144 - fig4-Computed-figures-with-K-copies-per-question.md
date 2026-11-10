---
id: TASK-144
title: fig4 Computed figures with K copies per question
status: Done
assignee: []
created_date: '2026-11-10 02:15'
updated_date: '2026-11-10 03:55'
labels:
  - backend
  - frontend
milestone: m-12
dependencies:
  - TASK-142
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Plan: docs/FIGURE_QUESTIONS_MILESTONES.md (fig4). SVGs saved as files with a DB pointer (ADR-080 point 4); programs that run long are rejected (point 3). Evidence: graders/executors, app/config.py
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A crashing, invalid-JSON, slow or check-failing program is repaired or rejected, never served
- [x] #2 Two attempts can get different copies and each is scored against its own key
- [x] #3 SQLAlchemy only; Alembic upgrade/downgrade works
- [x] #4 A student never receives the program or another copy's key
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
tests/test_computed_figures.py (real local executor, fake LLM): crash repaired; crash/invalid JSON/bad fields/forbidden import/slow (timeout) rejected with nothing stored; two students get different copies, each scored on its own key; student serve and attempt review carry no program or other copy; 0034 downgrade/upgrade. Review screen shows all copies + program (QuestionDetail.figure_copies/figure_program, new QuestionFigureCopies component). regenerate_copy() added for fig6. Chrome run not done.
<!-- SECTION:FINAL_SUMMARY:END -->
