---
id: TASK-102
title: 'Transactional email service (invites, verification, reset)'
status: Later
assignee: []
created_date: '2026-10-05 17:35'
updated_date: '2026-10-05 17:45'
labels:
  - e2e-gap
  - backend
  - needs-decision
milestone: m-1
dependencies: []
priority: high
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No email infra at all (no hits for smtp/sendgrid/resend/ses). Blocks invites, verification, password reset (task-75), notifications.
Decision (needs confirm): Resend via its HTTP API, with an SMTP backend selectable by env for university mail servers. Alternative: AWS SES.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Provider-agnostic mailer (e.g. Resend/SES) with templates
- [ ] #2 Dev mode logs emails instead of sending
<!-- AC:END -->
