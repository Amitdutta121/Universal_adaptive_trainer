---
id: TASK-88
title: 'Fix backend Docker image (graders/, alembic, non-root, workers)'
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - infra
  - blocker
milestone: m-5
dependencies: []
priority: high
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dockerfile copies only pyproject + app/: graders/ is missing (app imports it, ADR-055), alembic config/scripts missing. Single uvicorn worker, runs as root, no HEALTHCHECK.
Evidence: Dockerfile:16
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docker compose up --build yields a backend that grades a submission
- [ ] #2 Non-root user, HEALTHCHECK on /api/health
<!-- AC:END -->
