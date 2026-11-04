---
id: TASK-138
title: 'Type-first question setup dialog (course/subtopic scope, allowed-type gate)'
status: Done
assignee: []
created_date: '2026-11-02 23:11'
updated_date: '2026-11-02 23:21'
labels:
  - frontend
milestone: m-8
dependencies: []
priority: medium
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rebuild step 2 of the Set up questions dialog as the approved prototype: scope rail (Whole course / one subtopic), question types with switches, coverage strip, per-type style table and rows. Three layers decide a subtopic's styles: course on/off, AI suggestion intersected with the course, subtopic overrides. approved_styles storage unchanged; overrides are derived on open. Phase 2 (turn-off dialogs, HIDDEN status) is a separate task.
Evidence: frontend/src/app/experiments/question-types/ (question-types-experience.tsx, step-styles.tsx, step-targets.tsx, setup-model.ts); frontend/src/app/courses/[courseId]/questions/setup/question-setup-dialog.tsx, setup-state.ts; frontend/src/components/question-setup/style-row.tsx; frontend/src/app/courses/question-type-picker.tsx
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Step 2 is type-first: scope rail (Whole course default, topics and subtopics with Custom badge), types with switch, N of M and difficulty bars, coverage strip, Easy/Medium/Hard style table and StyleRow per style with its own Switch
- [x] #2 Course -> AI suggestion ∩ course -> subtopic overrides decide a subtopic's styles; course changes reach every subtopic, subtopic edits stay local; course-off styles are disabled with 'Off for the course'; Suggested badge and Reset to course in subtopic scope; type switch turns all its styles on/off
- [x] #3 Save still sends approved_styles (resolved effective set per subtopic) via saveRequest; an existing setup is derived back into course-on and per-subtopic overrides; a new setup starts with every library style of an allowed type on
- [x] #4 Only course.question_types are usable; other library types are greyed 'Not allowed in this course' with switches disabled, and 'Allow for this course' adds the type through the course update mutation; a blocked type's styles are remembered
- [x] #5 Targets step shows a Custom badge per subtopic, a warning cell when a planned difficulty has no style, and clicking a subtopic jumps to step 2 scoped to it
- [x] #6 style-groups.ts and its uses are removed; course-styles.tsx and custom-rules.tsx unchanged
- [x] #7 Copy matches the prototype, no explanatory paragraphs; pure layer logic unit-tested with vitest; gates pass and the dialog is checked in the browser
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Step 2 of Set up questions is type-first (scope rail, types with switches, coverage, style table + StyleRows) over a pure layer model in setup-state.ts (course-on, AI fit, subtopic overrides, derived from saved approved_styles); allowed-type gate with inline Allow via PATCH /api/courses; targets get Custom/no-style cells and jump-back; style-groups.ts removed; ADR-069. Verified: tsc, biome lint, vitest setup folder 28/28 (new setup-state.test.ts), and in the browser on course 2 (Edit setup, course switch-off, override/reset, Allow then restored, targets, cancelled without saving).
<!-- SECTION:FINAL_SUMMARY:END -->
