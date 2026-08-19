"""Cookie-session auth for the professor console.

There is one identity kind (a professor); students never log in and reach
their sessions anonymously by link (ADR-041). Built on ``fastapi-users`` with
its database session strategy, so logging out revokes the session
server-side rather than merely clearing the browser's cookie.

Depends on :mod:`app.config` and :mod:`app.persistence` (both the sync engine,
for schema creation, and :mod:`app.persistence.async_database`, which this
subsystem is the only user of). Nothing outside ``app/auth`` and
``app/web/routes/api/auth.py`` should import ``fastapi_users`` directly --
route modules that need to require a logged-in professor take
``Depends(current_active_user)`` from :mod:`app.auth.backend`.
"""

from __future__ import annotations
