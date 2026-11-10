---
id: TASK-142
title: fig2 Styles can ask for a figure; diagram and chart questions generated
status: Done
assignee: []
created_date: '2026-11-10 02:15'
updated_date: '2026-11-10 03:55'
labels:
  - backend
milestone: m-12
dependencies:
  - TASK-141
ordinal: 93000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Plan: docs/FIGURE_QUESTIONS_MILESTONES.md (fig2). Evidence: app/styles/schema.py:77, app/styles/drafting.py, app/generation/prompts.py:171, app/course_design/design.py, app/curriculum/capabilities.py
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Style drafter proposes a figure style for structure/dataset material in two unrelated subjects and none otherwise (fake LLM)
- [x] #2 Generated figure questions pass the type's authoring checks
- [x] #3 Python golden prompts unchanged for styles without a figure
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Round generation dispatches computed styles to generate_computed_question; BaseQuestionGenerator.prepare shares prompts, generate_one refuses computed styles. tests/test_figure_styles.py (fake LLM): drafter makes diagram/chart styles for a biology and a custom course and keeps none for recall; generated diagram/chart questions pass the type checks (figure_drawable), broken Mermaid is repaired; subject-word scan of all figure prompt text. Golden prompts unchanged (test_golden_prompts).
<!-- SECTION:FINAL_SUMMARY:END -->
