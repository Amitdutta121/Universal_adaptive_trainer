---
id: TASK-134
title: Reconcile the dev database's create_all-era drift
status: To Do
assignee: []
created_date: '2026-10-05 17:50'
labels:
  - data
  - backend
milestone: m-0
dependencies: []
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
alembic check against data/adaptive_trainer.db (after init_db) reports drift that a fresh migrated DB does not: legacy tables preference_statements and review_embeddings, questions.regenerated_from_question_id FK missing ondelete SET NULL, students.resume_token nullable. Decide drop-or-keep via a migration guarded for databases that lack them. Evidence: alembic check with DATABASE_URL=sqlite:///data/adaptive_trainer.db; ADR-057
<!-- SECTION:DESCRIPTION:END -->
