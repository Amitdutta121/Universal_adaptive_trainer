---
id: TASK-71
title: 'Production config guard: refuse to boot with unsafe defaults'
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - backend
  - blocker
milestone: m-5
dependencies: []
priority: high
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
debug=True, auth_secret_key=dev-only-insecure..., environment=development are defaults; only the executor checks prod. Secure-cookie flag and dev account seeding hinge on ENVIRONMENT, and docker-compose sets development.
Evidence: app/config.py:58,59,164; app/auth/backend.py:50; docker-compose.yml:7; app/auth/seed.py:25
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ENVIRONMENT=production startup fails if secret is default, debug on, EXECUTOR=local, or CORS includes localhost
- [ ] #2 Dev account never seeded in production
<!-- AC:END -->
