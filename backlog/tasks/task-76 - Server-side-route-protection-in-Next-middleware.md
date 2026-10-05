---
id: TASK-76
title: Server-side route protection in Next (middleware)
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - frontend
milestone: m-6
dependencies: []
priority: medium
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No middleware.ts; instructor pages hidden only by client AuthGate. Any /me error (incl. 500) redirects to /login, masking outages. No return-to URL.
Evidence: frontend/src/components/auth-gate.tsx:19-28; frontend/src/app/login/login-screen.tsx:27
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Unauthenticated request to instructor route redirects server-side
- [ ] #2 5xx from /me shows an error, not login
<!-- AC:END -->
