---
id: TASK-121
title: Staging environment
status: Later
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:45'
labels:
  - e2e-gap
  - infra
  - needs-decision
milestone: m-5
dependencies:
  - TASK-89
priority: high
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Environment enum is only development/test/production (app/config.py:22-27); no staging.
Decision (needs confirm): second docker compose project on the same VM with its own DB, secrets and subdomain, deployed from main; prod deploys from tags. Alternative: a separate small VM.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Staging deploy with its own DB and secrets; one-command deploy to staging and prod
<!-- AC:END -->
