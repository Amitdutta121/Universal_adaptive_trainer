---
id: TASK-93
title: 'Structured logging, error tracking, metrics'
status: Later
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:45'
labels:
  - infra
  - backend
  - needs-decision
milestone: m-5
dependencies: []
priority: medium
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Good base (global handler, request-id middleware, /api/health) but plain-text logs, no Sentry, no metrics.
Evidence: app/logging_config.py:34; app/errors.py:286; app/web/middleware.py
Decision (needs confirm): Sentry (backend and Next SDKs, free tier) for errors; structlog JSON logs to stdout. Alternative: OpenTelemetry to Grafana Cloud.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 JSON logs with request id
- [ ] #2 Error tracking on backend + frontend
- [ ] #3 Basic latency/error/LLM-cost metrics
<!-- AC:END -->
