"""UI / API boundary.

Server-rendered Jinja2 pages for the professor plus a small JSON API. Routes are
thin: they resolve a session, call a repository or service, and render. Business
rules belong in the subsystem packages, not here.
"""
