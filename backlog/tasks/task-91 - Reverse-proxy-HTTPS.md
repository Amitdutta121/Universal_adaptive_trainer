---
id: TASK-91
title: Reverse proxy + HTTPS
status: Later
assignee: []
created_date: '2026-10-05 17:31'
updated_date: '2026-10-05 17:45'
labels:
  - infra
  - needs-decision
milestone: m-5
dependencies: []
priority: high
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No nginx/Caddy/TLS config; the only remote access is Tailscale dev access.
Decision (needs confirm): Caddy in front of both apps on a single VM: automatic Let's Encrypt HTTPS, routes / to Next and /api to FastAPI directly (no Next proxy). Alternative: nginx + certbot, or a PaaS such as Fly.io or Render.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Caddy or nginx terminates TLS and routes / and /api
- [ ] #2 Secure cookies verified over HTTPS
<!-- AC:END -->
