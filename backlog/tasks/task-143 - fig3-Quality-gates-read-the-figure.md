---
id: TASK-143
title: fig3 Quality gates read the figure
status: Done
assignee: []
created_date: '2026-11-10 02:15'
updated_date: '2026-11-10 04:36'
labels:
  - backend
milestone: m-12
dependencies:
  - TASK-141
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Plan: docs/FIGURE_QUESTIONS_MILESTONES.md (fig3). Evidence: app/retrieval/duplicates.py:68, app/generation/solve.py:74, app/evaluation/prompts.py:327
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Same wording with different figures is not flagged duplicate
- [x] #2 Seeded chart/key mismatch is flagged by the solver
- [x] #3 Judge rubric version changes only for courses whose questions carry figures
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Duplicate check, solver and judge figure gates covered by tests/test_figure_gates.py; targeted suites passed.
<!-- SECTION:FINAL_SUMMARY:END -->
