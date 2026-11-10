---
id: TASK-141
title: fig1 Figure field end to end with hand-made questions
status: Done
assignee: []
created_date: '2026-11-10 02:15'
updated_date: '2026-11-10 04:42'
labels:
  - backend
  - frontend
milestone: m-12
dependencies: []
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Plan: docs/FIGURE_QUESTIONS_MILESTONES.md (fig1). ADR-080. Evidence: app/question_types/base.py:39, app/web/routes/api/schemas.py:2280, frontend/src/components/prompt-text.tsx, app/tutorials/renderers.py:105
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Choice, numeric and true/false questions each with a diagram, chart and computed figure render on the student screen and in review
- [x] #2 figure never leaks answer fields (whitelist test)
- [x] #3 Broken Mermaid source fails figure_problems
- [x] #4 Subject-word scan of figure code passes
- [x] #5 Python golden prompts unchanged
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Figure field end-to-end: seeded MC/numeric/TF with diagram, chart and computed figures. Browser-checked on course 6 (questions 505-507 review) and student set 9 (sessions 47-48): Mermaid SVG, Chart.js canvas, and computed SVG all rendered. Seed script absolute_tolerance fixed so numeric answers mark.
<!-- SECTION:FINAL_SUMMARY:END -->
