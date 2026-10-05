---
id: TASK-89
title: Production docker-compose
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:45'
labels:
  - infra
milestone: m-5
dependencies: []
priority: high
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
compose has ENVIRONMENT=development, SQLite, no env_file (no API keys/AUTH_SECRET_KEY), no healthcheck conditions, no restart policy, no Piston.
Evidence: docker-compose.yml:6-10
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docker-compose.prod.yml with env_file, postgres, piston, healthchecks, restart policy
<!-- AC:END -->
