---
id: TASK-77
title: Remove dev credentials and /experiments from prod build
status: Later
assignee: []
created_date: '2026-10-05 17:30'
updated_date: '2026-10-05 17:44'
labels:
  - security
  - frontend
milestone: m-6
dependencies: []
priority: high
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Landing page prints devpassword123; login placeholder shows dev@local.test; 11 /experiments/* mock prototypes ship publicly and skip auth; public/db-map.html is served.
Evidence: frontend/src/app/page.tsx:251-252; frontend/src/app/login/login-screen.tsx:57; frontend/src/components/app-chrome.tsx:84
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No dev creds in prod bundle
- [ ] #2 C:/Program Files/Git/experiments returns 404 in production build
<!-- AC:END -->
