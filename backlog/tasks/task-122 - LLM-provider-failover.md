---
id: TASK-122
title: LLM provider failover
status: To Do
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:40'
labels:
  - e2e-gap
  - llm
  - backend
  - needs-decision
milestone: m-5
dependencies: []
priority: medium
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Single OpenRouter client; retries the same model only (app/llm/client.py:89,104); other providers raise (162-165).
Decision (needs confirm): use OpenRouter's built-in fallback (the models list in the request) instead of a second provider client. Alternative: add a direct OpenAI or Anthropic client behind the existing client interface.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Configurable fallback model/provider on repeated failure
- [ ] #2 Alert when provider failure rate is high
<!-- AC:END -->
