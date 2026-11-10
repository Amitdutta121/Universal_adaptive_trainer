---
id: TASK-146
title: fig6 Professor controls for figures
status: Done
assignee: []
created_date: '2026-11-10 02:15'
updated_date: '2026-11-10 04:36'
labels:
  - backend
  - frontend
milestone: m-12
dependencies:
  - TASK-144
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Plan: docs/FIGURE_QUESTIONS_MILESTONES.md (fig6). Evidence: app/feedback/service.py:89
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Professor can edit a diagram or chart in review; stored as an edit, re-validated, re-judged
- [x] #2 Professor can regenerate one copy of a computed question
- [x] #3 Professor can turn figures off for a course
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Review submit sends figure edits and blocks on figureError; regenerate-copy hook + per-copy Regenerate button; course settings Allow figure questions (figures_enabled). Verified with tsc, biome lint, and vitest on courses/components/review.
<!-- SECTION:FINAL_SUMMARY:END -->
