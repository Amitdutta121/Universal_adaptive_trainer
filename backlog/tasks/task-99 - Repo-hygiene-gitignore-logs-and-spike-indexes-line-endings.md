---
id: TASK-99
title: 'Repo hygiene: gitignore logs and spike indexes, line endings'
status: To Do
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:32'
labels:
  - hygiene
milestone: m-7
dependencies: []
priority: low
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
20 untracked *_fresh_*.log files, spikes/.rag_* indexes (32MB), loose tune_adaptive_params.py. Biome format fails repo-wide from CRLF autocrlf.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 *.log and spikes/.rag_* ignored
- [ ] #2 .gitattributes eol=lf; pnpm run lint passes
<!-- AC:END -->
